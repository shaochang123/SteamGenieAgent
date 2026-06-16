from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

# Runtime layout
runtime_path = BASE_DIR / "runtime"
profiles_path = runtime_path / "profiles"
history_path = runtime_path / "histories"
vector_path = runtime_path / "vector"
cache_path = runtime_path / "cache"
md5_path = runtime_path / "md5.txt"

# Legacy paths kept for one-time migration
legacy_history_path = BASE_DIR / "ChatHisTory"
legacy_vector_path = BASE_DIR / "ChatDB"
legacy_md5_path = BASE_DIR / "md5.txt"

# Static assets
knowledge_path = BASE_DIR / "Knowledge"

# User knowledge
user_knowledge_path = runtime_path / "knowledge"

# Non-sensitive defaults
user = "system"
model_name = "qwen3:8b"
# Context/input windows used for prompt budgeting. Provider deployments or
# local Ollama num_ctx settings can still impose lower runtime limits.
model_max_token = {
    # Qwen / Ollama-style names
    "qwen3:0.6b": 32768,
    "qwen3:1.7b": 32768,
    "qwen3:4b": 32768,
    "qwen3:8b": 32768,
    "qwen3:14b": 32768,
    "qwen3:30b-a3b": 32768,
    "qwen3:32b": 32768,
    "qwen3:235b-a22b": 32768,
    "qwen2.5:3b": 131072,
    "qwen2.5:7b": 131072,
    "qwen2.5:14b": 131072,
    "qwen2.5:32b": 131072,
    "qwen2.5:72b": 131072,
    "qwen2.5-coder:7b": 131072,
    "qwen2.5-coder:14b": 131072,
    "qwen2.5-coder:32b": 131072,

    # DeepSeek API names
    "deepseek-v4-flash": 1000000,
    "deepseek-v4-pro": 1000000,
    "deepseek-chat": 1000000,
    "deepseek-reasoner": 1000000,

    # OpenAI API names
    "gpt-4.1": 1048576,
    "gpt-4.1-mini": 1048576,
    "gpt-4.1-nano": 1048576,
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4-turbo": 128000,
    "gpt-3.5-turbo": 16385,

    # Common local/open-weight families
    "llama3:8b": 8192,
    "llama3:70b": 8192,
    "llama3.1:8b": 131072,
    "llama3.1:70b": 131072,
    "llama3.1:405b": 131072,
    "llama3.2:1b": 131072,
    "llama3.2:3b": 131072,
    "llama3.3:70b": 131072,
    "mistral-large": 131072,
    "mistral-large-latest": 131072,
}
max_token = model_max_token[model_name]
embedding_model_name = "qwen3-embedding:4b"
ollama_base_url = "http://127.0.0.1:11434"
openai_base_url = "https://api.openai.com/v1"
openai_model_name = "gpt-4.1-mini"
steam_country = "CN"
steam_language = "zh-CN"
http_timeout = 60
# LLM calls can legitimately take longer than ordinary Steam/API requests,
# especially when the model is deciding whether to call MCP tools.
llm_http_timeout = 300
max_knowledge_upload_bytes = 5 * 1024 * 1024

# Retrieval tuning
chunk_size = 1000
chunk_overlap = 100
separators = ["\n\n", "\n", ".", "!", "?", "。", "！", "？", " ", ""]
max_split_char_number = 1000

system_prompt = (
    "You are a professional Steam data analysis and game recommendation expert. "
    "Answer clearly and concisely.\n"
    "{knowledge_context}"
    "{history_context}"
)

system_prompt_with_tools = (
    "You are a professional Steam data analysis and game recommendation expert "
    "with access to Steam MCP tools (function calling).\n\n"
    "CRITICAL RULES:\n"
    "1. ALWAYS use the available tools to fetch real data. NEVER tell the user "
    "to check manually, open the Steam client, or visit a website.\n"
    "2. For questions about the user's games, playtime, friends, achievements, "
    "inventory, or Steam store, call the relevant tool immediately.\n"
    "3. The tool results are real data, not examples. Cite them directly.\n"
    "4. If a tool returns an error or empty result, explain that clearly, "
    "then try calling it again with different arguments.\n"
    "5. Use default parameter values. Do NOT add filters like installed_only "
    "unless the user explicitly asks for them.\n"
    "6. Do not output code unless the user explicitly asks for code.\n"
    "7. Use tools only through the native function-calling/tool_calls channel. "
    "Never print or simulate tool calls in the answer. Do not output DSML, XML, "
    "JSON, code fences, <tool_calls>, or <invoke> blocks for tool calls.\n"
    "8. Below is a knowledge base and historical dialogue data, but note that games mentioned in the knowledge base do not necessarily exist in the user's database.\n\n"
    "Answer clearly and concisely.\n"
    "{knowledge_context}"
    "{history_context}"
)
