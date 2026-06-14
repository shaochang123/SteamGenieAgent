"""
服务器微调脚本 — Qwen2.5-7B/8B LoRA + 工具调用
适配学校服务器 Linux，带断点续训 + GGUF 导出
"""

import os, json, sys, gc, time
import torch
from pathlib import Path

# ============================================================
# 配置（按需修改）
# ============================================================
BASE_MODEL = "unsloth/Qwen2.5-7B-Instruct"  # unsloth 加速版
DATA_FILE = "game_assistant_v3.jsonl"        # 训练数据文件
MAX_SEQ = 2048
BATCH_SIZE = 2
GRAD_ACCUM = 8       # 等效 batch = 16
EPOCHS = 3
LR = 1e-4
SAVE_DIR = Path("./lora_output")
CHECKPOINT_DIR = SAVE_DIR / "checkpoints"
MERGED_DIR = SAVE_DIR / "merged_model"
GGUF_FILE = SAVE_DIR / "game_assistant_7b.gguf"

for d in [SAVE_DIR, CHECKPOINT_DIR, MERGED_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ============================================================
# 0. 环境检测
# ============================================================
print("=" * 60)
print("  游戏助手 LoRA 微调 — 服务器版")
print(f"  PyTorch {torch.__version__} | CUDA {torch.version.cuda}")
if torch.cuda.is_available():
    for i in range(torch.cuda.device_count()):
        p = torch.cuda.get_device_properties(i)
        print(f"  GPU[{i}]: {p.name} ({p.total_memory/1e9:.1f} GB)")
else:
    print("  WARNING: 无 GPU 可用！将使用 CPU（极慢）")
print(f"  数据: {DATA_FILE}")
print(f"  输出: {SAVE_DIR}")
print("=" * 60)

# ============================================================
# 1. 安装依赖
# ============================================================
def install_deps():
    import subprocess
    pkgs = ["unsloth", "datasets", "peft", "accelerate", "trl"]
    for pkg in pkgs:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", pkg], check=False)
    # 安装 huggingface_hub 如果需要（有些服务器需要）
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "huggingface_hub"], check=False)

print("\n检查依赖...")
try:
    import unsloth
    print("  unsloth: OK")
except ImportError:
    print("  安装 unsloth...")
    install_deps()
    import unsloth
    print("  unsloth: OK")

from datasets import Dataset
from trl import SFTTrainer, SFTConfig

# ============================================================
# 2. 加载数据
# ============================================================
print("\n[1/5] 加载数据...")
if not os.path.exists(DATA_FILE):
    print(f"  ERROR: 找不到 {DATA_FILE}！")
    print(f"  请先将训练数据文件传到当前目录。")
    print(f"  scp game_assistant_v3.jsonl user@58.199.177.109:~/")
    sys.exit(1)

data = []
with open(DATA_FILE, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            data.append(json.loads(line))
print(f"  训练样本: {len(data)} 条")

def format_chat(ex):
    text = ""
    for m in ex["messages"]:
        r, c = m["role"], m.get("content", "")
        if r == "user":
            text += f"<|im_start|>user\n{c}<|im_end|>\n"
        elif r == "assistant":
            if m.get("tool_calls"):
                tc = json.dumps(m["tool_calls"], ensure_ascii=False)
                text += f"<|im_start|>assistant\n{tc}<|im_end|>\n"
            else:
                text += f"<|im_start|>assistant\n{c}<|im_end|>\n"
        elif r == "tool":
            text += f"<|im_start|>tool\n{c}<|im_end|>\n"
    return {"text": text}

dataset = Dataset.from_list(data).map(format_chat)
print("  数据格式化完成")

# ============================================================
# 3. 加载模型
# ============================================================
print("\n[2/5] 加载模型...")
from unsloth import FastLanguageModel

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=BASE_MODEL,
    max_seq_length=MAX_SEQ,
    dtype=None,
    load_in_4bit=True,
)
model = FastLanguageModel.get_peft_model(
    model, r=16,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                    "gate_proj", "up_proj", "down_proj"],
    lora_alpha=16, lora_dropout=0.05, bias="none",
    use_gradient_checkpointing="unsloth", random_state=42,
)
trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
total = sum(p.numel() for p in model.parameters())
print(f"  可训练: {trainable/1e6:.1f}M / {total/1e9:.2f}B ({trainable/total*100:.2f}%)")

