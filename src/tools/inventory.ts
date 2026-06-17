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
  return `${item.tradable ? "tradable" : "not tradable"} | ${item.marketable ? "marketable" : "not marketable"}`;
}

function priceText(price: Awaited<ReturnType<SteamMarketService["getItemPrice"]>>): string {
  return price ? `${price.lowestPrice} (volume: ${price.volume})` : "No market data";
}

export function registerInventoryTools(
  server: McpServer,
  market: SteamMarketService
) {
  server.tool(
    "get_inventory",
    "Read a CS2 or Dota 2 inventory and optionally include Steam Community Market prices.",
    {
      steam_id: z
        .string()
        .optional()
        .describe("SteamID64. If omitted, the caller should provide the configured user's Steam ID."),
      game: z
        .enum(["cs2", "dota2"])
        .optional()
        .default("cs2")
        .describe("Inventory game: cs2 or dota2."),
      include_prices: z
        .boolean()
        .optional()
        .default(true)
        .describe("Whether to fetch market prices. Price lookups make the request slower."),
      limit: z
        .number()
        .optional()
        .default(100)
        .describe("Maximum number of inventory items to return."),
    },
    async ({ steam_id, game, include_prices, limit }) => {
      const sid = steam_id || "";
      if (!sid) {
        return textResult("steam_id is required.");
      }

      const { appid, name: gameName } = gameMeta(game);
      const items = await market.getInventory(sid, appid);

      if (items.length === 0) {
        return textResult("The inventory is empty or inaccessible. Verify that the Steam inventory is public.");
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
  Market price: ${priceText(price)} | ${tradeState(item)}`;
        });

        const totalEstimate = prices.reduce(
          (total, price) => total + (price ? parsePriceValue(price.lowestPrice) : 0),
          0
        );

        return textResult(`**${gameName} inventory** (${items.length} items, showing ${limited.length})
Estimated value for shown items: about ${formatCny(totalEstimate)}

${lines.join("\n")}

Tip: set include_prices=false for faster inventory listing.`);
      }

      const lines = limited.map(
        (item) =>
          `- **${item.marketHashName}** x${item.amount} | ${tradeState(item)}`
      );

      return textResult(`**${gameName} inventory** (${items.length} items, showing ${limited.length})\n\n${lines.join("\n")}`);
    }
  );

  server.tool(
    "get_item_price",
    "Fetch the current Steam Community Market price for an item.",
    {
      market_hash_name: z
        .string()
        .describe("Item market_hash_name from the inventory or Steam market."),
      appid: z
        .number()
        .optional()
        .default(730)
        .describe("Game AppID. 730=CS2, 570=Dota 2."),
    },
    async ({ market_hash_name, appid }) => {
      const price = await market.getItemPrice(market_hash_name, appid);

      if (!price) {
        return textResult(`No market price found for "${market_hash_name}". Verify that the item name is correct and marketable.`);
      }

      return textResult(`**${market_hash_name}** market price

| Metric | Value |
|------|------|
| Lowest listing | ${price.lowestPrice} |
| Median sale price | ${price.medianPrice} |
| Volume | ${price.volume} |
| Last updated | ${price.lastUpdated} |

[Market page](${steamMarketUrl(appid, market_hash_name)})`);
    }
  );

  server.tool(
    "get_inventory_summary",
    "Summarize a CS2 or Dota 2 inventory with counts, marketability, and top-value items.",
    {
      steam_id: z.string().optional().describe("SteamID64."),
      game: z
        .enum(["cs2", "dota2"])
        .optional()
        .default("cs2")
        .describe("Inventory game: cs2 or dota2."),
    },
    async ({ steam_id, game }) => {
      const sid = steam_id || "";
      if (!sid) {
        return textResult("steam_id is required.");
      }

      const { appid, name: gameName } = gameMeta(game);
      const items = await market.getInventory(sid, appid);

      if (items.length === 0) {
        return textResult("The inventory is empty or inaccessible.");
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
        `**${gameName} inventory summary**`,
        "",
        `| Metric | Value |`,
        `|------|------|`,
        `| Total items | ${items.length} |`,
        `| Tradable items | ${tradable.length} |`,
        `| Marketable items | ${marketable.length} |`,
        `| Estimated value (first 20 marketable items) | ${formatCny(totalValue)} |`,
        "",
        "**Most valuable items (top 5):**",
        ...valuedItems.slice(0, 5).map(
          (v, i) =>
            `${i + 1}. **${v.name}** - ${formatCny(v.price)} x${v.amount}`
        ),
      ];

      return textResult(lines.join("\n"));
    }
  );
}
