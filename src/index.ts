#!/usr/bin/env node
// ============================================================================
// Steam Genie MCP Server
// AI-powered Steam game management via Model Context Protocol
// ============================================================================

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

// ---- Parse CLI arguments ----
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

  return {
    apiKey:
      process.env.STEAM_API_KEY || getArg("api-key") || getArg("apiKey") || "",
    steamId:
      process.env.STEAM_ID || getArg("steam-id") || getArg("steamId") || "",
    steamPath:
      process.env.STEAM_PATH ||
      getArg("steam-path") ||
      getArg("steamPath") ||
      detectSteamPath(),
    currency: process.env.STEAM_CURRENCY || getArg("currency") || "CNY",
  };
}

// ---- Main ----
async function main() {
  const config = parseArgs();

  // Initialize services
  const api = new SteamApiClient(config.apiKey, config.steamId);
  const market = new SteamMarketService(config.currency);

  // Create MCP server
  const server = new McpServer({
    name: "steam-genie-mcp",
    version: "1.0.0",
  });

  // Register all tool groups
  registerLibraryTools(server, api, market, config.steamPath);
  registerInventoryTools(server, api, market);
  registerMarketTools(server, api, market);
  registerLocalTools(server, config.steamPath);
  registerSocialTools(server, api);

  // Start the stdio transport
  const transport = new StdioServerTransport();
  await server.connect(transport);

  // Log startup info to stderr (won't interfere with MCP protocol on stdout)
  console.error(" Steam Genie MCP Server started");
  console.error(`   Steam Path: ${config.steamPath}`);
  console.error(`   API Key: ${config.apiKey ? "✓ configured" : "✗ not set (some features limited)"}`);
  console.error(`   Steam ID: ${config.steamId || "✗ not set"}`);
  console.error(`   Currency: ${config.currency}`);
}

main().catch((err) => {
  const msg = err instanceof Error ? err.message : String(err);
  console.error("Failed to start Steam Genie MCP:", msg);
  process.exit(1);
});
