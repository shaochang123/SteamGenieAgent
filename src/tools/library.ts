import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { SteamApiClient } from "../steam/api.js";
import { scanInstalledGames } from "../steam/vdf.js";
import { launchGame } from "../steam/launcher.js";
import type { GameSessionCandidate, LibraryGame, StoreAppDetails } from "../types.js";
import { formatCnyCents, formatHours, formatWholeHours, steamStoreUrl } from "./format.js";
import { textResult } from "./response.js";

const UNKNOWN = "未知";
const LIBRARY_SORTERS: Record<string, (a: LibraryGame, b: LibraryGame) => number> = {
  playtime: (a, b) => b.playtime_forever - a.playtime_forever,
  name: (a, b) => a.name.localeCompare(b.name, "zh-CN"),
  recent: (a, b) => b.playtime_2weeks - a.playtime_2weeks,
};

function formatStorePrice(details: StoreAppDetails): string {
  if (!details.price_overview) return "价格未知";
  const price = details.is_free
    ? "免费"
    : formatCnyCents(details.price_overview.final);
  const discount = details.price_overview.discount_percent;
  return discount > 0 ? `${price} (折扣 ${discount}%)` : price;
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
    "列出你的 Steam 游戏库，包含游戏时长、评分等信息。可筛选已安装的游戏。",
    {
      installed_only: z
        .boolean()
        .optional()
        .default(false)
        .describe("仅显示已安装的游戏"),
      sort_by: z
        .enum(["playtime", "name", "recent"])
        .optional()
        .default("playtime")
        .describe("排序方式：playtime=游戏时长, name=名称, recent=最近游玩"),
      limit: z
        .number()
        .optional()
        .default(50)
        .describe("返回数量上限"),
    },
    async ({ installed_only, sort_by, limit }) => {
      const games = await api.getOwnedGames();
      if (games.length === 0) {
        return textResult(
          "⚠️ 游戏库为空或未配置 Steam API Key。\n请设置环境变量 STEAM_API_KEY 和 STEAM_ID 后重试。\n\n你也可以使用 list_installed_games 查看本地已安装的游戏（无需 API Key）。"
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
          ? ` | 近两周 ${formatWholeHours(g.playtime_2weeks)}h`
          : "";
        const installedTag = installedIds?.has(g.appid) ? " 📀" : "";
        return `- **${g.name}** (AppID: ${g.appid})${installedTag}\n  时长: ${formatHours(g.playtime_forever)}h${recent}`;
      });

      return textResult(
        `📚 游戏库 (共 ${games.length} 款，显示前 ${slice.length} 款)：\n\n${lines.join("\n")}`
      );
    }
  );

  server.tool(
    "find_game_for_session",
    "根据你的空闲时长，从游戏库中推荐最适合的游戏。综合考虑好评率、游戏时长、是否通关等因素。",
    {
      available_minutes: z
        .number()
        .describe("你有多少分钟的空闲时间"),
      prefer_installed: z
        .boolean()
        .optional()
        .default(true)
        .describe("优先推荐已安装的游戏"),
      prefer_unplayed: z
        .boolean()
        .optional()
        .default(true)
        .describe("优先推荐未通关/未玩过的游戏"),
      genre: z
        .string()
        .optional()
        .describe("偏好的游戏类型，如 RPG、FPS、策略、休闲"),
    },
    async ({ available_minutes, prefer_installed, prefer_unplayed }) => {
      const games = await api.getOwnedGames();
      if (games.length === 0) {
        return textResult("需要配置 Steam API Key 才能获取游戏库数据。");
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
        .filter((c) => c.estimatedHours <= available_minutes / 60 + 1) // allow a bit over
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
        const icon = idx === 0 ? "⭐" : idx === 1 ? "🌟" : "🎮";
        const installed = c.isInstalled ? "已安装" : "未安装";
        const progress = c.playtime_minutes > 30
          ? `成就 ${c.achievementProgress}%`
          : "尚未游玩";
        return `${icon} **${c.name}** (AppID: ${c.appid})
   - ${installed} | 预估通关: ${c.estimatedHours}h | ${progress}
   - 综合评分: ${c.score}/100`;
      });

      const summary =
        scored.length > 0
          ? `🎯 为你找到 ${scored.length} 款适合 ${available_minutes} 分钟的游戏：\n\n${lines.join("\n")}\n\n💡 使用 launch_game 启动你选中的游戏。`
          : `未找到合适游戏。尝试放宽筛选条件或增加空闲时长。`;

      return textResult(summary);
    }
  );

  server.tool(
    "launch_game",
    "通过 Steam 启动一款游戏。传入游戏的 AppID 即可启动。只能启动你已拥有的游戏。",
    {
      appid: z.number().describe("Steam 游戏的 AppID（必须是已拥有的游戏）"),
    },
    async ({ appid }) => {
      const games = await api.getOwnedGames();
      const owned = games.find((g) => g.appid === appid);
      if (!owned) {
        const ownedIds = games.map((g) => g.appid).join(", ");
        return textResult(
          `❌ 你没有拥有 AppID ${appid} 的游戏，无法启动。\n\n你拥有的游戏 AppID: ${ownedIds.substring(0, 500)}`
        );
      }

      const result = await launchGame(appid, steamPath);
      return textResult(
        result.success
          ? `🚀 ${result.message}\n已尝试启动 **${owned.name}** (AppID: ${appid})`
          : `❌ ${result.message}`
      );
    }
  );

  server.tool(
    "get_game_details",
    "获取 Steam 游戏的详细信息，包括价格、评价、描述、配置要求等。",
    {
      appid: z.number().describe("Steam 游戏的 AppID"),
      country: z
        .string()
        .optional()
        .default("CN")
        .describe("国家代码，默认 CN(中国)"),
      language: z
        .string()
        .optional()
        .default("zh-CN")
        .describe("语言代码，默认 zh-CN"),
    },
    async ({ appid, country, language }) => {
      const details = await api.getStoreAppDetails(appid, country, language);
      if (!details) {
        return textResult(
          `无法获取 AppID ${appid} 的游戏详情。这个 AppID 可能不存在或不是商店 AppID。请先用 search_store 搜索游戏名，拿到正确 AppID 后再调用 get_game_details。`
        );
      }

      const priceInfo = formatStorePrice(details);
      const scoreRow = details.metacritic
        ? `| 评分 | Metacritic: ${details.metacritic.score} |`
        : "";
      const genres = joinDescriptions(details.genres);
      const platforms = formatPlatforms(details.platforms);
      const releaseDate = details.release_date?.date || UNKNOWN;
      const achievements = details.achievements?.total || 0;
      const recommendations = details.recommendations?.total || 0;

      return textResult(`
## ${details.name} (AppID: ${appid})

${details.short_description}

| 属性 | 详情 |
|------|------|
| 价格 | ${priceInfo} |
| 开发商 | ${details.developers?.join(", ") || "未知"} |
| 发行商 | ${details.publishers?.join(", ") || "未知"} |
| 发行日期 | ${releaseDate} |
| 平台 | ${platforms} |
| 类型 | ${genres} |
| 成就 | ${achievements} 个 |
| 评测 | ${recommendations} 条推荐 |
${scoreRow}

🔗 [Steam 商店页面](${steamStoreUrl(appid)})
      `.trim());
    }
  );

  server.tool(
    "get_achievements",
    "查询你在某款游戏中的成就进度。",
    {
      appid: z.number().describe("Steam 游戏的 AppID"),
    },
    async ({ appid }) => {
      const achievements = await api.getPlayerAchievements(appid);
      if (achievements.length === 0) {
        return textResult(`该游戏没有成就数据，或需要配置 Steam API Key。`);
      }

      const earned = achievements.filter((a) => a.achieved === 1);
      const progress = Math.round((earned.length / achievements.length) * 100);

      const recentEarned = earned
        .filter((a) => a.unlocktime > 0)
        .sort((a, b) => b.unlocktime - a.unlocktime)
        .slice(0, 5);

      const lines = [
        `🏆 成就进度: ${earned.length}/${achievements.length} (${progress}%)`,
        "",
        recentEarned.length > 0 ? "**最近解锁：**" : "**尚未解锁成就**",
        ...recentEarned.map((a) => {
          const d = new Date(a.unlocktime * 1000).toLocaleDateString("zh-CN");
          return `- ${a.name}: ${a.description} (${d})`;
        }),
        "",
        "---",
        "**未解锁（随机展示 5 个）：**",
        ...achievements
          .filter((a) => a.achieved === 0)
          .slice(0, 5)
          .map((a) => `- ${a.name}: ${a.description}`),
      ];

      return textResult(lines.join("\n"));
    }
  );
}
