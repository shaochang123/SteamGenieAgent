import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { SteamApiClient } from "../steam/api.js";
import type { SteamFriend } from "../types.js";
import { formatHours } from "./format.js";
import { textResult } from "./response.js";

const PERSONA_STATE: Record<number, string> = {
  0: "Offline",
  1: "Online",
  2: "Busy",
  3: "Away",
  4: "Snooze",
  5: "Looking to trade",
  6: "Looking to play",
};

const COOP_CATEGORY_IDS = [1, 9, 24, 27, 29, 38, 49]; // Multi-player, Co-op, Online Co-op, etc.
const STEAM_ID64_RE = /^\d{17}$/;
const isOnline = (friend: SteamFriend): boolean => friend.personastate !== 0;
const isPlaying = (friend: SteamFriend): boolean => Boolean(friend.gameextrainfo);

type FriendResolution =
  | { ok: true; steamId: string; label: string }
  | { ok: false; error: string };

function compareFriends(a: SteamFriend, b: SteamFriend): number {
  if (isOnline(a) && !isOnline(b)) return -1;
  if (!isOnline(a) && isOnline(b)) return 1;
  if (isPlaying(a) && !isPlaying(b)) return -1;
  if (!isPlaying(a) && isPlaying(b)) return 1;
  return (a.personaname || "").localeCompare(b.personaname || "");
}

function formatFriendLine(friend: SteamFriend): string {
  const status = PERSONA_STATE[friend.personastate || 0] || "Unknown";
  const playing = friend.gameextrainfo ? ` | playing ${friend.gameextrainfo}` : "";
  const displayName = friend.personaname || "Unknown";
  return `- **${displayName}** (SteamID64: ${friend.steamid}) - ${status}${playing}`;
}

function friendLabel(friend: SteamFriend): string {
  return `${friend.personaname || "Unknown"} (${friend.steamid})`;
}

function friendlySteamError(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  if (message.includes("400")) {
    return "Steam rejected the request. This usually means the friend identifier is not a valid SteamID64, or Steam cannot expose that account's library through the Web API.";
  }
  return message;
}

async function resolveFriendSteamId(
  api: SteamApiClient,
  friendQuery: string
): Promise<FriendResolution> {
  const query = String(friendQuery || "").trim();
  if (!query) {
    return {
      ok: false,
      error: "friend_steam_id is required. Provide a SteamID64, or call get_friend_list first and use a returned friend SteamID64.",
    };
  }

  if (STEAM_ID64_RE.test(query)) {
    return { ok: true, steamId: query, label: query };
  }

  let friends: SteamFriend[] = [];
  try {
    friends = await api.getEnrichedFriends();
  } catch {
    friends = [];
  }

  const normalized = query.toLowerCase();
  const exact = friends.find((friend) =>
    friend.steamid === query ||
    (friend.personaname || "").toLowerCase() === normalized
  );
  if (exact) {
    return { ok: true, steamId: exact.steamid, label: friendLabel(exact) };
  }

  const partialMatches = friends
    .filter((friend) => (friend.personaname || "").toLowerCase().includes(normalized))
    .slice(0, 5);

  if (partialMatches.length === 1) {
    const friend = partialMatches[0];
    return { ok: true, steamId: friend.steamid, label: friendLabel(friend) };
  }

  if (partialMatches.length > 1) {
    return {
      ok: false,
      error: `Multiple friends matched "${query}". Use one exact SteamID64 instead: ${partialMatches.map(friendLabel).join(", ")}`,
    };
  }

  return {
    ok: false,
    error: `Could not resolve "${query}" to a friend SteamID64. Call get_friend_list first, then pass the friend's SteamID64 to find_shared_games.`,
  };
}

