// ============================================================================
// Steam Web API Client
// ============================================================================

import type {
  LibraryGame,
  SteamFriend,
  PlayerAchievement,
  StoreAppDetails,
  CountryPrice,
} from "../types.js";
import fetch, { type RequestInit } from "node-fetch";
import { HttpsProxyAgent } from "https-proxy-agent";

const STEAM_API_BASE = "https://api.steampowered.com";
const STEAM_STORE_BASE = "https://store.steampowered.com";

// node-fetch does not read proxy environment variables automatically.
// Reuse one proxy agent when HTTP_PROXY or HTTPS_PROXY is configured.
let _proxyAgent: HttpsProxyAgent<string> | null | undefined;
function getProxyAgent(): HttpsProxyAgent<string> | null {
  if (_proxyAgent !== undefined) return _proxyAgent;
  const proxyUrl =
    process.env.HTTP_PROXY || process.env.HTTPS_PROXY || "";
  if (!proxyUrl) {
    _proxyAgent = null;
    return _proxyAgent;
  }
  _proxyAgent = new HttpsProxyAgent(proxyUrl);
  return _proxyAgent;
}

function fetchOptions(): RequestInit {
  const agent = getProxyAgent();
  return agent ? { agent } as RequestInit : {};
}

export class SteamApiClient {
  readonly apiKey: string;
  readonly steamId: string;

  constructor(apiKey?: string, steamId?: string) {
    this.apiKey = apiKey || "";
    this.steamId = steamId || "";
  }

  get hasApiKey(): boolean {
    return this.apiKey.length > 0;
  }

  get hasSteamId(): boolean {
    return this.steamId.length > 0;
  }

  // ---- HTTP Helpers ----

  private async fetchJson<T>(url: string): Promise<T> {
    // Keep Steam response validation in one place so feature methods can stay
    // focused on mapping API payloads into app types.
    const resp = await fetch(url, fetchOptions());
    if (!resp.ok) {
      throw new Error(`Steam API returned ${resp.status}: ${resp.statusText}`);
    }
    return resp.json() as Promise<T>;
  }

  private apiUrl(iface: string, method: string, version: string, params: Record<string, string> = {}): string {
    const searchParams = new URLSearchParams({ ...params, key: this.apiKey });
    return `${STEAM_API_BASE}/${iface}/${method}/v${version}/?${searchParams.toString()}`;
  }

  // ---- Player Data ----

  /** Get the player's owned games (includes non-installed) */
  async getOwnedGames(): Promise<LibraryGame[]> {
    if (!this.hasApiKey || !this.hasSteamId) return [];

    const url = this.apiUrl("IPlayerService", "GetOwnedGames", "0001", {
      steamid: this.steamId,
      include_appinfo: "1",
      include_played_free_games: "1",
    });

    const data = await this.fetchJson<{
      response: { games?: LibraryGame[]; game_count?: number };
    }>(url);
    return data.response.games || [];
  }

  /** Get player summaries (names, avatars, status) for a list of Steam IDs */
  async getPlayerSummaries(steamIds: string[]): Promise<Record<string, { personaname: string; avatarfull: string; personastate: number; gameextrainfo?: string; profileurl: string }>> {
    if (!this.hasApiKey || steamIds.length === 0) return {};

    // batch in groups of 100
    const result: Record<string, unknown> = {};
    for (let i = 0; i < steamIds.length; i += 100) {
      const batch = steamIds.slice(i, i + 100);
      const url = this.apiUrl("ISteamUser", "GetPlayerSummaries", "0002", {
        steamids: batch.join(","),
      });
      const data = await this.fetchJson<{
        response: { players: Array<Record<string, unknown>> };
      }>(url);
      for (const player of data.response.players || []) {
        result[player.steamid as string] = player;
      }
    }
    return result as Record<string, { personaname: string; avatarfull: string; personastate: number; gameextrainfo?: string; profileurl: string }>;
  }

  // ---- Friends ----

  /** Get the friend list for the configured Steam ID */
  async getFriendList(): Promise<SteamFriend[]> {
    if (!this.hasApiKey || !this.hasSteamId) return [];

    const url = this.apiUrl("ISteamUser", "GetFriendList", "0001", {
      steamid: this.steamId,
    });

    const data = await this.fetchJson<{
      friendslist: { friends: SteamFriend[] };
    }>(url);
    return data.friendslist?.friends || [];
  }

