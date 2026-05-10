# 🧞‍♂️ Steam-Genie-MCP

> **Turn AI into your ultimate Steam gaming assistant.**
> Built on the Model Context Protocol (MCP), connecting your AI assistants (Claude Desktop, Cursor, Windsurf) directly with the Steam ecosystem.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![MCP Version: 1.0](https://img.shields.io/badge/MCP-Protocol--v1.0-blue)](https://modelcontextprotocol.io)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](http://makeapullrequest.com)

**English** | [中文说明](./README_CN.md)

---

# 🌟 Why Steam-Genie-MCP?

**Steam-Genie-MCP** offers the following features:

* **Offline-first**: A built-in VDF parser reads local Steam files directly, enabling instant access to installed games and screenshots without internet access.
* **Region-focused**: Deep optimization for the Chinese Steam region (CNY), with support for 40+ currencies.
* **End-to-end workflow**: From game recommendations → inventory valuation → market comparison → one-click launching.

**Tech Stack**: TypeScript + [MCP SDK](https://github.com/modelcontextprotocol/typescript-sdk) + Zod validation + custom-built VDF parsing engine. Native support for Claude Code, Claude Desktop, Cursor, and Windsurf.

## 🛠️ Core Features

| Feature                       | Description                            | Example Use Case                                                                                          |
| ----------------------------- | -------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| **🕹️ Smart Game Control**    | Intelligent game recommendation engine | “I have 2 free hours this afternoon. Pick the highest-rated unfinished game in my library and launch it.” |
| **💰 Inventory Expert**       | CS2 / Dota2 inventory valuation        | “How much is my CS2 inventory worth? Which items increased in value?”                                     |
| **📈 Market Intelligence**    | Steam CN-region price monitoring       | “Track the historical lowest price of Black Myth: Wukong.”                                                |
| **📂 Deep Local Integration** | Offline VDF parser                     | “List all my installed games and screenshots without connecting online.”                                  |
| **🤝 Social Assistant**       | Friend management + invite generation  | “See who’s online, find a co-op game everyone owns, and generate an invite message.”                      |

---

# 🚀 Quick Start

## Prerequisites

* Install [Node.js](https://nodejs.org/) (v18+)
* (Optional) A [Steam Web API Key](https://steamcommunity.com/dev/apikey) — required for online features such as library sync, friends, and achievements
* Local VDF parsing works **without an API key**

## 1. Install & Run

```bash
npx steam-genie-mcp --api-key YOUR_STEAM_KEY --steam-id YOUR_STEAM_ID --steam-path "D:\\steam"
```

| Parameter      | Required    | Description                                                                             |
| -------------- | ----------- | --------------------------------------------------------------------------------------- |
| `--api-key`    | Recommended | Steam Web API Key. Without it, only online features are disabled                        |
| `--steam-id`   | Recommended | SteamID64. Without it, inventory/friend features are unavailable                        |
| `--steam-path` | No          | Steam installation directory. **Auto-detected if omitted** (Windows/macOS/Linux)        |
| `--currency`   | No          | Currency for market/store prices. Default: CNY. Supports USD/EUR/JPY and 40+ currencies |

The `currency` parameter controls:

* The display currency for **market lowest prices** of inventory items
* Store **price queries** (`check_price`, `monitor_price`, `get_deals`)
* Currency units returned by Steam Market APIs (`USD` → `$`, `CNY` → `¥`)

---

## 2. Configure Your AI Assistant

### Claude Code (`.mcp.json` in project root)

```json
{
  "mcpServers": {
    "steam-genie": {
      "command": "npx",
      "args": [
        "steam-genie-mcp",
        "--api-key", "YOUR_STEAM_API_KEY",
        "--steam-id", "YOUR_64BIT_STEAM_ID",
        "--currency", "CNY"
      ]
    }
  }
}
```

Claude Code automatically loads `.mcp.json` from the project root.
You can also place it in the global path `~/.claude/.mcp.json` to share across projects.

After launching Claude Code, run `/mcp` to check connection status.

---

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "steam-genie": {
      "command": "npx",
      "args": [
        "steam-genie-mcp",
        "--api-key", "YOUR_STEAM_API_KEY",
        "--steam-id", "YOUR_64BIT_STEAM_ID",
        "--currency", "CNY"
      ]
    }
  }
}
```

---

### Cursor / Windsurf (`.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "steam-genie": {
      "command": "npx",
      "args": [
        "steam-genie-mcp",
        "--api-key", "YOUR_STEAM_API_KEY",
        "--steam-id", "YOUR_64BIT_STEAM_ID",
        "--currency", "CNY"
      ]
    }
  }
}
```

---

## 3. Environment Variables (Optional)

You may also configure everything using environment variables instead of CLI arguments:

| Variable         | Description             | Default           |
| ---------------- | ----------------------- | ----------------- |
| `STEAM_API_KEY`  | Steam Web API key       | —                 |
| `STEAM_ID`       | SteamID64               | —                 |
| `STEAM_PATH`     | Steam installation path | **Auto-detected** |
| `STEAM_CURRENCY` | Market/store currency   | CNY               |

---

# 🧰 MCP Tool List

## 🕹️ Game Library Management

| Tool                    | Description                                                          |
| ----------------------- | -------------------------------------------------------------------- |
| `list_games`            | List library games with sorting by install status, playtime, or name |
| `find_game_for_session` | Recommend the best game based on available playtime                  |
| `launch_game`           | Launch a game via AppID (`steam://` protocol)                        |
| `get_game_details`      | Fetch game details: price, reviews, platforms, genres                |
| `get_achievements`      | View achievement progress, including recent unlocks                  |