export function registerSocialTools(
  server: McpServer,
  api: SteamApiClient
) {
  server.tool(
    "get_friend_list",
    "List Steam friends with online status and currently played games.",
    {
      online_only: z
        .boolean()
        .optional()
        .default(false)
        .describe("Only return online friends."),
    },
    async ({ online_only }) => {
      const friends = await api.getEnrichedFriends();

      if (friends.length === 0) {
        return textResult(
          "The friend list is empty or Steam API access is not configured.\nSet STEAM_API_KEY and STEAM_ID, then retry."
        );
      }

      const filtered = online_only ? friends.filter(isOnline) : friends;

      const online = friends.filter(isOnline);
      const playing = friends.filter(isPlaying);

      const lines = filtered.sort(compareFriends).map(formatFriendLine);

      return textResult(`Steam friends (${filtered.length})
Online: ${online.length} | In game: ${playing.length}

${lines.join("\n")}

Use find_shared_games to inspect games shared with a specific friend.`);
    }
  );

  server.tool(
    "find_shared_games",
    "Find games owned by both the configured user and a specific Steam friend.",
    {
      friend_steam_id: z
        .string()
        .describe("Friend SteamID64. An exact Steam persona name is accepted only if it can be resolved from get_friend_list."),
      coop_only: z
        .boolean()
        .optional()
        .default(false)
        .describe("Reserved option for filtering to co-op capable games."),
      limit: z
        .number()
        .optional()
        .default(30)
        .describe("Maximum number of shared games to return."),
    },
    async ({ friend_steam_id, limit }) => {
      let myGames;
      try {
        myGames = await api.getOwnedGames();
      } catch (error) {
        return textResult(`Unable to read the configured user's game library. ${friendlySteamError(error)}`);
      }
      if (myGames.length === 0) {
        return textResult("Unable to read the configured user's game library. Configure Steam API access first.");
      }

      const resolvedFriend = await resolveFriendSteamId(api, friend_steam_id);
      if (!resolvedFriend.ok) {
        return textResult(resolvedFriend.error);
      }

      const friendApi = new SteamApiClient(api.apiKey, resolvedFriend.steamId);
      let friendGames;
      try {
        friendGames = await friendApi.getOwnedGames();
      } catch (error) {
        return textResult(
          `Unable to read the game library for friend ${resolvedFriend.label}. ${friendlySteamError(error)}`
        );
      }

      if (friendGames.length === 0) {
        return textResult(
          `Unable to read the game library for friend ${resolvedFriend.label}. Verify that the friend's Steam library is public.`
        );
      }

      const myAppIds = new Set(myGames.map((g) => g.appid));
      const shared = friendGames.filter((g) => myAppIds.has(g.appid));

      const myPlaytime = new Map(
        myGames.map((g) => [g.appid, g.playtime_forever])
      );
      shared.sort(
        (a, b) =>
          (b.playtime_forever + (myPlaytime.get(b.appid) || 0)) -
          (a.playtime_forever + (myPlaytime.get(a.appid) || 0))
      );

      const lines = shared.slice(0, limit).map((g) => `- **${g.name}** (AppID: ${g.appid})
  Your playtime: ${formatHours(myPlaytime.get(g.appid) || 0)}h | Friend playtime: ${formatHours(g.playtime_forever)}h`);

      return textResult(`Shared games (${shared.length}, showing ${Math.min(limit, shared.length)})

${lines.join("\n")}

Use launch_game to start a game, or generate_invite to create an invite message.`);
    }
  );

  server.tool(
    "find_coop_game",
    "Recommend multiplayer or co-op games from the configured user's library for online friends.",
    {
      max_players: z
        .number()
        .optional()
        .default(4)
        .describe("Preferred maximum player count."),
      min_shared_count: z
        .number()
        .optional()
        .default(2)
        .describe("Minimum number of friends expected to own the game. This is advisory because Steam privacy limits friend library access."),
    },
    async () => {
      const friends = await api.getEnrichedFriends();
      const onlineFriends = friends.filter((f) => isOnline(f) && f.personastate !== undefined);

      if (onlineFriends.length === 0) {
        return textResult("No friends are currently online.");
      }

      const myGames = await api.getOwnedGames();
      if (myGames.length === 0) {
        return textResult("Unable to read the configured user's game library.");
      }

      // Recommend multiplayer/co-op games from the user's library.
      // Cross-referencing with friends' libraries is limited by Steam privacy settings.
      const candidates = myGames
        .filter((g) => g.playtime_forever > 0)
        .sort((a, b) => b.playtime_forever - a.playtime_forever)
        .slice(0, 20);

      const coopCandidates: Array<{
        name: string;
        appid: number;
        yourPlaytime: number;
      }> = [];
      for (const game of candidates) {
        const details = await api.getStoreAppDetails(game.appid);
        if (!details) continue;

        const isMultiplayer = details.categories?.some((c) =>
          COOP_CATEGORY_IDS.includes(c.id)
        );
        const genreText = (details.genres || [])
          .map((g) => g.description.toLowerCase())
          .join(" ");
        if (isMultiplayer || genreText.includes("multiplayer") || genreText.includes("co-op")) {
          coopCandidates.push({
            name: game.name,
            appid: game.appid,
            yourPlaytime: game.playtime_forever,
          });
        }
      }

      const yourPlaylist = coopCandidates.slice(0, 12);

      const lines = yourPlaylist.map(
        (g, i) => `${i + 1}. **${g.name}** (AppID: ${g.appid}) - your playtime: ${formatHours(g.yourPlaytime)}h`
      );

      return textResult(`Recommended co-op games from your library
Online friends: ${onlineFriends.length}
${lines.join("\n")}

Note: Steam privacy restrictions limit automatic friend-library matching. Use find_shared_games for a specific friend when their library is public.`);
    }
  );

  server.tool(
    "generate_invite",
    "Generate a short Steam game invite message for a friend.",
    {
      game_name: z.string().describe("Game name."),
      friend_name: z.string().describe("Friend display name."),
      style: z
        .enum(["funny", "serious", "casual", "enthusiastic"])
        .optional()
        .default("funny")
        .describe("Invite style: funny, serious, casual, or enthusiastic."),
      language: z
        .enum(["zh", "en"])
        .optional()
        .default("en")
        .describe("Output language. English is returned; zh is accepted for backward compatibility."),
    },
    async ({ game_name, friend_name, style, language }) => {
      const templates: Record<string, string[]> = {
        funny: [
          `Hey ${friend_name}! My copy of ${game_name} is gathering dust. Help me rescue it with one session?`,
          `${friend_name}, urgent mission: the NPCs in ${game_name} are asking for backup. Join me before they file a complaint.`,
        ],
        serious: [
          `Hi ${friend_name}, I am about to play ${game_name}. If you are available, I would like to team up for a session.`,
        ],
        casual: [
          `Hey ${friend_name}, want to play some ${game_name}? I saw you online and thought it could be a good time.`,
          `${friend_name}, are you free for ${game_name}? I am ready when you are.`,
        ],
        enthusiastic: [
          `${friend_name}, ${game_name} is exactly what I want to play tonight. Join me and let's get a good run going.`,
          `${friend_name}, queue up ${game_name}. I need a teammate and you are the first pick.`,
        ],
      };

      const outputLanguage = language === "zh" ? "English (zh accepted for compatibility)" : "English";
      const options = templates[style] || templates.funny;
      const message = options[Math.floor(Math.random() * options.length)];

      return textResult(`Generated invite
Style: ${style}
Language: ${outputLanguage}

---

${message}

---

You can send this message directly to ${friend_name}.`);
    }
  );

  server.tool(
    "get_friend_summary",
    "Summarize Steam friend availability, online counts, and currently played games.",
    {},
    async () => {
      const friends = await api.getEnrichedFriends();

      if (friends.length === 0) {
        return textResult("Unable to fetch the friend list. Configure Steam API access first.");
      }

      const online = friends.filter(isOnline);
      const playing = online.filter(isPlaying);

      const gameGroups = new Map<string, string[]>();
      for (const f of playing) {
        const game = f.gameextrainfo || "Unknown game";
        const existing = gameGroups.get(game) || [];
        existing.push(f.personaname || f.steamid);
        gameGroups.set(game, existing);
      }

      const gameLines = Array.from(gameGroups.entries())
        .sort((a, b) => b[1].length - a[1].length)
        .map(([game, players]) => `- **${game}**: ${players.length} players (${players.join(", ")})`);

      return textResult(`Friend summary
- Total friends: ${friends.length}
- Online: ${online.length}
- In game: ${playing.length}
- Online and idle: ${online.length - playing.length}

Current popular games:
${gameLines.length > 0 ? gameLines.join("\n") : "No friends are currently in game."}

Use find_coop_game to get multiplayer recommendations.`);
    }
  );
}
