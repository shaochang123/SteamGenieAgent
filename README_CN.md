# 🧞‍♂️ Steam-Genie-MCP

> **让 AI 成为你的终极 Steam 游戏管家。**
> 基于 Model Context Protocol (MCP)，连接你的 AI 助手（Claude Desktop, Cursor, Windsurf）与 Steam 生态。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![MCP Version: 1.0](https://img.shields.io/badge/MCP-Protocol--v1.0-blue)](https://modelcontextprotocol.io)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](http://makeapullrequest.com)

[English](./README.md) | **中文说明**


---

## 🌟 为什么选择 Steam-Genie-MCP？

**Steam-Genie-MCP** 有以下几个特性：

- **离线优先**：VDF 解析器直读本地 Steam 文件，不联网也能秒查已安装游戏、截图
- **区域深耕**：Steam 市场/商店 API 针对国区 (CNY) 深度适配，支持 40+ 货币切换
- **全链路打通**：从游戏推荐 → 资产估值 → 市场比价 → 一键启动，一条龙闭环

**技术栈**：TypeScript + [MCP SDK](https://github.com/modelcontextprotocol/typescript-sdk) + Zod 输入校验 + 自研 VDF 解析引擎。原生支持 Claude Code、Claude Desktop、Cursor、Windsurf。

### 🛠️ 核心功能

| 功能 | 说明 | 使用场景 |
|------|------|---------|
| **🕹️ 极致控制** | 游戏库智能推荐引擎 | "我下午有 2 小时空档，帮我从库里挑一个好评最高且未通关的游戏并启动。" |
| **💰 资产专家** | CS2 / Dota2 饰品估值系统 | "查一下我 CS2 库存值多少钱？哪个饰品涨了？" |
| **📈 市场情报** | Steam 国区特供价格监控 | "监控《黑神话：悟空》的史低价格" |
| **📂 深度本地化** | 离线 VDF 解析器 | "列出我所有已安装的游戏和截图，无需联网。" |
| **🤝 社交助手** | 好友管理 + 邀请生成 | "看看现在谁在线，找个大家都能玩的合作游戏，并生成一段邀请语。" |

---

## 🚀 快速开始

### 前提条件

- 安装了 [Node.js](https://nodejs.org/) (v18+)
- （可选）拥有一个 [Steam Web API Key](https://steamcommunity.com/dev/apikey) — 用于游戏库、好友、成就等在线功能
- 本地 VDF 解析功能**无需 API Key**，直接可用

### 1. 安装与运行

```bash
npx steam-genie-mcp --api-key YOUR_STEAM_KEY --steam-id YOUR_STEAM_ID --steam-path "D:\\steam"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--api-key` | 推荐 | Steam Web API Key，缺失时仅无法使用在线功能 |
| `--steam-id` | 推荐 | SteamID64，缺失时仅无法使用库存/好友功能 |
| `--steam-path` | 否 | Steam 安装目录，**不填则自动检测**（Windows/macOS/Linux） |
| `--currency` | 否 | 市场/商店价格显示的货币，默认 CNY（人民币）。支持 USD/EUR/JPY 等 40+ 种货币 |

`currency` 参数控制：
- 库存物品的**市场最低价**显示货币
- 游戏商店**价格查询**（`check_price`、`monitor_price`、`get_deals`）的币种
- Steam 市场 API 返回的货币单位（如 `USD` → `$`、`CNY` → `¥`）

### 2. 配置 AI 助手

**Claude Code**（项目根目录 `.mcp.json`）：

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

Claude Code 会自动加载项目根目录的 `.mcp.json`。也可以放入全局 `~/.claude/.mcp.json`，所有项目通用。启动 Claude Code 后输入 `/mcp` 可查看连接状态。

**Claude Desktop** (`claude_desktop_config.json`)：

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

**Cursor / Windsurf** (`.cursor/mcp.json`)：

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

### 3. 环境变量配置 (可选)

除 CLI 参数外，你也可以使用环境变量：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `STEAM_API_KEY` | Steam Web API 密钥 | — |
| `STEAM_ID` | SteamID64 | — |
| `STEAM_PATH` | Steam 安装目录 | **自动检测** |
| `STEAM_CURRENCY` | 市场/商店价格货币 | CNY |

---

## 🧰 MCP 工具列表

### 🕹️ 游戏库管理

| 工具 | 描述 |
|------|------|
| `list_games` | 列出游戏库，支持按安装状态、时长、名称排序 |
| `find_game_for_session` | 根据空闲时长智能推荐最适合的游戏 |
| `launch_game` | 通过 AppID 启动游戏（调用 `steam://` 协议） |
| `get_game_details` | 获取游戏详情：价格、评价、平台、类型 |
| `get_achievements` | 查询成就进度，展示最近解锁和未解锁项 |

### 💰 资产管理

| 工具 | 描述 |
|------|------|
| `get_inventory` | 获取 CS2 / Dota2 库存，含市场实时价格 |
| `get_item_price` | 查询单个物品的 Steam 市场行情 |
| `get_inventory_summary` | 库存摘要：总估值、Top 物品、可交易统计 |

### 📈 市场情报

| 工具 | 描述 |
|------|------|
| `search_store` | 搜索 Steam 商店 |
| `get_deals` | 获取当前促销折扣列表，支持按折扣筛选 |
| `monitor_price` | 对比当前价格与历史数据，判断是否史低 |
| `check_price` | 批量查询多个游戏的中国区价格 |

### 📂 本地集成（无需 API Key）

| 工具 | 描述 |
|------|------|
| `list_installed_games` | 扫描本地 VDF 文件，列出已安装游戏及磁盘占用 |
| `list_library_folders` | 列出所有 Steam 库文件夹位置 |
| `get_screenshots` | 按游戏或全部列出本地截图 |
| `list_shortcuts` | 列出添加的非 Steam 快捷方式 |

### 🤝 社交功能

| 工具 | 描述 |
|------|------|
| `get_friend_list` | 查看好友列表及在线/游戏状态 |
| `find_shared_games` | 查找与指定好友的共同游戏 |
| `find_coop_game` | 从库中筛选支持多人合作的游戏 |
| `generate_invite` | 生成风趣的游戏邀请语 (4 种风格 / 中英文) |
| `get_friend_summary` | 好友在线统计摘要 |

---

## 📂 项目结构

```
steam-genie-mcp/
├── src/
│   ├── index.ts              # MCP Server 入口，工具注册
│   ├── types.ts              # TypeScript 类型定义
│   ├── steam/
│   │   ├── api.ts            # Steam Web API 封装
│   │   ├── market.ts         # Steam 市场 / 价格服务
│   │   ├── vdf.ts            # VDF 文件解析器
│   │   └── launcher.ts       # 游戏启动器 (steam://)
│   └── tools/
│       ├── library.ts        # 游戏库管理工具
│       ├── inventory.ts      # 库存 / 资产管理工具
│       ├── market.ts         # 市场情报工具
│       ├── local.ts          # 本地 VDF 工具
│       └── social.ts         # 社交功能工具
├── package.json
├── tsconfig.json
├── LICENSE
├── README.md          # English documentation
└── README_CN.md       # 中文文档
```

---

## 🔒 安全设计

Steam-Genie-MCP 是**本地运行**的 MCP Server，你的数据从未离开你的机器：

| 安全特性 | 说明 |
|----------|------|
| **API Key 不出境** | `STEAM_API_KEY` 仅从你的 `.mcp.json` 或环境变量读取，通过 stdio 直连 `api.steampowered.com`。不经过任何第三方服务器 |
| **无遥测无追踪** | 零埋点、零分析、零上报。代码一共 11 个源文件，全部可审计 |
| **本地只读** | VDF 解析仅读取 Steam 安装目录下的配置文件，不写入、不修改任何本地文件 |
| **Zod 输入校验** | 全部 19 个 MCP 工具的输入参数均由 Zod schema 严格校验，防止注入 |
| **stdio 隔离** | MCP 协议通过标准输入/输出通信，无 HTTP 端口暴露，无网络监听 |
| **配置不入库** | `.mcp.json` 和 `.env` 已加入 `.gitignore`，不会误提交 API Key |
| **Stderr 脱敏** | 启动日志中 API Key 仅显示 `✓ configured`，不会明文打印 |

> 你可以在 [`src/`](src/) 目录下审阅全部源码。

---

## 📋 常见问题

<details>
<summary><b>Q: 没有 Steam API Key 怎么用？</b></summary>

本地功能（`list_installed_games`、`get_screenshots`、`list_library_folders` 等）不需要 API Key。只有需要联网的功能（好友、商店、市场）才需要 API Key。
</details>

<details>
<summary><b>Q: 如何获取 Steam Web API Key？</b></summary>

访问 [https://steamcommunity.com/dev/apikey](https://steamcommunity.com/dev/apikey)，登录你的 Steam 账号，填写一个域名（如 `localhost`）即可获取。
</details>

<details>
<summary><b>Q: 如何获取我的 SteamID64？</b></summary>

打开 Steam 客户端，点击 **个人资料 → 页面 URL** 中的数字即为 SteamID64。或者使用在线工具转换你的自定义 URL。
</details>

<details>
<summary><b>Q: 库存查询返回空怎么办？</b></summary>

1. 确认 Steam 个人资料 → 隐私设置 → 库存设为「公开」
2. 确认使用的 SteamID64 正确
3. CS2 库存改用 context_id: 2，Dota2 用 2
</details>

---

## 🤝 参与贡献

欢迎提交 Issue、PR 和功能建议！提交 PR 前请确保：

- [ ] `npm run typecheck` 通过
- [ ] `npm run build` 成功
- [ ] 新增工具包含清晰的 `zod` schema 描述

---

## 🗺️ 路线图

- [ ] 愿望单监控与降价通知
- [ ] 游戏时长预估（对接 HowLongToBeat）
- [ ] 多账号库存聚合管理
- [ ] Steam 评测自动翻译
- [ ] 远程启动（Tailscale/Wake-on-LAN）
- [ ] 游戏配置云同步建议

---

## 📄 许可证

MIT License — 详见 [LICENSE](./LICENSE)

---

<p align="center">
  <sub>Made with ❤️ for Steam gamers and AI enthusiasts</sub>
</p>
