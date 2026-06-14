"""
LoRA 微调脚本 — 游戏助手语气风格训练
基于 Qwen2.5-1.5B-Instruct，适配 8GB VRAM (RTX 4060)
"""

import os
import torch

# 强制使用 HF 镜像，避免国内网络阻断
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    TrainerCallback,
)
from peft import LoraConfig, get_peft_model, TaskType, PeftModel
from trl import SFTTrainer
from datasets import load_dataset

# ============================================================
# 配置区 — 按需修改
# ============================================================

BASE_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"  # 1.5B 稳妥适配 8GB，可换 3B
DATA_FILE = "training_data/game_assistant_data.jsonl"
OUTPUT_DIR = "outputs/lora_game_assistant"
FINAL_MODEL_DIR = "outputs/game_assistant_merged"
MAX_SEQ_LENGTH = 1024          # 最大序列长度
BATCH_SIZE = 1                 # 小批量（8GB 显存限制）
GRAD_ACCUM_STEPS = 8           # 梯度累积 = 等效 batch size 8
NUM_EPOCHS = 3                 # 训练轮数
LEARNING_RATE = 2e-4           # LoRA 推荐学习率
LORA_R = 8                     # LoRA rank（越大越强但越慢）
LORA_ALPHA = 16                # LoRA alpha
LORA_DROPOUT = 0.05            # 防止过拟合
SAVE_STEPS = 50                # 每隔多少步保存一次
WARMUP_STEPS = 10              # 预热步数

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(FINAL_MODEL_DIR, exist_ok=True)


def format_chat(example: dict) -> dict:
    """将 messages 列表转换为训练文本"""
    messages = example["messages"]
    # 使用 Qwen2.5 的 chat template
    text = ""
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if role == "user":
            text += f"<|im_start|>user\n{content}<|im_end|>\n"
        elif role == "assistant":
            text += f"<|im_start|>assistant\n{content}<|im_end|>\n"
    return {"text": text}


class ProgressCallback(TrainerCallback):
    """打印训练进度"""
    def on_log(self, args, state, control, logs=None, **kwargs):
        if logs:
            loss = logs.get("loss", "N/A")
            epoch = logs.get("epoch", "N/A")
            step = logs.get("step", "N/A")
            print(f"  📊 Step {step} | Epoch {epoch} | Loss: {loss}")


def main():
    print("=" * 60)
    print("== 游戏助手 LoRA 微调 ==")
    print(f"   基础模型: {BASE_MODEL}")
    print(f"   训练数据: {DATA_FILE}")
    print(f"   输出目录: {OUTPUT_DIR}")
    print(f"   显存: {torch.cuda.get_device_properties(0).total_mem / 1e9:.1f} GB")
    print("=" * 60)

    # ----------------------------------------------------------
    # 1. 加载模型和分词器 (fp16，不用量化)
    # ----------------------------------------------------------
    print("\n[1/5] 加载模型和分词器...")
    tokenizer = AutoTokenizer.from_pretrained(
        BASE_MODEL,
        local_files_only=True,             # 离线模式，不联网
    )

    # 设置 pad token（Qwen 默认没有）
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        dtype=torch.float16,               # 新版 transformers 用 dtype
        device_map="auto",                 # 自动分配 GPU
        local_files_only=True,             # 离线模式，不联网
        low_cpu_mem_usage=True,            # 减少 CPU 内存占用
    )

    # 启用梯度检查点（省显存）
    model.gradient_checkpointing_enable()
    model.config.use_cache = False  # 训练时必须关闭

    print(f"   模型参数量: {model.num_parameters() / 1e9:.2f}B")

    # ----------------------------------------------------------
    # 2. 配置 LoRA
    # ----------------------------------------------------------
    print("\n[2/5] 配置 LoRA...")
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        target_modules=[               # Qwen2.5 的 attention 层
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        bias="none",
    )

    model = get_peft_model(model, lora_config)
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"   可训练参数: {trainable_params / 1e6:.2f}M（仅 {trainable_params / model.num_parameters() * 100:.2f}%）")

    # ----------------------------------------------------------
    # 3. 加载数据集
    # ----------------------------------------------------------
    print("\n[3/5] 加载训练数据...")
    dataset = load_dataset("json", data_files=DATA_FILE, split="train")
    dataset = dataset.map(format_chat, remove_columns=dataset.column_names)
    print(f"   训练样本数: {len(dataset)}")
    print(f"   ⚠️  建议至少 200 条，当前 {len(dataset)} 条。数据越多效果越好！")

    # ----------------------------------------------------------
    # 4. 训练
    # ----------------------------------------------------------
    print("\n[4/5] 开始训练...")
    training_args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        per_device_train_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRAD_ACCUM_STEPS,
        num_train_epochs=NUM_EPOCHS,
        learning_rate=LEARNING_RATE,
        warmup_steps=WARMUP_STEPS,
        logging_steps=10,
        save_steps=SAVE_STEPS,
        save_total_limit=2,
        fp16=True,                       # 混合精度训练
        gradient_checkpointing=True,     # 省显存
        optim="adamw_torch",
        lr_scheduler_type="cosine",
        remove_unused_columns=False,
        report_to="none",                # 不上传日志
        dataloader_num_workers=0,        # Windows 下设为 0
    )

    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        tokenizer=tokenizer,
        max_seq_length=MAX_SEQ_LENGTH,
        dataset_text_field="text",
        callbacks=[ProgressCallback()],
    )

    trainer.train()

    # ----------------------------------------------------------
    # 5. 保存
    # ----------------------------------------------------------
    print("\n[5/5] 保存 LoRA adapter...")
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    print(f"   Adapter 已保存到: {OUTPUT_DIR}")

    # 保存完整配置，方便后续合并
    model.config.save_pretrained(OUTPUT_DIR)

    print("\n[OK] 训练完成！")
    print(f"   LoRA 权重: {OUTPUT_DIR}")
    print(f"   下一步: python merge_and_export.py")


if __name__ == "__main__":
    main()
