import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { SteamApiClient } from "../steam/api.js";
import { scanInstalledGames } from "../steam/vdf.js";
import { launchGame } from "../steam/launcher.js";
import type { GameSessionCandidate, LibraryGame, StoreAppDetails } from "../types.js";
import { formatCnyCents, formatHours, formatWholeHours, steamStoreUrl } from "./format.js";
import { textResult } from "./response.js";

const UNKNOWN = "Unknown";
const LIBRARY_SORTERS: Record<string, (a: LibraryGame, b: LibraryGame) => number> = {
  playtime: (a, b) => b.playtime_forever - a.playtime_forever,
  name: (a, b) => a.name.localeCompare(b.name),
  recent: (a, b) => b.playtime_2weeks - a.playtime_2weeks,
};

function formatStorePrice(details: StoreAppDetails): string {
  if (!details.price_overview) return "Price unknown";
  const price = details.is_free
    ? "Free"
    : formatCnyCents(details.price_overview.final);
  const discount = details.price_overview.discount_percent;
  return discount > 0 ? `${price} (${discount}% off)` : price;
}

function formatPlatforms(platforms: StoreAppDetails["platforms"]): string {
  return [
    platforms?.windows ? "Windows" : "",
    platforms?.mac ? "macOS" : "",
    platforms?.linux ? "Linux" : "",
  ].filter(Boolean).join(", ") || UNKNOWN;
}

function joinDescriptions(items: Array<{ description: string }> | undefined): string {
  return (items || []).map((item) => item.description).join(", ") || UNKNOWN;
}

function candidatePriorityScore(c: GameSessionCandidate, preferInstalled: boolean, preferUnplayed: boolean): number {
  return (preferInstalled && c.isInstalled ? 10 : 0) + (preferUnplayed && c.playtime_minutes < 30 ? 5 : 0);
}

function recommendationScore(c: GameSessionCandidate, preferUnplayed: boolean, availableMinutes: number): number {
  return (c.isInstalled ? 30 : 0) +
    (preferUnplayed && c.achievementProgress < 20 ? 25 : 0) +
    (c.ratingPercent > 0 ? Math.round(c.ratingPercent / 5) : 0) +
    (c.estimatedHours <= availableMinutes / 60 ? 20 : 0);
}

