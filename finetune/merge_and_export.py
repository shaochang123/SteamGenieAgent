"""
合并 LoRA adapter → 完整模型，用于 GGUF 转换
"""

import os
import sys
import torch

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

# ============================================================
# 配置
# ============================================================

BASE_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"    # 和训练时保持一致
LORA_PATH = "outputs/lora_game_assistant"      # 训练输出的 adapter 目录
MERGED_PATH = "outputs/game_assistant_merged"  # 合并后的完整模型

# ============================================================


def main():
    print("=" * 60)
    print("🔧 合并 LoRA adapter → 完整模型")
    print(f"   基座模型: {BASE_MODEL}")
    print(f"   LoRA 权重: {LORA_PATH}")
    print(f"   输出路径: {MERGED_PATH}")
    print("=" * 60)

    # 1. 检查 LoRA 权重是否存在
    if not os.path.exists(os.path.join(LORA_PATH, "adapter_config.json")):
        print(f"\n[ERR] 在 {LORA_PATH} 找不到 adapter_config.json")
        print("   请先运行 train_lora.py 完成训练")
        sys.exit(1)

    # 2. 加载基座模型
    print("\n[1/4] 加载基座模型...")
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        dtype=torch.float16,
        device_map="cpu",                     # CPU 合并，兼容性最好
        local_files_only=True,
        low_cpu_mem_usage=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, local_files_only=True)

    # 3. 加载并合并 LoRA
    print("\n[2/4] 加载 LoRA adapter...")
    model = PeftModel.from_pretrained(model, LORA_PATH)
    print("[3/4] 合并权重中...")
    model = model.merge_and_unload()

    # 4. 保存合并后的完整模型
    print(f"\n[4/4] 保存合并模型到 {MERGED_PATH}...")
    os.makedirs(MERGED_PATH, exist_ok=True)
    model.save_pretrained(MERGED_PATH, safe_serialization=True)
    tokenizer.save_pretrained(MERGED_PATH)
    print("   模型 + tokenizer 已保存为 safetensors 格式")

    print("\n" + "=" * 60)
    print("[OK] 合并完成！")
    print(f"   合并模型路径: {MERGED_PATH}")
    print()
    print(" 下一步: 将模型转换为 GGUF 格式")
    print()
    print("   方法 1（推荐）: 使用 llama.cpp 转换")
    print("      git clone https://github.com/ggerganov/llama.cpp")
    print("      cd llama.cpp && pip install -r requirements.txt")
    print(f"     python convert_hf_to_gguf.py {MERGED_PATH} --outtype f16")
    print()
    print("   方法 2: 下载 llama.cpp 预编译版本")
    print("      https://github.com/ggerganov/llama.cpp/releases")
    print("      下载 llama-bxxxx-win-cuda-cu12.2.0-x64.zip")
    print(f"      解压后: .\\llama-convert-hf-to-gguf.exe {MERGED_PATH} --outtype f16")
    print("=" * 60)


if __name__ == "__main__":
    main()
