import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { SteamMarketService } from "../steam/market.js";
import { SteamApiClient } from "../steam/api.js";
import { formatCny, formatCnyCents, steamStoreUrl } from "./format.js";
import { textResult } from "./response.js";

export function registerMarketTools(
  server: McpServer,
  api: SteamApiClient,
  market: SteamMarketService
) {
  server.tool(
    "search_store",
    "Search the Steam store for games, DLC, or software by keyword.",
    {
      query: z.string().describe("Search keyword or game title."),
      country: z
        .string()
        .optional()
        .default("CN")
        .describe("Country code. Defaults to CN."),
    },
    async ({ query, country }) => {
      const results = await market.searchStore(query, country);

      if (results.length === 0) {
        return textResult(`No Steam store results found for "${query}".`);
      }

      const lines = results.slice(0, 20).map(
        (r) =>
          `- **${r.name}** (AppID: ${r.appid})\n  ${steamStoreUrl(r.appid)}`
      );

      return textResult(`Search results for "${query}" (${results.length} total):\n\n${lines.join("\n")}\n\nUse get_game_details with an AppID to inspect a specific game.`);
    }
  );

  server.tool(
    "get_deals",
    "List current Steam store deals and optionally filter by minimum discount.",
    {
      country: z
        .string()
        .optional()
        .default("CN")
        .describe("Country code. Defaults to CN."),
      min_discount: z
        .number()
        .optional()
        .default(0)
        .describe("Minimum discount percentage. For example, 50 means at least 50% off."),
      limit: z
        .number()
        .optional()
        .default(20)
        .describe("Maximum number of deals to return."),
    },
    async ({ country, min_discount, limit }) => {
      const deals = await market.getFeaturedDeals(country);

      const filtered = deals
        .filter((d) => d.discountPercent >= min_discount)
        .slice(0, limit);

      if (filtered.length === 0) {
        return textResult("No current Steam deals match the requested filters.");
      }

      const lines = filtered.map(
        (d) =>
          `- **${d.name}** - ${formatCny(d.finalPrice)} (original ${formatCny(d.originalPrice)} | ${d.discountPercent}% off)\n  ${steamStoreUrl(d.appid)}`
      );

      return textResult(`Steam deals (${filtered.length} games):\n\n${lines.join("\n")}`);
    }
  );

  server.tool(
    "monitor_price",
    "Check the current Steam price for a game and compare it with locally recorded price history.",
    {
      appid: z.number().describe("Steam AppID."),
      country: z
        .string()
        .optional()
        .default("CN")
        .describe("Country code. Defaults to CN."),
    },
    async ({ appid, country }) => {
      const details = await api.getStoreAppDetails(appid, country);
      const history = await market.getPriceHistory(appid);

      if (!details) {
        return textResult(`Unable to fetch information for AppID ${appid}.`);
      }

      const priceNow = details.price_overview;
      let analysis = "";

      if (priceNow) {
        if (details.is_free) {
          analysis = "This game is free.";
        } else if (priceNow.discount_percent > 0) {
          analysis = `Discount active: ${priceNow.discount_percent}% off
Current price: ${formatCnyCents(priceNow.final)}
Original price: ${formatCnyCents(priceNow.initial)}
Savings: ${formatCnyCents(priceNow.initial - priceNow.final)}`;

          if (priceNow.discount_percent >= 75) {
            analysis += "\n\nThis is a deep discount and may be worth buying if the game is on your wishlist.";
          }
        } else {
          analysis = `Current price: ${formatCnyCents(priceNow.final)}
No discount is active. Consider waiting for a sale if you are price-sensitive.`;
        }
      } else {
        analysis = "Price information is unavailable. The game may be unpriced or removed from the store.";
      }

      const historyStr =
        history.length > 0
          ? `\n\n**Recent price records:**\n${history
              .map((h) => `- ${h.date}: ${formatCny(h.price)}${h.discount ? " (discounted)" : ""}`)
              .join("\n")}`
          : "";

      return textResult(`**${details.name}** price monitor\n\n${analysis}${historyStr}\n\n[Steam store](${steamStoreUrl(appid)})`);
    }
  );

  server.tool(
    "check_price",
    "Quickly check current CN-region Steam prices for one or more games.",
    {
      appids: z
        .array(z.number())
        .describe("Steam AppID list, for example [730, 570, 1172470]."),
    },
    async ({ appids }) => {
      const results: string[] = [];

      for (const appid of appids) {
        const details = await api.getStoreAppDetails(appid, "CN");
        if (details) {
          const price = details.price_overview;
          const priceStr = details.is_free
            ? "Free"
            : price
              ? `${formatCnyCents(price.final)}${price.discount_percent > 0 ? ` (${price.discount_percent}% off)` : ""}`
              : "Unknown";
          results.push(
            `- **${details.name}**: ${priceStr}\n  ${steamStoreUrl(appid)}`
          );
        } else {
          results.push(`- AppID ${appid}: unable to fetch price information.`);
        }
      }

      return textResult(`Steam CN price check\n\n${results.join("\n")}`);
    }
  );
}