  /** Enrich friend entries with names and status from summaries */
  async getEnrichedFriends(): Promise<SteamFriend[]> {
    const friends = await this.getFriendList();
    if (friends.length === 0) return [];

    const ids = friends.map((f) => f.steamid);
    const summaries = await this.getPlayerSummaries(ids);

    return friends.map((f) => ({
      ...f,
      personaname: summaries[f.steamid]?.personaname || f.steamid,
      avatarfull: summaries[f.steamid]?.avatarfull || "",
      personastate: summaries[f.steamid]?.personastate ?? 0,
      profileurl: summaries[f.steamid]?.profileurl || "",
      gameextrainfo: summaries[f.steamid]?.gameextrainfo,
    }));
  }

  // ---- Achievements ----

  /** Get achievements for a specific game */
  async getPlayerAchievements(appid: number): Promise<PlayerAchievement[]> {
    if (!this.hasApiKey || !this.hasSteamId) return [];

    const url = this.apiUrl("ISteamUserStats", "GetPlayerAchievements", "0001", {
      steamid: this.steamId,
      appid: String(appid),
      l: "zh-CN",
    });

    try {
      const data = await this.fetchJson<{
        playerstats: {
          gameName: string;
          success: boolean;
          achievements?: PlayerAchievement[];
        };
      }>(url);

      if (!data.playerstats?.success) return [];
      return data.playerstats.achievements || [];
    } catch {
      return [];
    }
  }

  /** Get user playtime stats for a specific game */
  async getUserStatsForGame(
    appid: number
  ): Promise<{ totalPlaytime: number; lastPlayed: number } | null> {
    if (!this.hasApiKey || !this.hasSteamId) return null;

    const url = this.apiUrl("ISteamUserStats", "GetUserStatsForGame", "0002", {
      steamid: this.steamId,
      appid: String(appid),
    });

    try {
      const data = await this.fetchJson<{
        playerstats: { stats: Array<{ name: string; value: number }> };
      }>(url);
      const stats = data.playerstats?.stats || [];
      const totalPlaytime =
        stats.find((s) => s.name === "total_time_played")?.value || 0;
      return { totalPlaytime, lastPlayed: 0 };
    } catch {
      return null;
    }
  }

  // ---- Store ----

  /** Get detailed store page information */
  async getStoreAppDetails(
    appid: number,
    country = "CN",
    language = "zh-CN"
  ): Promise<StoreAppDetails | null> {
    const url = `${STEAM_STORE_BASE}/api/appdetails?appids=${appid}&cc=${country}&l=${language}`;

    try {
      const data = await this.fetchJson<
        Record<string, { success: boolean; data: StoreAppDetails }>
      >(url);
      const entry = data[String(appid)];
      if (!entry?.success) return null;
      return entry.data;
    } catch {
      return null;
    }
  }

  /** Get the store page description (scraped short_description HTML) */
  async getStoreDescription(
    appid: number,
    country = "CN",
    language = "zh-CN"
  ): Promise<string> {
    try {
      const resp = await fetch(
        `${STEAM_STORE_BASE}/api/appdetails?appids=${appid}&cc=${country}&l=${language}`,
        fetchOptions()
      );
      const data = (await resp.json()) as Record<
        string,
        { success: boolean; data: { short_description: string } }
      >;
      const entry = data[String(appid)];
      if (!entry?.success) return "";
      return entry.data.short_description || "";
    } catch {
      return "";
    }
  }

  /** Get all prices for a game across all regions */
  async getAppPriceInfo(appid: number): Promise<Record<string, CountryPrice>> {
    try {
      const resp = await fetch(
        `https://store.steampowered.com/api/appdetails?appids=${appid}&filters=price_overview`,
        fetchOptions()
      );
      const data = (await resp.json()) as Record<string, { success: boolean; data: { price_overview: CountryPrice } }>;
      const entry = data[String(appid)];
      if (!entry?.success) return {};
      return { CN: entry.data.price_overview };
    } catch {
      return {};
    }
  }
}
