# 🧞‍♂️ Steam-Genie-MCP

> **让 AI 成为你的终极 Steam 游戏管家。**  
> 基于 Model Context Protocol (MCP)，连接你的 AI 助手（Claude, Cursor, Windsurf）与 Steam 生态。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![MCP Version: 1.0](https://img.shields.io/badge/MCP-Protocol--v1.0-blue)](https://modelcontextprotocol.io)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](http://makeapullrequest.com)

[English](./README_EN.md) | **中文说明**

---

## 🌟 为什么选择 Steam-Genie-MCP？

目前 GitHub 上大多数 Steam MCP 仅支持基础的 Web API 调用。**Steam-Genie-MCP** 专为深度玩家设计，通过深度整合**本地客户端数据**与**区域化市场信息**，实现真正的“一句话玩转 Steam”。

### 🛠️ 核心功能

*   **🕹️ 极致控制：** “我下午有 2 小时空档，帮我从库里挑一个好评最高且未通关的游戏并启动。”
*   **💰 资产专家：** 深度集成 **CS2/Dota2 饰品估值**，一键查询库存市场价值波动。
*   **📈 市场情报：** 针对 **Steam 国区** 优化，监控史低价格、汇率变动，再也不用手动刷小黑盒。
*   **📂 深度本地化：** 直接解析本地 `VDF` 文件，无需网络即可秒速读取已安装游戏列表及截图。
*   **🤝 社交助手：** “看看现在谁在线，找个大家都能玩的合作游戏，并生成一段邀请语。”

---

## 📺 演示 (Demo)

![Demo GIF](https://your-project-link.com/demo.gif)
*(建议在此处放置一个 GIF，展示你在 Claude 桌面端输入指令，Steam 自动启动游戏的瞬间)*

---

## 🚀 快速开始

### 前提条件
*   安装了 [Node.js](https://nodejs.org/) (v18+)
*   拥有一个 [Steam Web API Key](https://steamcommunity.com/dev/apikey)

### 1. 安装
使用 `npx` 直接运行（最简方式）：
```bash
npx steam-genie-mcp --api-key YOUR_STEAM_KEY --steam-id YOUR_STEAM_ID