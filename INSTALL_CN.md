# 快速开始

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

