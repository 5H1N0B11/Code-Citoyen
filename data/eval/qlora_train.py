#!/usr/bin/env python3
"""QLoRA distillation : entraîne mistral-nemo (NF4 + LoRA) sur les analyses-étalons
pour améliorer la CALIBRATION (catégorie, verdict nuancé). Sortie : adaptateur LoRA.
Env: MAX_STEPS pour un run court de validation (sinon epochs complètes).
Usage: TORCHDYNAMO_DISABLE=1 python data/eval/qlora_train.py
"""
import os, json
os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
import torch
from datasets import Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import LoraConfig, prepare_model_for_kbit_training
from trl import SFTConfig, SFTTrainer

BASE = "data/eval/base_model/Mistral-Nemo-Instruct-2407"
OUT = "data/eval/lora_adapter"
MAX_STEPS = int(os.environ.get("MAX_STEPS", "0"))

tok = AutoTokenizer.from_pretrained(BASE, fix_mistral_regex=True)
if tok.pad_token is None:
    tok.pad_token = tok.eos_token

# Liger-kernel : fused linear cross-entropy → ne matérialise plus les logits [seq×131k vocab],
# économise ~2,5 Go (permet de coexister avec le bot de trading sur le même GPU 16 Go).
try:
    from liger_kernel.transformers import apply_liger_kernel_to_mistral
    apply_liger_kernel_to_mistral(fused_linear_cross_entropy=True, cross_entropy=False)
    print("Liger-kernel appliqué (fused cross-entropy).")
except Exception as e:
    print(f"Liger indispo (on continue sans): {e}")

bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                         bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
print("Chargement NF4…")
model = AutoModelForCausalLM.from_pretrained(BASE, quantization_config=bnb, device_map={"": 0})
model = prepare_model_for_kbit_training(model)
model.config.use_cache = False

DROPOUT = float(os.environ.get("DROPOUT", "0.05"))
EPOCHS = float(os.environ.get("EPOCHS", "4"))
R = int(os.environ.get("R", "32"))
MODULES = os.environ.get("MODULES", "q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj").split(",")
lora = LoraConfig(r=R, lora_alpha=2 * R, lora_dropout=DROPOUT,
                  target_modules=MODULES, task_type="CAUSAL_LM")

rows = [json.loads(l) for l in open("data/eval/dataset/sft.jsonl", encoding="utf-8")]
ds = Dataset.from_list([{"messages": r["messages"]} for r in rows])
print(f"{len(ds)} exemples d'entraînement")

cfg = dict(output_dir="data/eval/lora_out", per_device_train_batch_size=1,
           gradient_accumulation_steps=8, num_train_epochs=EPOCHS, learning_rate=2e-4,
           lr_scheduler_type="cosine", warmup_ratio=0.05, logging_steps=5,
           save_strategy="no", bf16=True, gradient_checkpointing=True,
           max_length=int(os.environ.get("MAXLEN", "768")),  # paged optim retiré (bug bnb Blackwell)
           gradient_checkpointing_kwargs={"use_reentrant": False}, report_to="none")
if MAX_STEPS > 0:
    cfg["max_steps"] = MAX_STEPS
args = SFTConfig(**cfg)

trainer = SFTTrainer(model=model, args=args, train_dataset=ds,
                     peft_config=lora, processing_class=tok)
trainer.train()
trainer.save_model(OUT)
tok.save_pretrained(OUT)
print(f"TRAIN_DONE → adaptateur sauvé dans {OUT}")
