// ============================================================================
// Library Management Tools — game library, search, recommendations
// ============================================================================

import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { SteamApiClient } from "../steam/api.js";
import { SteamMarketService } from "../steam/market.js";
import { scanInstalledGames } from "../steam/vdf.js";
import { launchGame } from "../steam/launcher.js";
import type { GameSessionCandidate } from "../types.js";

export function registerLibraryTools(
  server: McpServer,
  api: SteamApiClient,
  market: SteamMarketService,
  steamPath: string
) {
  // ---- list_games ----
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
        return {
          content: [
            {
              type: "text" as const,
              text: "⚠️ 游戏库为空或未配置 Steam API Key。\n请设置环境变量 STEAM_API_KEY 和 STEAM_ID 后重试。\n\n你也可以使用 list_installed_games 查看本地已安装的游戏（无需 API Key）。",
            },
          ],
        };
      }

      const installed = installed_only
        ? scanInstalledGames(steamPath)
        : null;
      const installedIds = installed
        ? new Set(installed.map((g) => g.appid))
        : null;

      let filtered = installed_only
        ? games.filter((g) => installedIds!.has(g.appid))
        : games;

      switch (sort_by) {
        case "playtime":
          filtered.sort((a, b) => b.playtime_forever - a.playtime_forever);
          break;
        case "name":
          filtered.sort((a, b) => a.name.localeCompare(b.name, "zh-CN"));
          break;
        case "recent":
          filtered.sort((a, b) => b.playtime_2weeks - a.playtime_2weeks);
          break;
      }

      const slice = filtered.slice(0, limit);
      const lines = slice.map((g) => {
        const hours = Math.round((g.playtime_forever / 60) * 10) / 10;
        const recent = g.playtime_2weeks > 0
          ? ` | 近两周 ${Math.round(g.playtime_2weeks / 60)}h`
          : "";
        const installedTag = installedIds?.has(g.appid) ? " 📀" : "";
        return `- **${g.name}** (AppID: ${g.appid})${installedTag}\n  时长: ${hours}h${recent}`;
      });

      return {
        content: [
          {
            type: "text" as const,
            text: `📚 游戏库 (共 ${games.length} 款，显示前 ${slice.length} 款)：\n\n${lines.join("\n")}`,
          },
        ],
      };
    }
  );

  // ---- find_game_for_session ----
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
    async ({ available_minutes, prefer_installed, prefer_unplayed, genre }) => {
      const games = await api.getOwnedGames();
      if (games.length === 0) {
        return {
          content: [
            {
              type: "text" as const,
              text: "需要配置 Steam API Key 才能获取游戏库数据。",
            },
          ],
        };
      }

      const installed = prefer_installed
        ? scanInstalledGames(steamPath)
        : [];
      const installedIds = new Set(installed.map((g) => g.appid));

      const candidates: GameSessionCandidate[] = [];

      for (const game of games) {
        // estimate hours from howlongtobeat (rough heuristic based on playtime)
        const hours = game.playtime_forever / 60;
        const isInstalled = installedIds.has(game.appid);

        // Score calculation later — gather data first
        candidates.push({
          appid: game.appid,
          name: game.name,
          playtime_minutes: game.playtime_forever,
          achievementProgress: 0,
          positiveRatings: 0,
          totalRatings: 0,
          ratingPercent: 0,
          estimatedHours: Math.max(1, Math.round(hours * 0.6)),
          isInstalled,
        });
      }

      // Enrich top candidates with store data for ratings
      const topCandidates = candidates
        .filter((c) => c.estimatedHours <= available_minutes / 60 + 1) // allow a bit over
        .sort((a, b) => {
          let scoreA = 0;
          let scoreB = 0;
          if (prefer_installed) {
            if (a.isInstalled) scoreA += 10;
            if (b.isInstalled) scoreB += 10;
          }
          if (prefer_unplayed) {
            if (a.playtime_minutes < 30) scoreA += 5;
            if (b.playtime_minutes < 30) scoreB += 5;
          }
          return scoreB - scoreA;
        })
        .slice(0, 10);

      // Get achievement data for these candidates
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

        // Get store ratings
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

      // Final scoring
      const scored = topCandidates.map((c) => {
        let score = 0;
        if (c.isInstalled) score += 30;
        if (prefer_unplayed && c.achievementProgress < 20) score += 25;
        if (c.ratingPercent > 0) score += Math.round(c.ratingPercent / 5);
        const timeFit = c.estimatedHours <= available_minutes / 60 ? 20 : 0;
        score += timeFit;
        return { ...c, score };
      });

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

      return {
        content: [{ type: "text" as const, text: summary }],
      };
    }
  );

  // ---- launch_game ----
  server.tool(
    "launch_game",
    "通过 Steam 启动一款游戏。传入游戏的 AppID 即可启动。",
    {
      appid: z.number().describe("Steam 游戏的 AppID"),
    },
    async ({ appid }) => {
      const result = await launchGame(appid);
      return {
        content: [
          {
            type: "text" as const,
            text: result.success
              ? `🚀 ${result.message}\n已尝试启动 AppID: ${appid}`
              : `❌ ${result.message}`,
          },
        ],
      };
    }
  );

  // ---- get_game_details ----
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
        return {
          content: [
            {
              type: "text" as const,
              text: `无法获取 AppID ${appid} 的游戏详情。请检查 AppID 是否正确。`,
            },
          ],
        };
      }

      const priceInfo = details.price_overview
        ? `${details.is_free ? "免费" : `¥${(details.price_overview.final / 100).toFixed(2)}`}${details.price_overview.discount_percent > 0 ? ` (折扣 ${details.price_overview.discount_percent}%)` : ""}`
        : "价格未知";

      const meta = details.metacritic
        ? `Metacritic: ${details.metacritic.score}`
        : "";

      const genres = details.genres.map((g) => g.description).join(", ");
      const platforms = [
        details.platforms.windows ? "Windows" : "",
        details.platforms.mac ? "macOS" : "",
        details.platforms.linux ? "Linux" : "",
      ]
        .filter(Boolean)
        .join(", ");

      return {
        content: [
          {
            type: "text" as const,
            text: `
## ${details.name} (AppID: ${appid})

${details.short_description}

| 属性 | 详情 |
|------|------|
| 价格 | ${priceInfo} |
| 开发商 | ${details.developers?.join(", ") || "未知"} |
| 发行商 | ${details.publishers?.join(", ") || "未知"} |
| 发行日期 | ${details.release_date.date} |
| 平台 | ${platforms} |
| 类型 | ${genres} |
| 成就 | ${details.achievements?.total || 0} 个 |
| 评测 | ${details.recommendations?.total || 0} 条推荐 |
| ${meta ? "评分" : ""} | ${meta} |

🔗 [Steam 商店页面](https://store.steampowered.com/app/${appid}/)
            `.trim(),
          },
        ],
      };
    }
  );

  // ---- get_achievements ----
  server.tool(
    "get_achievements",
    "查询你在某款游戏中的成就进度。",
    {
      appid: z.number().describe("Steam 游戏的 AppID"),
    },
    async ({ appid }) => {
      const achievements = await api.getPlayerAchievements(appid);
      if (achievements.length === 0) {
        return {
          content: [
            {
              type: "text" as const,
              text: `该游戏没有成就数据，或需要配置 Steam API Key。`,
            },
          ],
        };
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

      return {
        content: [{ type: "text" as const, text: lines.join("\n") }],
      };
    }
  );
}
