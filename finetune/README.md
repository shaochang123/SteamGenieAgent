# 🎮 游戏助手 LoRA 微调工程

将 Ollama 模型微调为「游戏精灵」语气风格。

## 硬件要求

- NVIDIA GPU 8GB+ VRAM（当前：RTX 4060 8GB ✅）
- Python 3.12.7（SteamGenieMcp venv ✅）

## 文件结构

```
finetune/
├── README.md                    ← 本文件
├── train_lora.py                ← 训练脚本
├── merge_and_export.py          ← 合并 LoRA → 完整模型
├── create_ollama_model.py       ← 生成 Ollama Modelfile
├── expand_data.py               ← 批量扩充训练数据
└── training_data/
    └── game_assistant_data.jsonl ← 训练数据（10条种子数据）
```

## 操作流程

### 步骤 1：扩充训练数据

当前只有 10 条种子数据，需要扩充到 200+ 条：

```bash
cd finetune
python expand_data.py
```

> 确保 Ollama 在运行（自动调用 qwen3:8b 批量生成对话数据）

---

### 步骤 2：运行 LoRA 训练

```bash
cd finetune
python train_lora.py
```

训练参数（可在脚本顶部修改）：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| BASE_MODEL | Qwen2.5-1.5B-Instruct | 基座模型 |
| NUM_EPOCHS | 3 | 训练轮数 |
| BATCH_SIZE | 1 | 批量大小（8GB 显存限制） |
| LEARNING_RATE | 2e-4 | LoRA 学习率 |
| LORA_R | 8 | LoRA rank |

**预计时间**：200 条数据 × 3 epochs ≈ 10-20 分钟（RTX 4060）

如果 OOM（显存溢出）：
- 减小 `MAX_SEQ_LENGTH` 到 512
- 确认关闭了其他占用显存的程序（Chrome、Ollama 等）

---

### 步骤 3：合并 LoRA 权重

```bash
python merge_and_export.py
```

生成完整模型到 `outputs/game_assistant_merged/`

---

### 步骤 4：转换 GGUF

```bash
# 克隆 llama.cpp
git clone https://github.com/ggerganov/llama.cpp.git
cd llama.cpp
pip install -r requirements.txt

# 转换
python convert_hf_to_gguf.py ../outputs/game_assistant_merged \
    --outtype f16 \
    --outfile ../game-assistant-qwen.gguf
cd ..
```

> 如果转换报错，尝试 `--outtype q8_0` 替代 `f16`

---

### 步骤 5：导入 Ollama

```bash
python create_ollama_model.py
ollama create game-assistant -f Modelfile
```

---

### 步骤 6：在你的项目中使用

1. 打开前端 → 设置 → Ollama Model 改为 `game-assistant`
2. 或在 config.py 中修改默认模型为 `game-assistant`

---

## 如何进一步优化效果

1. **增加数据量** — 目标 500-1000 条效果最佳
2. **提高数据质量** — 手动审核 AI 生成的对话，修正不自然的表达
3. **调大 LoRA rank** — 从 r=8 提升到 r=16（需要更多显存）
4. **换更大的基座模型** — 如 Qwen2.5-3B-Instruct（更吃显存但效果好）
