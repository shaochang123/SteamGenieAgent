// ============================================================================
// Asset / Inventory Tools — CS2 & Dota2 item valuation
// ============================================================================

import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { SteamApiClient } from "../steam/api.js";
import { SteamMarketService } from "../steam/market.js";

const CS2_APPID = 730;
const DOTA2_APPID = 570;

export function registerInventoryTools(
  server: McpServer,
  api: SteamApiClient,
  market: SteamMarketService
) {
  // ---- get_inventory ----
  server.tool(
    "get_inventory",
    "获取 CS2 或 Dota2 的物品库存，包含每个物品的市场最低价。",
    {
      steam_id: z
        .string()
        .optional()
        .describe("SteamID64。不填则使用环境变量 STEAM_ID"),
      game: z
        .enum(["cs2", "dota2"])
        .optional()
        .default("cs2")
        .describe("游戏：cs2 或 dota2"),
      include_prices: z
        .boolean()
        .optional()
        .default(true)
        .describe("是否查询市场价（会增加查询时间）"),
      limit: z
        .number()
        .optional()
        .default(100)
        .describe("返回物品数量上限"),
    },
    async ({ steam_id, game, include_prices, limit }) => {
      const sid = steam_id || "";
      if (!sid) {
        return {
          content: [
            {
              type: "text" as const,
              text: "需要提供 steam_id 或设置环境变量 STEAM_ID。",
            },
          ],
        };
      }

      const appid = game === "dota2" ? DOTA2_APPID : CS2_APPID;
      const items = await market.getInventory(sid, appid);

      if (items.length === 0) {
        return {
          content: [
            {
              type: "text" as const,
              text: `库存为空或无法访问（请确保 Steam 库存设置为公开）。`,
            },
          ],
        };
      }

      const limited = items.slice(0, limit);

      if (include_prices && limited.length > 0) {
        const pricePromises = limited.map((item) =>
          market.getItemPrice(item.marketHashName, appid)
        );
        const prices = await Promise.all(pricePromises);

        const lines = limited.map((item, i) => {
          const price = prices[i];
          const priceStr = price
            ? `${price.lowestPrice} (销量: ${price.volume})`
            : "暂无市场数据";
          const tradable = item.tradable ? "可交易" : "不可交易";
          const marketable = item.marketable ? "可出售" : "不可出售";
          return `- **${item.marketHashName}** x${item.amount}
  市场价: ${priceStr} | ${tradable} | ${marketable}`;
        });

        // Calculate total value estimate
        let totalEstimate = 0;
        for (const p of prices) {
          if (p) {
            const num = parseFloat(p.lowestPrice.replace(/[^0-9.]/g, ""));
            if (!isNaN(num)) totalEstimate += num;
          }
        }

        const gameName = game === "dota2" ? "Dota 2" : "CS2";
        return {
          content: [
            {
              type: "text" as const,
              text: `🎒 **${gameName} 库存** (${items.length} 件物品，展示前 ${limited.length} 件)
💰 总估值（前 ${limited.length} 件）：约 ¥${totalEstimate.toFixed(2)}

${lines.join("\n")}

💡 提示：设置 include_prices=false 可加快查询速度。`,
            },
          ],
        };
      }

      const lines = limited.map(
        (item) =>
          `- **${item.marketHashName}** x${item.amount} | ${item.tradable ? "可交易" : "不可交易"}`
      );

      const gameName = game === "dota2" ? "Dota 2" : "CS2";
      return {
        content: [
          {
            type: "text" as const,
            text: `🎒 **${gameName} 库存** (${items.length} 件物品，展示前 ${limited.length} 件)

${lines.join("\n")}`,
          },
        ],
      };
    }
  );

  // ---- get_item_price ----
  server.tool(
    "get_item_price",
    "查询 Steam 市场上某个物品的实时价格。",
    {
      market_hash_name: z
        .string()
        .describe("物品的 market_hash_name（从库存中获取）"),
      appid: z
        .number()
        .optional()
        .default(730)
        .describe("游戏 AppID（730=CS2, 570=Dota2）"),
    },
    async ({ market_hash_name, appid }) => {
      const price = await market.getItemPrice(market_hash_name, appid);

      if (!price) {
        return {
          content: [
            {
              type: "text" as const,
              text: `未找到物品 "${market_hash_name}" 的市场价格。请确认名称正确且物品可在市场上交易。`,
            },
          ],
        };
      }

      return {
        content: [
          {
            type: "text" as const,
            text: `💹 **${market_hash_name}** 市场行情

| 指标 | 数值 |
|------|------|
| 最低售价 | ${price.lowestPrice} |
| 中位售价 | ${price.medianPrice} |
| 成交量 | ${price.volume} |
| 更新时间 | ${price.lastUpdated} |

🔗 [市场页面](https://steamcommunity.com/market/listings/${appid}/${encodeURIComponent(market_hash_name)})`,
          },
        ],
      };
    }
  );

  // ---- get_inventory_summary ----
  server.tool(
    "get_inventory_summary",
    "获取 CS2/Dota2 库存摘要：总估值、最有价值物品、可交易物品统计。",
    {
      steam_id: z.string().optional().describe("SteamID64"),
      game: z
        .enum(["cs2", "dota2"])
        .optional()
        .default("cs2")
        .describe("游戏"),
    },
    async ({ steam_id, game }) => {
      const sid = steam_id || "";
      if (!sid) {
        return {
          content: [
            { type: "text" as const, text: "需要提供 steam_id。" },
          ],
        };
      }

      const appid = game === "dota2" ? DOTA2_APPID : CS2_APPID;
      const items = await market.getInventory(sid, appid);

      if (items.length === 0) {
        return {
          content: [
            { type: "text" as const, text: "库存为空或无法访问。" },
          ],
        };
      }

      const tradable = items.filter((i) => i.tradable);
      const marketable = items.filter((i) => i.marketable);

      // Get prices for marketable items (top 20 by value)
      const toPrice = marketable.slice(0, 20);
      const priceMap = await market.getMultipleItemPrices(
        toPrice.map((i) => ({ name: i.marketHashName, appid }))
      );

      let totalValue = 0;
      const valuedItems: Array<{ name: string; price: number; amount: number }> = [];

      for (const item of toPrice) {
        const price = priceMap.get(item.marketHashName);
        if (price) {
          const num = parseFloat(price.lowestPrice.replace(/[^0-9.]/g, ""));
          if (!isNaN(num)) {
            totalValue += num * item.amount;
            valuedItems.push({
              name: item.marketHashName,
              price: num,
              amount: item.amount,
            });
          }
        }
      }

      valuedItems.sort((a, b) => b.price * b.amount - a.price * a.amount);

      const lines = [
        `📊 **${game === "dota2" ? "Dota 2" : "CS2"} 库存摘要**`,
        "",
        `| 指标 | 数值 |`,
        `|------|------|`,
        `| 物品总数 | ${items.length} |`,
        `| 可交易 | ${tradable.length} |`,
        `| 可出售 | ${marketable.length} |`,
        `| 估值（前20件） | ¥${totalValue.toFixed(2)} |`,
        "",
        "**🏆 最有价值物品 (Top 5):**",
        ...valuedItems.slice(0, 5).map(
          (v, i) =>
            `${i + 1}. **${v.name}** — ¥${v.price.toFixed(2)} x${v.amount}`
        ),
      ];

      return {
        content: [{ type: "text" as const, text: lines.join("\n") }],
      };
    }
  );
}
