// ============================================================================
// Market Intelligence Tools — price tracking, deals, search
// ============================================================================

import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { SteamMarketService } from "../steam/market.js";
import { SteamApiClient } from "../steam/api.js";

export function registerMarketTools(
  server: McpServer,
  api: SteamApiClient,
  market: SteamMarketService
) {
  // ---- search_store ----
  server.tool(
    "search_store",
    "搜索 Steam 商店中的游戏、DLC 或软件。",
    {
      query: z.string().describe("搜索关键词"),
      country: z
        .string()
        .optional()
        .default("CN")
        .describe("国家代码，默认 CN"),
    },
    async ({ query, country }) => {
      const results = await market.searchStore(query, country);

      if (results.length === 0) {
        return {
          content: [
            { type: "text" as const, text: `未找到与 "${query}" 相关的结果。` },
          ],
        };
      }

      const lines = results.slice(0, 20).map(
        (r) =>
          `- **${r.name}** (AppID: ${r.appid})\n  🔗 https://store.steampowered.com/app/${r.appid}/`
      );

      return {
        content: [
          {
            type: "text" as const,
            text: `🔍 搜索 "${query}" 的结果 (${results.length} 个)：

${lines.join("\n")}

💡 使用 get_game_details 查看具体游戏的详细信息。`,
          },
        ],
      };
    }
  );

  // ---- get_deals ----
  server.tool(
    "get_deals",
    "获取 Steam 当前打折促销的游戏列表。",
    {
      country: z
        .string()
        .optional()
        .default("CN")
        .describe("国家代码"),
      min_discount: z
        .number()
        .optional()
        .default(0)
        .describe("最低折扣百分比，如 50 表示至少半价"),
      limit: z
        .number()
        .optional()
        .default(20)
        .describe("返回数量"),
    },
    async ({ country, min_discount, limit }) => {
      const deals = await market.getFeaturedDeals(country);

      const filtered = deals
        .filter((d) => d.discountPercent >= min_discount)
        .slice(0, limit);

      if (filtered.length === 0) {
        return {
          content: [
            {
              type: "text" as const,
              text: "当前没有符合条件的促销活动。",
            },
          ],
        };
      }

      const lines = filtered.map(
        (d) =>
          `- **${d.name}** — ¥${d.finalPrice.toFixed(2)} (原价 ¥${d.originalPrice.toFixed(2)} | ${d.discountPercent}% OFF)\n  🔗 https://store.steampowered.com/app/${d.appid}/`
      );

      return {
        content: [
          {
            type: "text" as const,
            text: `🛒 **Steam 特惠** (${filtered.length} 款折扣游戏)

${lines.join("\n")}`,
          },
        ],
      };
    }
  );

  // ---- monitor_price ----
  server.tool(
    "monitor_price",
    "查看一款游戏的当前价格，并与历史价格对比，判断是否处于史低。",
    {
      appid: z.number().describe("Steam 游戏的 AppID"),
      country: z
        .string()
        .optional()
        .default("CN")
        .describe("国家代码"),
    },
    async ({ appid, country }) => {
      const details = await api.getStoreAppDetails(appid, country);
      const history = await market.getPriceHistory(appid);

      if (!details) {
        return {
          content: [
            { type: "text" as const, text: `无法获取 AppID ${appid} 的信息。` },
          ],
        };
      }

      const priceNow = details.price_overview;
      let analysis = "";

      if (priceNow) {
        if (details.is_free) {
          analysis = "🆓 此游戏免费！";
        } else if (priceNow.discount_percent > 0) {
          analysis = `🔥 正在打折！折扣 ${priceNow.discount_percent}%
当前价格：¥${(priceNow.final / 100).toFixed(2)}
原价：¥${(priceNow.initial / 100).toFixed(2)}
节省：¥${((priceNow.initial - priceNow.final) / 100).toFixed(2)}`;

          if (priceNow.discount_percent >= 75) {
            analysis += "\n\n🏆 **这是大折扣！可能是史低价格，建议入手！**";
          }
        } else {
          analysis = `当前价格：¥${(priceNow.final / 100).toFixed(2)}
⚠️ 目前没有折扣。建议加入愿望单等待促销。`;
        }
      } else {
        analysis = "价格信息不可用。此游戏可能尚未定价或已下架。";
      }

      const historyStr =
        history.length > 0
          ? `\n\n**近期价格记录：**\n${history
              .map((h) => `- ${h.date}: ¥${h.price.toFixed(2)}${h.discount ? " (折扣)" : ""}`)
              .join("\n")}`
          : "";

      return {
        content: [
          {
            type: "text" as const,
            text: `📈 **${details.name}** 价格监测

${analysis}${historyStr}

🔗 [Steam 商店](https://store.steampowered.com/app/${appid}/)`,
          },
        ],
      };
    }
  );

  // ---- check_price ----
  server.tool(
    "check_price",
    "快速查看一个或多个 Steam 游戏的中国区当前价格。",
    {
      appids: z
        .array(z.number())
        .describe("游戏 AppID 列表，如 [730, 570, 1172470]"),
    },
    async ({ appids }) => {
      const results: string[] = [];

      for (const appid of appids) {
        const details = await api.getStoreAppDetails(appid, "CN");
        if (details) {
          const price = details.price_overview;
          const priceStr = details.is_free
            ? "免费 🆓"
            : price
              ? `¥${(price.final / 100).toFixed(2)}${price.discount_percent > 0 ? ` (${price.discount_percent}% OFF)` : ""}`
              : "未知";
          results.push(
            `- **${details.name}**: ${priceStr}\n  🔗 https://store.steampowered.com/app/${appid}/`
          );
        } else {
          results.push(`- AppID ${appid}: 无法获取信息`);
        }
      }

      return {
        content: [
          {
            type: "text" as const,
            text: `💰 **Steam 国区价格查询**

${results.join("\n")}`,
          },
        ],
      };
    }
  );
}