# ============================================================
# 4. 训练（断点续训）
# ============================================================
print("\n[3/5] 训练...")

ALREADY_MERGED = (MERGED_DIR / "model-00001-of-00004.safetensors").exists()

if ALREADY_MERGED:
    print("  [SKIP] 合并模型已存在，跳过训练")
else:
    trainer = SFTTrainer(
        model=model, tokenizer=tokenizer, train_dataset=dataset,
        args=SFTConfig(
            dataset_text_field="text", max_seq_length=MAX_SEQ,
            per_device_train_batch_size=BATCH_SIZE,
            gradient_accumulation_steps=GRAD_ACCUM,
            num_train_epochs=EPOCHS, learning_rate=LR, warmup_steps=10,
            fp16=False,
            bf16=torch.cuda.is_available(),
            logging_steps=1,
            save_steps=10,
            save_total_limit=3,
            output_dir=str(CHECKPOINT_DIR),
            resume_from_checkpoint=True,
            report_to="none",
        ),
    )
    print(f"  开始训练（检查点: {CHECKPOINT_DIR}）...")
    trainer.train()
    print("  训练完成！")

# ============================================================
# 5. 合并 LoRA
# ============================================================
print("\n[4/5] 合并 LoRA 权重...")

if ALREADY_MERGED:
    print(f"  [SKIP] 合并模型已存在: {MERGED_DIR}")
else:
    model.save_pretrained_merged(str(MERGED_DIR), tokenizer, save_method="merged_16bit")
    print(f"  合并完成: {MERGED_DIR}")

# ============================================================
# 6. 转换 GGUF
# ============================================================
print("\n[5/5] 转换 GGUF...")

if GGUF_FILE.exists():
    size_gb = GGUF_FILE.stat().st_size / 1e9
    print(f"  [SKIP] GGUF 已存在: {GGUF_FILE} ({size_gb:.2f} GB)")
else:
    import subprocess

    # 检查 llama.cpp 是否已克隆
    llama_cpp_dir = SAVE_DIR.parent / "llama.cpp"
    if not (llama_cpp_dir / "convert_hf_to_gguf.py").exists():
        print("  克隆 llama.cpp...")
        subprocess.run(
            ["git", "clone", "--depth", "1",
             "https://github.com/ggerganov/llama.cpp.git",
             str(llama_cpp_dir)],
            check=False,
        )
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q",
             "-r", str(llama_cpp_dir / "requirements.txt")],
            check=False,
        )

    print(f"  转换中（q8_0 量化）...")
    result = subprocess.run(
        [sys.executable, str(llama_cpp_dir / "convert_hf_to_gguf.py"),
         str(MERGED_DIR), "--outtype", "q8_0",
         "--outfile", str(GGUF_FILE)],
        check=False,
    )
    if result.returncode == 0 and GGUF_FILE.exists():
        size_gb = GGUF_FILE.stat().st_size / 1e9
        print(f"  GGUF 完成: {GGUF_FILE} ({size_gb:.2f} GB)")
    else:
        print(f"  GGUF 转换失败（返回码: {result.returncode}）")
        print("  手动转换：")
        print(f"    python {llama_cpp_dir}/convert_hf_to_gguf.py {MERGED_DIR} --outtype q8_0 --outfile {GGUF_FILE}")

# ============================================================
# 完成
# ============================================================
print()
print("=" * 60)
print("  全部完成！")
print(f"  合并模型: {MERGED_DIR}")
print(f"  GGUF 文件: {GGUF_FILE}")
print()
print("  下载到本地：")
print(f"    scp user@58.199.177.109:{GGUF_FILE} ./")
print()
print("  导入 Ollama：")
print("    ollama create game-assistant-v2 -f Modelfile")
print("=" * 60)