export function registerLibraryTools(
  server: McpServer,
  api: SteamApiClient,
  steamPath: string
) {
  server.tool(
    "list_games",
    "List the user's Steam library with playtime, recent activity, and optional installed-game filtering.",
    {
      installed_only: z
        .boolean()
        .optional()
        .default(false)
        .describe("Only return games detected in the local Steam installation."),
      sort_by: z
        .enum(["playtime", "name", "recent"])
        .optional()
        .default("playtime")
        .describe("Sort order: playtime, name, or recent."),
      limit: z
        .number()
        .optional()
        .default(50)
        .describe("Maximum number of games to return."),
    },
    async ({ installed_only, sort_by, limit }) => {
      const games = await api.getOwnedGames();
      if (games.length === 0) {
        return textResult(
          "The Steam library is empty or STEAM_API_KEY/STEAM_ID is not configured.\nSet STEAM_API_KEY and STEAM_ID, then retry.\n\nYou can also use list_installed_games to inspect locally installed games without a Steam API key."
        );
      }

      const installed = installed_only
        ? scanInstalledGames(steamPath)
        : null;
      const installedIds = installed
        ? new Set(installed.map((g) => g.appid))
        : null;

      const filtered = installed_only
        ? games.filter((g) => installedIds!.has(g.appid))
        : [...games];
      filtered.sort(LIBRARY_SORTERS[sort_by]);

      const slice = filtered.slice(0, limit);
      const lines = slice.map((g) => {
        const recent = g.playtime_2weeks > 0
          ? ` | last two weeks: ${formatWholeHours(g.playtime_2weeks)}h`
          : "";
        const installedTag = installedIds?.has(g.appid) ? " [installed]" : "";
        return `- **${g.name}** (AppID: ${g.appid})${installedTag}\n  Playtime: ${formatHours(g.playtime_forever)}h${recent}`;
      });

      return textResult(
        `Steam library (${games.length} games, showing ${slice.length}):\n\n${lines.join("\n")}`
      );
    }
  );

  server.tool(
    "find_game_for_session",
    "Recommend games from the user's Steam library for the available session length.",
    {
      available_minutes: z
        .number()
        .describe("Available play time in minutes."),
      prefer_installed: z
        .boolean()
        .optional()
        .default(true)
        .describe("Prefer games installed locally."),
      prefer_unplayed: z
        .boolean()
        .optional()
        .default(true)
        .describe("Prefer unplayed or lightly played games."),
      genre: z
        .string()
        .optional()
        .describe("Preferred genre, such as RPG, FPS, strategy, or casual."),
    },
    async ({ available_minutes, prefer_installed, prefer_unplayed }) => {
      const games = await api.getOwnedGames();
      if (games.length === 0) {
        return textResult("A Steam API key is required to read the game library.");
      }

      const installed = prefer_installed
        ? scanInstalledGames(steamPath)
        : [];
      const installedIds = new Set(installed.map((g) => g.appid));

      const candidates: GameSessionCandidate[] = games.map((game) => {
        // Use playtime as a rough session-length proxy; no HLTB data is available here.
        const hours = game.playtime_forever / 60;
        const isInstalled = installedIds.has(game.appid);

        return {
          appid: game.appid,
          name: game.name,
          playtime_minutes: game.playtime_forever,
          achievementProgress: 0,
          ratingPercent: 0,
          estimatedHours: Math.max(1, Math.round(hours * 0.6)),
          isInstalled,
        };
      });

      // Only enrich narrowed candidates to keep Steam API calls bounded.
      const topCandidates = candidates
        .filter((c) => c.estimatedHours <= available_minutes / 60 + 1)
        .sort((a, b) =>
          candidatePriorityScore(b, prefer_installed, prefer_unplayed) -
          candidatePriorityScore(a, prefer_installed, prefer_unplayed)
        )
        .slice(0, 10);

      for (const c of topCandidates) {
        if (c.playtime_minutes > 30) {
          const achievements = await api.getPlayerAchievements(c.appid);
          if (achievements.length > 0) {
            const earned = achievements.filter((a) => a.achieved === 1).length;
            c.achievementProgress = Math.round(
              (earned / achievements.length) * 100
            );
          }
        }

        const storeData = await api.getStoreAppDetails(c.appid);
        if (storeData && storeData.recommendations) {
          c.ratingPercent = storeData.recommendations.total > 0
            ? Math.round(
                (storeData.metacritic?.score || 75) * 0.7 +
                (storeData.recommendations.total > 10000 ? 25 : 10)
              )
            : 0;
        }
      }

      const scored = topCandidates.map((c) => ({
        ...c,
        score: recommendationScore(c, prefer_unplayed, available_minutes),
      }));

      scored.sort((a, b) => b.score - a.score);

      const lines = scored.slice(0, 5).map((c, idx) => {
        const installed = c.isInstalled ? "installed" : "not installed";
        const progress = c.playtime_minutes > 30
          ? `Achievements: ${c.achievementProgress}%`
          : "Not played yet";
        return `${idx + 1}. **${c.name}** (AppID: ${c.appid})
   - ${installed} | Estimated length: ${c.estimatedHours}h | ${progress}
   - Recommendation score: ${c.score}/100`;
      });

      const summary =
        scored.length > 0
          ? `Found ${scored.length} games that fit a ${available_minutes}-minute session:\n\n${lines.join("\n")}\n\nUse launch_game with the selected AppID to start a game.`
          : "No suitable games were found. Try relaxing filters or increasing the available time.";

      return textResult(summary);
    }
  );

  server.tool(
    "launch_game",
    "Launch a Steam game by AppID. The game must be owned by the configured Steam account.",
    {
      appid: z.number().describe("Steam AppID for an owned game."),
    },
    async ({ appid }) => {
      const games = await api.getOwnedGames();
      const owned = games.find((g) => g.appid === appid);
      if (!owned) {
        const ownedIds = games.map((g) => g.appid).join(", ");
        return textResult(
          `The configured account does not own AppID ${appid}, so it cannot be launched.\n\nOwned AppIDs: ${ownedIds.substring(0, 500)}`
        );
      }

      const result = await launchGame(appid, steamPath);
      return textResult(
        result.success
          ? `${result.message}\nAttempted to launch **${owned.name}** (AppID: ${appid}).`
          : result.message
      );
    }
  );

  server.tool(
    "get_game_details",
    "Get Steam store details for a game, including price, release data, platforms, genres, and review signals.",
    {
      appid: z.number().describe("Steam AppID."),
      country: z
        .string()
        .optional()
        .default("CN")
        .describe("Country code. Defaults to CN."),
      language: z
        .string()
        .optional()
        .default("en")
        .describe("Steam store language code. Defaults to en."),
    },
    async ({ appid, country, language }) => {
      const details = await api.getStoreAppDetails(appid, country, language);
      if (!details) {
        return textResult(
          `Unable to fetch details for AppID ${appid}. The AppID may not exist or may not be a store AppID. Use search_store first to find the correct AppID.`
        );
      }

      const priceInfo = formatStorePrice(details);
      const scoreRow = details.metacritic
        ? `| Score | Metacritic: ${details.metacritic.score} |`
        : "";
      const genres = joinDescriptions(details.genres);
      const platforms = formatPlatforms(details.platforms);
      const releaseDate = details.release_date?.date || UNKNOWN;
      const achievements = details.achievements?.total || 0;
      const recommendations = details.recommendations?.total || 0;

      return textResult(`
## ${details.name} (AppID: ${appid})

${details.short_description}

| Field | Details |
|------|------|
| Price | ${priceInfo} |
| Developers | ${details.developers?.join(", ") || UNKNOWN} |
| Publishers | ${details.publishers?.join(", ") || UNKNOWN} |
| Release date | ${releaseDate} |
| Platforms | ${platforms} |
| Genres | ${genres} |
| Achievements | ${achievements} |
| Recommendations | ${recommendations} |
${scoreRow}

[Steam store page](${steamStoreUrl(appid)})
      `.trim());
    }
  );

  server.tool(
    "get_achievements",
    "Read the configured user's achievement progress for a Steam game.",
    {
      appid: z.number().describe("Steam AppID."),
    },
    async ({ appid }) => {
      const achievements = await api.getPlayerAchievements(appid);
      if (achievements.length === 0) {
        return textResult("No achievement data is available for this game, or Steam API access is not configured.");
      }

      const earned = achievements.filter((a) => a.achieved === 1);
      const progress = Math.round((earned.length / achievements.length) * 100);

      const recentEarned = earned
        .filter((a) => a.unlocktime > 0)
        .sort((a, b) => b.unlocktime - a.unlocktime)
        .slice(0, 5);

      const lines = [
        `Achievement progress: ${earned.length}/${achievements.length} (${progress}%)`,
        "",
        recentEarned.length > 0 ? "**Recently unlocked:**" : "**No achievements unlocked yet.**",
        ...recentEarned.map((a) => {
          const d = new Date(a.unlocktime * 1000).toLocaleDateString("en-US");
          return `- ${a.name}: ${a.description} (${d})`;
        }),
        "",
        "---",
        "**Locked achievements (showing up to 5):**",
        ...achievements
          .filter((a) => a.achieved === 0)
          .slice(0, 5)
          .map((a) => `- ${a.name}: ${a.description}`),
      ];

      return textResult(lines.join("\n"));
    }
  );
}
