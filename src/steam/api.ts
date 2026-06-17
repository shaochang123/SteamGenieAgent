import type {
  LibraryGame,
  SteamFriend,
  PlayerAchievement,
  StoreAppDetails,
} from "../types.js";
import { fetchSteamJson } from "./http.js";

const STEAM_API_BASE = "https://api.steampowered.com";
const STEAM_STORE_BASE = "https://store.steampowered.com";

type PlayerSummary = {
  personaname: string;
  avatarfull: string;
  personastate: number;
  gameextrainfo?: string;
  profileurl: string;
};

export class SteamApiClient {
  readonly apiKey: string;
  readonly steamId: string;

  constructor(apiKey?: string, steamId?: string) {
    this.apiKey = apiKey || "";
    this.steamId = steamId || "";
  }

  get hasApiKey(): boolean { return this.apiKey.length > 0; }

  get hasSteamId(): boolean { return this.steamId.length > 0; }

  get hasCredentials(): boolean { return this.hasApiKey && this.hasSteamId; }

  private apiUrl(iface: string, method: string, version: string, params: Record<string, string> = {}): string {
    const searchParams = new URLSearchParams({ ...params, key: this.apiKey });
    return `${STEAM_API_BASE}/${iface}/${method}/v${version}/?${searchParams.toString()}`;
  }

  async getOwnedGames(): Promise<LibraryGame[]> {
    if (!this.hasCredentials) return [];

    const url = this.apiUrl("IPlayerService", "GetOwnedGames", "0001", {
      steamid: this.steamId,
      include_appinfo: "1",
      include_played_free_games: "1",
    });

    const data = await fetchSteamJson<{
      response: { games?: LibraryGame[]; game_count?: number };
    }>(url);
    return data.response.games || [];
  }

  async getPlayerSummaries(steamIds: string[]): Promise<Record<string, PlayerSummary>> {
    if (!this.hasApiKey || steamIds.length === 0) return {};

    // batch in groups of 100
    const result: Record<string, unknown> = {};
    for (let i = 0; i < steamIds.length; i += 100) {
      const batch = steamIds.slice(i, i + 100);
      const url = this.apiUrl("ISteamUser", "GetPlayerSummaries", "0002", {
        steamids: batch.join(","),
      });
      const data = await fetchSteamJson<{
        response: { players: Array<Record<string, unknown>> };
      }>(url);
      for (const player of data.response.players || []) {
        result[player.steamid as string] = player;
      }
    }
    return result as Record<string, PlayerSummary>;
  }

  async getFriendList(): Promise<SteamFriend[]> {
    if (!this.hasCredentials) return [];

    const url = this.apiUrl("ISteamUser", "GetFriendList", "0001", {
      steamid: this.steamId,
    });

    const data = await fetchSteamJson<{
      friendslist: { friends: SteamFriend[] };
    }>(url);
    return data.friendslist?.friends || [];
  }

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

  async getPlayerAchievements(appid: number): Promise<PlayerAchievement[]> {
    if (!this.hasCredentials) return [];

    const url = this.apiUrl("ISteamUserStats", "GetPlayerAchievements", "0001", {
      steamid: this.steamId,
      appid: String(appid),
      l: "zh-CN",
    });

    try {
      const data = await fetchSteamJson<{
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

  async getStoreAppDetails(
    appid: number,
    country = "CN",
    language = "zh-CN"
  ): Promise<StoreAppDetails | null> {
    const locales = [
      [country, language],
      ["US", "en-US"],
    ];
    const tried = new Set<string>();

    for (const [cc, lang] of locales) {
      const key = `${cc}:${lang}`;
      if (tried.has(key)) continue;
      tried.add(key);

      const url = `${STEAM_STORE_BASE}/api/appdetails?appids=${appid}&cc=${cc}&l=${lang}`;
      try {
        const data = await fetchSteamJson<
          Record<string, { success: boolean; data: StoreAppDetails }>
        >(url);
        const entry = data[String(appid)];
        if (entry?.success && entry.data && typeof entry.data === "object") {
          return entry.data;
        }
      } catch {
        // Try the next locale before giving up.
      }
    }

    return null;
  }
}
