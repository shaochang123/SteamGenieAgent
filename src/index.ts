#!/usr/bin/env node

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { SteamApiClient } from "./steam/api.js";
import { SteamMarketService } from "./steam/market.js";
import { detectSteamPath } from "./steam/vdf.js";
import { registerLibraryTools } from "./tools/library.js";
import { registerInventoryTools } from "./tools/inventory.js";
import { registerMarketTools } from "./tools/market.js";
import { registerLocalTools } from "./tools/local.js";
import { registerSocialTools } from "./tools/social.js";

function parseArgs(): {
  apiKey: string;
  steamId: string;
  steamPath: string;
  currency: string;
} {
  const args = process.argv.slice(2);
  const getArg = (name: string): string => {
    const idx = args.findIndex(
      (a) => a === `--${name}` || a.startsWith(`--${name}=`)
    );
    if (idx === -1) return "";
    if (args[idx].includes("=")) return args[idx].split("=")[1];
    return args[idx + 1] || "";
  };
  const readOption = (envName: string, names: string[], fallback = ""): string =>
    process.env[envName] || names.map(getArg).find(Boolean) || fallback;

  return {
    apiKey: readOption("STEAM_API_KEY", ["api-key", "apiKey"]),
    steamId: readOption("STEAM_ID", ["steam-id", "steamId"]),
    steamPath: readOption("STEAM_PATH", ["steam-path", "steamPath"]) || detectSteamPath(),
    currency: readOption("STEAM_CURRENCY", ["currency"], "CNY"),
  };
}

async function main() {
  const config = parseArgs();

  const api = new SteamApiClient(config.apiKey, config.steamId);
  const market = new SteamMarketService(config.currency);

  const server = new McpServer({
    name: "steam-genie-mcp",
    version: "1.0.0",
  });

  registerLibraryTools(server, api, config.steamPath);
  registerInventoryTools(server, market);
  registerMarketTools(server, api, market);
  registerLocalTools(server, config.steamPath);
  registerSocialTools(server, api);

  const transport = new StdioServerTransport();
  await server.connect(transport);

  // Log startup info to stderr so stdout remains valid MCP protocol traffic.
  console.error("Steam Genie MCP Server started");
  console.error(`   Steam Path: ${config.steamPath}`);
  console.error(`   API Key: ${config.apiKey ? "configured" : "not set (some features limited)"}`);
  console.error(`   Steam ID: ${config.steamId || "not set"}`);
  console.error(`   Currency: ${config.currency}`);
}

main().catch((err) => {
  const msg = err instanceof Error ? err.message : String(err);
  console.error("Failed to start Steam Genie MCP:", msg);
  process.exit(1);
});
