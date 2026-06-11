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
embedding_model_name = "qwen3-embedding:4b"
ollama_base_url = "http://127.0.0.1:11434"
openai_base_url = "https://api.openai.com/v1"
openai_model_name = "gpt-4.1-mini"
steam_country = "CN"
steam_language = "zh-CN"
http_timeout = 60

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
    "1. ALWAYS use the available tools to fetch real data — NEVER tell the user "
    "to check manually, open the Steam client, or visit a website.\n"
    "2. For questions about the user's games, playtime, friends, achievements, "
    "inventory, or Steam store — call the relevant tool immediately.\n"
    "3. The tool results are real data, not examples. Cite them directly.\n"
    "4. If a tool returns an error or empty result, explain that clearly, "
    "then try calling it again with different arguments.\n"
    "5. Use default parameter values — do NOT add filters like installed_only "
    "unless the user explicitly asks for them.\n\n"
    "Answer clearly and concisely.\n"
    "{knowledge_context}"
    "{history_context}"
)
