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
    "qwen3:0.6b": 32768, "qwen3:1.7b": 32768, "qwen3:4b": 32768,
    "qwen3:8b": 32768, "qwen3:14b": 32768, "qwen3:30b-a3b": 32768,
    "qwen3:32b": 32768, "qwen3:235b-a22b": 32768,
    "qwen2.5:3b": 131072, "qwen2.5:7b": 131072, "qwen2.5:14b": 131072,
    "qwen2.5:32b": 131072, "qwen2.5:72b": 131072,
    "qwen2.5-coder:7b": 131072, "qwen2.5-coder:14b": 131072, "qwen2.5-coder:32b": 131072,
    "deepseek-v4-flash": 1000000, "deepseek-v4-pro": 1000000,
    "deepseek-chat": 1000000, "deepseek-reasoner": 1000000,
    "gpt-4.1": 1048576, "gpt-4.1-mini": 1048576, "gpt-4.1-nano": 1048576,
    "gpt-4o": 128000, "gpt-4o-mini": 128000, "gpt-4-turbo": 128000,
    "gpt-3.5-turbo": 16385,
    "llama3:8b": 8192, "llama3:70b": 8192,
    "llama3.1:8b": 131072, "llama3.1:70b": 131072, "llama3.1:405b": 131072,
    "llama3.2:1b": 131072, "llama3.2:3b": 131072, "llama3.3:70b": 131072,
    "mistral-large": 131072, "mistral-large-latest": 131072,
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
    "你是「游戏精灵」，一个热情、幽默的 Steam 游戏助手。\n"
    "说话风格像资深玩家聊天，经常使用游戏圈常用语和 emoji。\n"
    "回答时先共情再给建议，推荐游戏给出具体理由。\n"
    "请用中文回答。\n"
    "{knowledge_context}"
    "{history_context}"
)

system_prompt_with_tools = (
    "你是「游戏精灵」，一个热情、幽默的 Steam 游戏助手。\n"
    "你拥有一组 Steam MCP 工具，可以实时获取用户 Steam 账号的真实数据。\n\n"
    "你必须遵守以下规则：\n"
    "1.【强制】当用户问及他的游戏库、游戏时长、好友、成就、库存、截图、\n"
    "   已安装游戏、Steam 商店或促销信息时，你必须立即调用对应工具获取真实数据\n"
    "2.【强制】不要编造数据、不要假装查过了、不要说你无法访问\n"
    "3. 工具返回结果后，基于真实数据用游戏精灵风格回复\n"
    "4. 如果工具返回错误，如实告知用户，然后尝试用其他方式帮助\n"
    "5. 回复必须纯中文自然语言，严禁输出代码或 JSON\n"
    "6. 只通过原生 function_calling/tool_calls 通道使用工具，\n"
    "   绝不打印或模拟工具调用，不输出 DSML、XML、JSON、代码块\n\n"
    "你是一个真正的游戏伙伴，不是机器人客服。\n"
    "{knowledge_context}"
    "{history_context}"
)
