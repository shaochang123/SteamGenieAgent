"""
从合并后的模型创建 Ollama Modelfile 并导入
（需要先完成 GGUF 转换）
"""

import os
import sys

# ============================================================
# 配置
# ============================================================

# GGUF 文件路径（转换后）或 HuggingFace 合并模型目录名
GGUF_FILE = "game-assistant-qwen.gguf"
MODEL_NAME = "game-assistant"  # Ollama 中的模型名

SYSTEM_PROMPT = """你是「游戏精灵」，一个热情、幽默、专业的游戏助手。你的风格特点：
- 说话像资深玩家聊天，自然不做作
- 经常使用游戏圈常用语，适当加入 emoji
- 回答时先共情再给建议
- 推荐游戏时给出具体理由，不是无脑推
- 对玩家的选择保持尊重，不评判游戏品味"""

# ============================================================

MODELFILE_TEMPLATE = """FROM ./{gguf}

TEMPLATE \"\"\"{{ if .System }}<|im_start|>system
{{ .System }}<|im_end|>
{{ end }}{{ if .Prompt }}<|im_start|>user
{{ .Prompt }}<|im_end|>
{{ end }}<|im_start|>assistant
{{ .Response }}<|im_end|>\"
\"\"\"

PARAMETER stop "<|im_start|>"
PARAMETER stop "<|im_end|>"
PARAMETER temperature 0.8
PARAMETER top_p 0.9
PARAMETER top_k 40
PARAMETER num_predict 2048
PARAMETER repeat_penalty 1.1
"""


def main():
    print("🎮 Ollama 游戏助手模型导入")
    print()

    # 检查 GGUF 文件
    if not os.path.exists(GGUF_FILE):
        print(f"⚠️  GGUF 文件 '{GGUF_FILE}' 不存在")
        print()
        print("请先完成 GGUF 转换:")
        print(f"  1. git clone https://github.com/ggerganov/llama.cpp")
        print(f"  2. cd llama.cpp && pip install -r requirements.txt")
        print(f"  3. python convert_hf_to_gguf.py ../outputs/game_assistant_merged \\")
        print(f"       --outtype f16 \\")
        print(f"       --outfile ../{GGUF_FILE}")
        print()
        print("或下载预编译版 llama.cpp 并使用 convert-hf-to-gguf.exe")
        return

    # 生成 Modelfile
    modelfile_content = MODELFILE_TEMPLATE.format(gguf=GGUF_FILE)

    with open("Modelfile", "w", encoding="utf-8") as f:
        f.write(modelfile_content)

    print("✅ Modelfile 已生成")
    print()

    # 提示导入命令
    print("📋 接下来运行以下命令导入到 Ollama：")
    print()
    print(f"    ollama create {MODEL_NAME} -f Modelfile")
    print()
    print("📋 导入后使用：")
    print(f"    ollama run {MODEL_NAME}")
    print()
    print("📋 在你的 SteamGenieMcp 项目中使用：")
    print(f"    将 Ollama Model 配置改为 {MODEL_NAME}")


if __name__ == "__main__":
    main()
