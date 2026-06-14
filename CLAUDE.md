# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SteamGenieMcp is a local Steam AI workspace with two independent codebases:

1. **Active app**: Python FastAPI backend (`Agent/`) + Vue 2 frontend (`frontend/`) — a chat dashboard with RAG, per-user profiles, and Steam data cards.
2. **Legacy prototype**: TypeScript MCP server (`src/`) — a Steam CLI tool using Model Context Protocol. Kept for reference, not wired to the current dashboard.

## Build / Run / Lint

### Backend (Python)

```bash
# Start the API server (listens on http://127.0.0.1:8000)
python Agent/server.py

# Install dependencies
pip install fastapi uvicorn langchain-chroma langchain-core langchain-ollama langchain-text-splitters

# Pull default local models (if using Ollama)
ollama pull qwen3:8b
ollama pull qwen3-embedding:4b

# Smoke-check Python syntax
python -m py_compile Agent/Agent.py Agent/server.py Agent/profile_store.py Agent/steam_service.py Agent/http_utils.py

# Build the vector index from Agent/Knowledge/ JSON files
python Agent/build_vector_db.py
```

### Frontend (Vue 2)

```bash
cd frontend
npm install
npm run serve      # dev server on http://127.0.0.1:8080
npm run lint       # ESLint
npm run build      # production build
```

### Legacy MCP Server (TypeScript)

```bash
npm install
npm run build      # tsc → dist/
npm run dev        # tsx src/index.ts
npm run typecheck  # tsc --noEmit
```

## Architecture

### Active app data flow

```
frontend (Vue 2, port 8080)
  │  Axios → http://127.0.0.1:8000
  ▼
FastAPI server (Agent/server.py)
  │  Creates Agent() per request
  ▼
Agent (Agent/Agent.py)
  ├── Chroma vector store (OllamaEmbeddings, persist to Agent/runtime/vector/)
  ├── Ollama LLM (qwen3:8b default) or OpenAI-compatible API
  └── Per-user chat history (JSON files at Agent/runtime/histories/{profileId}.json)
```

### Backend key relationships

- **`Agent/server.py`** — FastAPI app; the only entry point. Creates a singleton `ProfileStore`, wires routes to `Agent` and `SteamService`.
- **`Agent/Agent.py`** — Chat orchestrator. On each `Call()`: retrieves context from Chroma → builds messages (system prompt + last 10 history messages + user question) → routes to Ollama or OpenAI-compatible LLM → appends the exchange to the history file.
- **`Agent/profile_store.py`** — CRUD for per-user JSON profiles (`Agent/runtime/profiles/`) and chat histories (`Agent/runtime/histories/`). Handles legacy data migration from `ChatHisTory/` and `ChatDB/`. User IDs are slugified display names.
- **`Agent/steam_service.py`** — Fetches Steam profile data via the Steam Web API (`ISteamUser`, `IPlayerService`) with graceful fallback to public XML profile scraping if no API key is set. Also fetches store featured deals.
- **`Agent/http_utils.py`** — Wrappers around Python stdlib `urllib` (not `requests`). `fetch_json()` and `fetch_text()` with error decoding, `append_query()` for URL building.
- **`Agent/config.py`** — All defaults and path constants. Runtime data is rooted at `Agent/runtime/` (gitignored).

### Per-user isolation

Each user profile (identified by slugified display name) has:
- A profile JSON in `Agent/runtime/profiles/{id}.json` — contains `ai` config (provider, model, keys) and `steam` config (API key, SteamID64, country, language).
- A chat history JSON in `Agent/runtime/histories/{id}.json` — array of `{role, content, timestamp}` objects.
- The profile also determines which LLM provider the `Agent` uses when that user chats.

### Frontend state management

The frontend uses `Vue.observable()` in [appStore.js](frontend/src/store/appStore.js) as a single reactive store — no Vuex/Pinia. The root `App.vue` holds all mutation methods and passes state down as props. API calls are centralized in [api.js](frontend/src/api/api.js) using a shared Axios instance.

### Legacy MCP server (independent)

The TypeScript MCP server in `src/` is a separate program. It registers five tool groups (`library`, `inventory`, `market`, `local`, `social`) on an `McpServer` instance and communicates via stdio. It reads Steam API keys and Steam paths from CLI args or env vars. It does **not** share code or runtime data with the Python backend.

### RAG (Retrieval-Augmented Generation)

Knowledge JSON files in `Agent/Knowledge/` are indexed into Chroma via `build_vector_db.py`. The `Agent` class retrieves top-k chunks per query and injects them into the system prompt. If retrieval fails (e.g., Chroma DB missing), chat degrades to history-only mode instead of crashing. MD5 deduplication prevents re-indexing the same content.

### Graceful degradation patterns

Both `steam_service.py` and `Agent.py` follow a degrade-don't-crash pattern:
- Missing Steam API key → fall back to public XML profile data
- Missing/empty vector store → "No related references" injected into prompt
- Invalid provider config → `RuntimeError` surfaced to the frontend as a 400

## Key conventions

- **No `requests` library**: The Python backend uses only stdlib `urllib`. All HTTP goes through `http_utils.py`.
- **Runtime data is gitignored**: Everything under `Agent/runtime/` stays local. API keys, Steam IDs, and chat histories never commit.
- **Profile IDs are slugs**: `slugify()` in `profile_store.py` converts display names to filesystem-safe IDs (lowercase, alphanumeric + hyphens).
- **History message format**: Always `{role: "user"|"assistant", content: string, timestamp: string}`. Both `Agent.py` and `profile_store.py` normalize legacy formats into this shape.
- **Frontend backend URL**: Set via `VUE_APP_API_BASE_URL` env var or defaults to `http://127.0.0.1:8000`.
