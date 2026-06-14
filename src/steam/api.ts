// ============================================================================
// Steam Web API Client — with proxy support via native https module
// (Node's built-in fetch/undici is incompatible with HttpsProxyAgent)
// ============================================================================

import type {
  LibraryGame,
  SteamFriend,
  PlayerAchievement,
  StoreAppDetails,
  CountryPrice,
} from "../types.js";
import { HttpsProxyAgent } from "https-proxy-agent";
import * as https from "node:https";
import * as http from "node:http";

const STEAM_API_BASE = "https://api.steampowered.com";
const STEAM_STORE_BASE = "https://store.steampowered.com";

let _proxyAgent: HttpsProxyAgent<string> | null | undefined = undefined;
function _getProxyAgent(): HttpsProxyAgent<string> | null {
  if (_proxyAgent !== undefined) return _proxyAgent;
  const proxyUrl = process.env.HTTP_PROXY || process.env.HTTPS_PROXY || "";
  if (!proxyUrl) {
    _proxyAgent = null;
    return null;
  }
  try {
    _proxyAgent = new HttpsProxyAgent(proxyUrl);
    return _proxyAgent;
  } catch {
    _proxyAgent = null;
    return null;
  }
}

/** Fetch JSON via native https/http module (works with HttpsProxyAgent). */
async function _fetchWithProxy(url: string, timeout = 15000): Promise<string> {
  const u = new URL(url);
  const isHttps = u.protocol === "https:";
  const mod = isHttps ? https : http;
  const agent = _getProxyAgent();
  const headers: Record<string, string> = { Accept: "application/json" };

  return new Promise((resolve, reject) => {
    const req = mod.request({
      hostname: u.hostname,
      path: u.pathname + u.search,
      agent: agent || undefined,
      headers,
      timeout,
    }, (res) => {
      let data = "";
      res.on("data", (chunk: Buffer) => data += chunk.toString());
      res.on("end", () => {
        if (res.statusCode && res.statusCode >= 400) {
          reject(new Error(`Steam API returned ${res.statusCode}`));
        } else {
          resolve(data);
        }
      });
    });
    req.on("error", (e: Error) => reject(new Error(`fetch failed: ${e.message}`)));
    req.on("timeout", () => { req.destroy(); reject(new Error("fetch timeout")); });
    req.end();
  });
}

export { _getProxyAgent };

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
    const text = await _fetchWithProxy(url);
    return JSON.parse(text) as T;
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
      const text = await _fetchWithProxy(
        `${STEAM_STORE_BASE}/api/appdetails?appids=${appid}&cc=${country}&l=${language}`
      );
      const data = JSON.parse(text) as Record<
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
      const text = await _fetchWithProxy(
        `https://store.steampowered.com/api/appdetails?appids=${appid}&filters=price_overview`
      );
      const data = JSON.parse(text) as Record<string, { success: boolean; data: { price_overview: CountryPrice } }>;
      const entry = data[String(appid)];
      if (!entry?.success) return {};
      return { CN: entry.data.price_overview };
    } catch {
      return {};
    }
  }
}
