# SteamGenieMcp

一个本地运行的 Steam AI 工作台，包含 Vue 2 前端界面、FastAPI 后端、按用户隔离的会话记忆，以及 Steam 个人资料和商店卡片。

[English](./README.md) | **中文说明**

## 这个仓库现在是什么

当前真正可运行的应用由两部分组成：

- `Agent/`：Python 后端，负责聊天、用户档案、Steam 数据和检索
- `frontend/`：Vue 2 单页前端，提供 iOS 风格的本地控制台界面

仓库里还保留着一套更早的 TypeScript MCP 原型，位于 `src/` 和 `dist/`。它没有被删除，但已经不是当前本地面板的主入口。

## 主要功能

- 多用户本地档案
  - 可创建、切换、删除用户
  - 每个用户都有独立的聊天记录和独立的凭据配置
- 按用户选择 AI 接入方式
  - 每个用户必须二选一：本地 `Ollama` 或 `OpenAI 兼容接口`
  - 切换用户后会恢复该用户自己的历史会话
- 外部记忆管理
  - 用户配置、聊天历史、向量库和日志统一写入 `Agent/runtime/`
  - 这些运行态数据默认被 Git 忽略
- Steam 数据卡片
  - Steam 概览卡：头像、昵称、在线状态、当前游戏、拥有游戏数、最近游戏
  - Steam 商店卡：按地区和语言获取促销卡片
  - 如果只填了 `SteamID64`，但 `Steam API Key` 缺失或无效，系统会自动降级为公开资料模式，而不是整块报错
- 检索增强回答
  - `Agent/Knowledge/` 下的本地知识文件可以写入 Chroma
  - 检索不可用时，会自动降级为纯历史对话，不会直接让聊天失败

## 技术栈

- 后端：Python、FastAPI、Uvicorn
- 检索：LangChain、Chroma、Ollama Embeddings
- 前端：Vue 2、Vue CLI、Axios、Less
- HTTP 请求：Python 标准库 `urllib`

## 项目结构

```text
SteamGenieMcp/
├── Agent/
│   ├── Agent.py                 # 聊天编排和 provider 路由
│   ├── server.py                # FastAPI 服务
│   ├── profile_store.py         # 用户配置和历史消息持久化
│   ├── steam_service.py         # Steam 概览与商店数据
│   ├── http_utils.py            # 简单 HTTP 工具
│   ├── build_vector_db.py       # 可选的知识库索引脚本
│   ├── Knowledge/               # 本地知识 JSON
│   └── runtime/                 # 本地运行态数据，默认不进 Git
├── frontend/
│   ├── src/App.vue
│   ├── src/components/
│   ├── src/api/api.js
│   └── src/store/appStore.js
├── src/                         # 旧的 TypeScript MCP 原型
├── README.md
└── README_CN.md
```

## 运行态数据与 Git 安全

本地敏感数据不会再写进受版本控制的源码文件，而是统一写到：

- `Agent/runtime/profiles/*.json`：每个用户的设置
- `Agent/runtime/histories/*.json`：每个用户的聊天历史
- `Agent/runtime/vector/`：Chroma 向量库
- `Agent/runtime/logs/`：本地开发日志
- `Agent/runtime/md5.txt`：知识索引去重状态

当前已忽略的重要路径：

- `Agent/runtime/`
- `Agent/ChatHisTory/`
- `Agent/ChatDB/`
- `frontend/.env*`
- `.mcp.json`
- `.codex/`

这样可以默认避免把 API Key、SteamID、聊天记录和本地缓存提交到仓库。

## 快速开始

### 1. 后端环境

建议环境：

- Python 3.10+
- 如果你要使用默认本地模型或本地 Embedding，需要安装 [Ollama](https://ollama.com/)

在你的 Python 环境中安装依赖：

```bash
pip install fastapi uvicorn langchain-chroma langchain-core langchain-ollama langchain-text-splitters
```

如果你准备使用默认本地模型，先拉取模型：

```bash
ollama pull qwen3:8b
ollama pull qwen3-embedding:4b
```

### 2. 前端环境

- Node.js 18+

安装前端依赖：

```bash
cd frontend
npm install
```

### 3. 启动后端

在仓库根目录执行：

```bash
python Agent/server.py
```

后端地址：

```text
http://127.0.0.1:8000
```

### 4. 启动前端

另开一个终端：

```bash
cd frontend
npm run serve
```

前端地址：

```text
http://127.0.0.1:8080
```

### 5. 打开应用

1. 新建一个本地用户
2. 打开右上角 `设置`
3. 在 `Ollama` 和 `OpenAI 兼容接口` 中二选一
4. 可选填写 `Steam API Key` 和 `SteamID64`
5. 开始聊天

## 配置模型

每个用户档案包含两部分配置：

### AI

- `provider`
  - `ollama`
  - `openai-compatible`
- `ollama.baseUrl`
- `ollama.model`
- `openaiCompatible.apiKey`
- `openaiCompatible.baseUrl`
- `openaiCompatible.model`

### Steam

- `apiKey`
- `steamId`
- `country`
- `language`

默认值定义在 [Agent/config.py](./Agent/config.py)。

## 可选：构建本地知识索引

如果你想让聊天对 `Agent/Knowledge/` 下的本地 JSON 做检索增强：

```bash
python Agent/build_vector_db.py
```

说明：

- 索引会写入 `Agent/runtime/vector/`
- 重复内容会通过 `Agent/runtime/md5.txt` 去重
- 即使检索失败，也不会阻断聊天，只会降级为普通对话

## HTTP API

前端当前使用的后端接口如下：

- `GET /profiles`
- `POST /profiles`
- `GET /profiles/{profileId}`
- `DELETE /profiles/{profileId}`
- `PATCH /profiles/{profileId}/config`
- `GET /profiles/{profileId}/messages`
- `POST /chat`
- `GET /profiles/{profileId}/steam/overview`
- `GET /profiles/{profileId}/steam/deals`

## 前端界面行为

当前面板分为三块：

- 左侧：用户列表与用户管理
- 中间：聊天记录与输入框
- 右侧：Steam 概览与商店卡片

已经实现的交互细节：

- 设置面板居中显示
- 对话输入框固定在聊天面板底部
- 设置入口只保留在聊天区右上角
- 侧边栏提供删除当前用户，并带确认提示

## 开发命令

前端：

```bash
cd frontend
npm run lint
npm run build
```

后端基础检查：

```bash
python -m py_compile Agent/Agent.py Agent/server.py Agent/profile_store.py Agent/steam_service.py Agent/http_utils.py
```

## 当前默认值

- 默认聊天 provider：`ollama`
- 默认 Ollama Base URL：`http://127.0.0.1:11434`
- 默认 Ollama 模型：`qwen3:8b`
- 默认 OpenAI 兼容 Base URL：`https://api.openai.com/v1`
- 默认 OpenAI 兼容模型：`gpt-4.1-mini`
- 默认 Steam 地区 / 语言：`CN` / `zh-CN`

## 备注

- 只填 `SteamID64` 也能进入公开资料兜底模式
- 如果想显示拥有游戏数和最近游玩数据，仍然需要有效的 Steam Web API Key
- 当前 UI 是本地优先设计，默认假设敏感数据保留在同一台机器上
