import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { SteamMarketService } from "../steam/market.js";
import { formatCny, steamMarketUrl } from "./format.js";
import { textResult } from "./response.js";

const INVENTORY_GAMES = {
  cs2: { appid: 730, name: "CS2" },
  dota2: { appid: 570, name: "Dota 2" },
} as const;

type InventoryGame = keyof typeof INVENTORY_GAMES;

function gameMeta(game: InventoryGame) {
  return INVENTORY_GAMES[game] || INVENTORY_GAMES.cs2;
}

function parsePriceValue(lowestPrice: string): number {
  const value = parseFloat(lowestPrice.replace(/[^0-9.]/g, ""));
  return Number.isNaN(value) ? 0 : value;
}

function tradeState(item: { tradable: boolean; marketable: boolean }): string {
  return `${item.tradable ? "可交易" : "不可交易"} | ${item.marketable ? "可出售" : "不可出售"}`;
}

function priceText(price: Awaited<ReturnType<SteamMarketService["getItemPrice"]>>): string {
  return price ? `${price.lowestPrice} (销量: ${price.volume})` : "暂无市场数据";
}

export function registerInventoryTools(
  server: McpServer,
  market: SteamMarketService
) {
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
        return textResult("需要提供 steam_id 或设置环境变量 STEAM_ID。");
      }

      const { appid, name: gameName } = gameMeta(game);
      const items = await market.getInventory(sid, appid);

      if (items.length === 0) {
        return textResult(`库存为空或无法访问（请确保 Steam 库存设置为公开）。`);
      }

      const limited = items.slice(0, limit);

      if (include_prices && limited.length > 0) {
        const pricePromises = limited.map((item) =>
          market.getItemPrice(item.marketHashName, appid)
        );
        const prices = await Promise.all(pricePromises);

        const lines = limited.map((item, i) => {
          const price = prices[i];
          return `- **${item.marketHashName}** x${item.amount}
  市场价: ${priceText(price)} | ${tradeState(item)}`;
        });

        const totalEstimate = prices.reduce(
          (total, price) => total + (price ? parsePriceValue(price.lowestPrice) : 0),
          0
        );

        return textResult(`🎒 **${gameName} 库存** (${items.length} 件物品，展示前 ${limited.length} 件)
💰 总估值（前 ${limited.length} 件）：约 ${formatCny(totalEstimate)}

${lines.join("\n")}

💡 提示：设置 include_prices=false 可加快查询速度。`);
      }

      const lines = limited.map(
        (item) =>
          `- **${item.marketHashName}** x${item.amount} | ${tradeState(item)}`
      );

      return textResult(`🎒 **${gameName} 库存** (${items.length} 件物品，展示前 ${limited.length} 件)

${lines.join("\n")}`);
    }
  );

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
        return textResult(`未找到物品 "${market_hash_name}" 的市场价格。请确认名称正确且物品可在市场上交易。`);
      }

      return textResult(`💹 **${market_hash_name}** 市场行情

| 指标 | 数值 |
|------|------|
| 最低售价 | ${price.lowestPrice} |
| 中位售价 | ${price.medianPrice} |
| 成交量 | ${price.volume} |
| 更新时间 | ${price.lastUpdated} |

🔗 [市场页面](${steamMarketUrl(appid, market_hash_name)})`);
    }
  );

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
        return textResult("需要提供 steam_id。");
      }

      const { appid, name: gameName } = gameMeta(game);
      const items = await market.getInventory(sid, appid);

      if (items.length === 0) {
        return textResult("库存为空或无法访问。");
      }

      const tradable = items.filter((i) => i.tradable);
      const marketable = items.filter((i) => i.marketable);

      // Limit market calls so inventory summaries stay responsive.
      const toPrice = marketable.slice(0, 20);
      const priceMap = await market.getMultipleItemPrices(
        toPrice.map((i) => ({ name: i.marketHashName, appid }))
      );

      let totalValue = 0;
      const valuedItems: Array<{ name: string; price: number; amount: number }> = [];

      for (const item of toPrice) {
        const price = priceMap.get(item.marketHashName);
        if (price) {
          const num = parsePriceValue(price.lowestPrice);
          if (num > 0) {
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
        `📊 **${gameName} 库存摘要**`,
        "",
        `| 指标 | 数值 |`,
        `|------|------|`,
        `| 物品总数 | ${items.length} |`,
        `| 可交易 | ${tradable.length} |`,
        `| 可出售 | ${marketable.length} |`,
        `| 估值（前20件） | ${formatCny(totalValue)} |`,
        "",
        "**🏆 最有价值物品 (Top 5):**",
        ...valuedItems.slice(0, 5).map(
          (v, i) =>
            `${i + 1}. **${v.name}** — ${formatCny(v.price)} x${v.amount}`
        ),
      ];

      return textResult(lines.join("\n"));
    }
  );
}
