# Quick Start

### 1. Backend requirements

Recommended:

- Python 3.10+
- [Ollama](https://ollama.com/) if you want to use the default local provider or build local embeddings

Install backend dependencies in your own environment:

```bash
pip install -r requirements.txt
```

If you plan to use the default local models, pull them first:

```bash
ollama pull qwen3:8b
ollama pull qwen3-embedding:4b
```

### 2. Frontend requirements

- Node.js 18+

Install frontend dependencies:

```bash
cd frontend
npm install
```

### 3. Start the backend

From the repository root:

```bash
python Agent/server.py
```

The API listens on:

```text
http://127.0.0.1:8000
```

### 4. Start the frontend

In a second terminal:

```bash
cd frontend
npm run serve
```

The UI runs on:

```text
http://127.0.0.1:8080
```

### 5. Open the app

1. Create a local user
2. Open `Settings`
3. Pick exactly one AI provider
4. Optionally add `Steam API Key` and `SteamID64`
5. Start chatting

## Configuration model

Each user profile stores two sections:

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

Defaults are defined in [Agent/config.py](./Agent/config.py).