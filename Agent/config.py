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
    "Answer clearly and concisely. Use the retrieved references when they are available. "
    "If no relevant reference exists, rely on the recent chat history and the user's prompt. "
    "References:\n{context}"
)