---

## 💰 Inventory Management

| Tool                    | Description                                                |
| ----------------------- | ---------------------------------------------------------- |
| `get_inventory`         | Retrieve CS2 / Dota2 inventory with live market prices     |
| `get_item_price`        | Query Steam Market prices for a specific item              |
| `get_inventory_summary` | Inventory overview: total value, top items, tradable stats |

---

## 📈 Market Intelligence

| Tool            | Description                                           |
| --------------- | ----------------------------------------------------- |
| `search_store`  | Search the Steam Store                                |
| `get_deals`     | Get active discounts and promotions with filtering    |
| `monitor_price` | Compare current price with historical price data      |
| `check_price`   | Batch query Steam CN-region prices for multiple games |

---

## 📂 Local Integration (No API Key Required)

| Tool                   | Description                                             |
| ---------------------- | ------------------------------------------------------- |
| `list_installed_games` | Scan local VDF files for installed games and disk usage |
| `list_library_folders` | List all Steam library folder locations                 |
| `get_screenshots`      | Retrieve local screenshots by game or globally          |
| `list_shortcuts`       | List added non-Steam shortcuts                          |

---

## 🤝 Social Features

| Tool                 | Description                                                      |
| -------------------- | ---------------------------------------------------------------- |
| `get_friend_list`    | View friends and their online/game status                        |
| `find_shared_games`  | Find games shared with a friend                                  |
| `find_coop_game`     | Recommend multiplayer co-op games from your library              |
| `generate_invite`    | Generate humorous invite messages (4 styles / bilingual support) |
| `get_friend_summary` | Friend online status summary                                     |

---

# 📂 Project Structure

```text
steam-genie-mcp/
├── src/
│   ├── index.ts              # MCP Server entry & tool registration
│   ├── types.ts              # TypeScript type definitions
│   ├── steam/
│   │   ├── api.ts            # Steam Web API wrapper
│   │   ├── market.ts         # Steam Market / pricing services
│   │   ├── vdf.ts            # VDF file parser
│   │   └── launcher.ts       # Game launcher (steam://)
│   └── tools/
│       ├── library.ts        # Game library tools
│       ├── inventory.ts      # Inventory / asset tools
│       ├── market.ts         # Market intelligence tools
│       ├── local.ts          # Local VDF tools
│       └── social.ts         # Social feature tools
├── package.json
├── tsconfig.json
├── LICENSE
├── README.md          # English documentation
└── README_CN.md       # Chinese documentation
```

---

# 🔒 Security Design

Steam-Genie-MCP is a **locally running** MCP server. Your data never leaves your machine.

| Security Feature            | Description                                                                                                                                                              |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **API Key Never Exposed**   | `STEAM_API_KEY` is only read from `.mcp.json` or environment variables and communicates directly with `api.steampowered.com` over stdio. No third-party servers involved |
| **No Telemetry / Tracking** | Zero analytics, zero tracking, zero reporting. The entire project contains only 11 source files and is fully auditable                                                   |
| **Local Read-Only Access**  | VDF parsing only reads configuration files in the Steam installation directory. No file modifications are performed                                                      |
| **Zod Input Validation**    | All 19 MCP tools use strict Zod schemas to prevent injection attacks                                                                                                     |
| **stdio Isolation**         | MCP communication uses standard input/output only. No exposed HTTP ports or network listeners                                                                            |
| **Config Files Ignored**    | `.mcp.json` and `.env` are already added to `.gitignore` to avoid accidental API key commits                                                                             |
| **Sanitized Logs**          | Startup logs only display `✓ configured` instead of printing API keys in plaintext                                                                                       |

> You can audit the full source code in the [`src/`](src/) directory.

---

# 📋 FAQ

<details>
<summary><b>Q: Can I use this without a Steam API Key?</b></summary>

Yes. Local features such as `list_installed_games`, `get_screenshots`, and `list_library_folders` work without an API key. Only online features (friends, store, market) require one.

</details>

<details>
<summary><b>Q: How do I get a Steam Web API Key?</b></summary>

Visit [https://steamcommunity.com/dev/apikey](https://steamcommunity.com/dev/apikey), log into your Steam account, and enter a domain name such as `localhost`.

</details>

<details>
<summary><b>Q: How do I find my SteamID64?</b></summary>

Open the Steam client and check the numeric ID in **Profile → Page URL**.
You can also use an online converter tool for custom profile URLs.

</details>

<details>
<summary><b>Q: Why is my inventory query empty?</b></summary>

1. Make sure your Steam profile inventory privacy is set to **Public**
2. Verify that your SteamID64 is correct
3. CS2 inventory uses `context_id: 2`, and Dota2 also uses `2`

</details>

---

# 🤝 Contributing

Issues, PRs, and feature suggestions are welcome!

Before submitting a PR, please ensure:

* [ ] `npm run typecheck` passes
* [ ] `npm run build` succeeds
* [ ] New tools include clear `zod` schema definitions

---

# 🗺️ Roadmap

* [ ] Wishlist monitoring & price drop notifications
* [ ] Playtime estimation integration (HowLongToBeat)
* [ ] Multi-account inventory aggregation
* [ ] Automatic Steam review translation
* [ ] Remote launch support (Tailscale / Wake-on-LAN)
* [ ] Cloud sync recommendations for game configs

---

# 📄 License

MIT License — see [LICENSE](./LICENSE)

---

<p align="center">
  <sub>Made with ❤️ for Steam gamers and AI enthusiasts</sub>
</p>
