"""
本地 LoRA 训练脚本 — RTX 4060 8GB 优化版
使用 Qwen2.5-3B-Instruct fp16 + LoRA（无需 bitsandbytes）
"""

import os, json, sys, time, gc
import torch
from pathlib import Path

# ============================================================
# 配置
# ============================================================
BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"
DATA_FILE = "training_data/game_assistant_v2.jsonl"
OUTPUT_DIR = Path("outputs/lora_v3")
MERGED_DIR = Path("outputs/game_assistant_3b_merged")
GGUF_FILE = Path("outputs/game_assistant_3b.gguf")
MAX_SEQ_LENGTH = 2048
BATCH_SIZE = 1
GRAD_ACCUM = 16
EPOCHS = 3
LR = 1e-4

# 从 ModelScope 国内源下载模型（速度快，不走代理）
BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"
MS_MODEL = "qwen/Qwen2.5-3B-Instruct"

from modelscope import snapshot_download as ms_download
MS_CACHE = os.path.join(os.path.expanduser("~"), ".cache", "modelscope")
MODEL_PATH = os.path.join(MS_CACHE, "qwen", "Qwen2___5-3B-Instruct")  # ModelScope 命名规则

if not os.path.exists(os.path.join(MODEL_PATH, "config.json")):
    print(f"从 ModelScope 下载模型（国内高速）...")
    ms_download(MS_MODEL, cache_dir=MS_CACHE)
    print(f"下载完成: {MODEL_PATH}")
else:
    print(f"模型已缓存: {MODEL_PATH}")

# 直接使用本地路径加载（transformers 支持）
BASE_MODEL = MODEL_PATH

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
MERGED_DIR.mkdir(parents=True, exist_ok=True)


def main():
    print("=" * 60)
    print("  本地 LoRA 微调 — 游戏助手 v3")
    print(f"  GPU: {torch.cuda.get_device_name(0)}")
    print(f"  VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
    print(f"  模型: {BASE_MODEL}")
    print(f"  数据: {DATA_FILE}")
    print("=" * 60)

    # ---- Step 1: Load model ----
    print("\n[1/5] 加载模型...")
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True, local_files_only=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True,
        low_cpu_mem_usage=True,
    )
    model.gradient_checkpointing_enable()
    model.config.use_cache = False
    print(f"  参数量: {model.num_parameters() / 1e9:.2f}B")

    # ---- Step 2: LoRA ----
    print("\n[2/5] 配置 LoRA...")
    from peft import LoraConfig, get_peft_model, TaskType

    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=16, lora_alpha=16, lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        bias="none",
    )
    model = get_peft_model(model, lora_config)
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"  可训练: {trainable/1e6:.1f}M / {model.num_parameters()/1e9:.2f}B ({trainable/model.num_parameters()*100:.2f}%)")

    # ---- Step 3: Load data ----
    print("\n[3/5] 加载数据...")
    from datasets import Dataset

    data = []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    print(f"  {len(data)} 条训练数据")

    def format_chat(example):
        text = ""
        for msg in example["messages"]:
            role = msg["role"]
            content = msg.get("content", "")
            if role == "user":
                text += f"<|im_start|>user\n{content}<|im_end|>\n"
            elif role == "assistant":
                if msg.get("tool_calls"):
                    tc_json = json.dumps(msg["tool_calls"], ensure_ascii=False)
                    text += f"<|im_start|>assistant\n{tc_json}<|im_end|>\n"
                else:
                    text += f"<|im_start|>assistant\n{content}<|im_end|>\n"
            elif role == "tool":
                text += f"<|im_start|>tool\n{content}<|im_end|>\n"
        return {"text": text}

    dataset = Dataset.from_list(data).map(format_chat)

    # ---- Step 4: Train ----
    print("\n[4/5] 训练中...")
    from trl import SFTTrainer, SFTConfig

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        args=SFTConfig(
            dataset_text_field="text",
            max_seq_length=MAX_SEQ_LENGTH,
            per_device_train_batch_size=BATCH_SIZE,
            gradient_accumulation_steps=GRAD_ACCUM,
            num_train_epochs=EPOCHS,
            learning_rate=LR,
            warmup_steps=10,
            fp16=True,
            gradient_checkpointing=True,
            logging_steps=1,
            save_steps=99999,
            output_dir=str(OUTPUT_DIR),
            report_to="none",
            dataloader_num_workers=0,
            optim="adamw_torch",
        ),
    )

    trainer.train()
    print("  训练完成！")

    # ---- Step 5: Merge + GGUF ----
    print("\n[5/5] 合并 + 转换 GGUF...")

    print("  合并 LoRA...")
    model = model.merge_and_unload()
    model.save_pretrained(str(MERGED_DIR), safe_serialization=True)
    tokenizer.save_pretrained(str(MERGED_DIR))
    print(f"  合并模型 -> {MERGED_DIR}")

    print("  转换 GGUF...")
    import subprocess
    result = subprocess.run(
        ["python", "llama.cpp/convert_hf_to_gguf.py",
         str(MERGED_DIR), "--outtype", "f16",
         "--outfile", str(GGUF_FILE)],
        capture_output=True, text=True,
        cwd=str(Path(__file__).resolve().parent),
    )
    if result.returncode != 0:
        print("  GGUF 转换失败，需要手动安装 llama.cpp:")
        print("    git clone https://github.com/ggerganov/llama.cpp")
        print(f"    python convert_hf_to_gguf.py {MERGED_DIR} --outtype f16 --outfile {GGUF_FILE}")
    else:
        size_gb = GGUF_FILE.stat().st_size / 1e9
        print(f"  GGUF -> {GGUF_FILE} ({size_gb:.1f} GB)")

    print("\n" + "=" * 60)
    print("  [OK] 全部完成！")
    print(f"  合并模型: {MERGED_DIR}")
    print(f"  GGUF: {GGUF_FILE}")
    print(f"  导入: ollama create game-assistant-v3 -f Modelfile")
    print("=" * 60)


if __name__ == "__main__":
    main()
