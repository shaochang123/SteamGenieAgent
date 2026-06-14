import os
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

print('1. torch...')
import torch
print('    OK')

print('2. transformers...')
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments, TrainerCallback
print('    OK')

print('3. peft...')
from peft import LoraConfig, get_peft_model, TaskType, PeftModel
print('    OK')

print('4. trl...')
from trl import SFTTrainer
print('    OK')

print('5. datasets...')
from datasets import load_dataset
print('    OK')

print('ALL IMPORTS PASSED')
