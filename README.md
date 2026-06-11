# SteamGenieMcp

Local Steam AI workspace with a Vue 2 dashboard, a FastAPI backend, per-user memory, and Steam profile/store cards.

Watch [INSTALL](./INSTALL.md) to configure the project

**English** | [中文说明](./README_CN.md)

## What this repo is now

The active application in this repository is:

- `Agent/`: Python backend for chat, profile storage, Steam data, and retrieval
- `frontend/`: Vue 2 single-page UI with an iOS-style layout

This repo also still contains an earlier TypeScript MCP prototype under `src/` and `dist/`. It is kept in the repository, but it is not the main surface used by the current local dashboard.

## Features

- Multi-user local profiles
  - Create, switch, and delete users by display name
  - Each user gets isolated chat history and isolated credentials
- AI chat with per-user provider selection
  - Choose exactly one provider per user: local `Ollama` or an `OpenAI-compatible` API
  - Recent conversation history is preserved when switching users
- External memory management
  - User profiles, message history, vector data, and logs live under `Agent/runtime/`
  - Runtime data is ignored by Git by default
- Steam data cards
  - Steam overview card: avatar, persona name, online status, current game, owned game stats, recent games
  - Steam store deals card: featured discounts for the configured region and language
  - If `SteamID64` is present but the Steam Web API key is missing or invalid, the app falls back to public profile data instead of failing completely
- Retrieval-augmented answers
  - Local knowledge files under `Agent/Knowledge/` can be indexed into Chroma
  - If retrieval is unavailable, chat degrades to history-only responses instead of crashing

## Stack

- Backend: Python, FastAPI, Uvicorn
- Retrieval: LangChain, Chroma, Ollama embeddings
- Frontend: Vue 2, Vue CLI, Axios, Less
- Data fetch: Python stdlib `urllib`

## Project layout

```text
SteamGenieMcp/
├── Agent/
│   ├── Agent.py                 # chat orchestration and provider routing
│   ├── server.py                # FastAPI app
│   ├── profile_store.py         # per-user profile and history persistence
│   ├── steam_service.py         # Steam profile and store data
│   ├── http_utils.py            # small HTTP helpers
│   ├── build_vector_db.py       # optional knowledge indexing
│   ├── Knowledge/               # optional local knowledge JSON files
│   └── runtime/                 # local-only runtime data, ignored by Git
├── frontend/
│   ├── src/App.vue
│   ├── src/components/
│   ├── src/api/api.js
│   └── src/store/appStore.js
├── src/                         # legacy TypeScript MCP prototype
├── README.md
└── README_CN.md
```

## Runtime data and Git safety

Local data is intentionally written outside tracked source files:

- `Agent/runtime/profiles/*.json`: per-user settings
- `Agent/runtime/histories/*.json`: per-user chat history
- `Agent/runtime/vector/`: Chroma persistence
- `Agent/runtime/logs/`: local dev logs
- `Agent/runtime/md5.txt`: dedupe state for knowledge indexing

Ignored paths include:

- `Agent/runtime/`
- `Agent/ChatHisTory/`
- `Agent/ChatDB/`
- `frontend/.env*`
- `.mcp.json`
- `.codex/`

That keeps API keys, Steam identifiers, histories, and local caches out of commits by default.

## HTTP API

The frontend talks to these backend endpoints:

- `GET /profiles`
- `POST /profiles`
- `GET /profiles/{profileId}`
- `DELETE /profiles/{profileId}`
- `PATCH /profiles/{profileId}/config`
- `GET /profiles/{profileId}/messages`
- `POST /chat`
- `GET /profiles/{profileId}/steam/overview`
- `GET /profiles/{profileId}/steam/deals`

## Frontend behavior

The current dashboard is designed around three areas:

- Left: profile list and user management
- Center: chat history and composer
- Right: Steam overview and Steam deals

UI details that are already implemented:

- centered settings modal
- pinned chat composer at the bottom of the chat pane
- single settings entry in the top-right of the chat pane
- delete-user action in the sidebar with confirmation

## Development commands

Frontend:

```bash
cd frontend
npm run lint
npm run build
```

Backend smoke checks:

```bash
python -m py_compile Agent/Agent.py Agent/server.py Agent/profile_store.py Agent/steam_service.py Agent/http_utils.py
```

## Known defaults

- default chat provider: `ollama`
- default Ollama base URL: `http://127.0.0.1:11434`
- default Ollama model: `qwen3:8b`
- default OpenAI-compatible base URL: `https://api.openai.com/v1`
- default OpenAI-compatible model: `gpt-4.1-mini`
- default Steam country/language: `CN` / `zh-CN`

## Notes

- `SteamID64` alone is enough to show a public-profile fallback
- A valid Steam Web API key is still required for owned-game counts and recent-play data
- The current UI is local-first and assumes sensitive data stays on the same machine
