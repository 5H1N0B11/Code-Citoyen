#!/usr/bin/env python3
"""Smoke QLoRA via bitsandbytes NF4 (chargement DIRECT en 4-bit, pic ~7 Go).
Teste si les kernels bnb tournent sur Blackwell sm_120."""
import os
os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

BASE = "data/eval/base_model/Mistral-Nemo-Instruct-2407"
print("torch", torch.__version__, "cuda", torch.cuda.is_available())
tok = AutoTokenizer.from_pretrained(BASE)
if tok.pad_token is None: tok.pad_token = tok.eos_token

bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                         bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
print("Chargement NF4…")
model = AutoModelForCausalLM.from_pretrained(BASE, quantization_config=bnb, device_map={"": 0})
print("VRAM après chargement:", round(torch.cuda.memory_allocated()/1e9, 2), "GB")

model = prepare_model_for_kbit_training(model)
lora = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.0,
                  target_modules=["q_proj","k_proj","v_proj","o_proj"], task_type="CAUSAL_LM")
model = get_peft_model(model, lora)
model.print_trainable_parameters()
model.train()
opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=1e-4)

ex = ["AFFIRMATION : La France a ~43% de prélèvements obligatoires.\nVERDICT : VRAI",
      "AFFIRMATION : Les politiques sont tous nuls.\nVERDICT : BIAIS",
      "AFFIRMATION : Le chômage est à 7,5% (INSEE).\nVERDICT : VRAI"]
print("--- 3 pas ---")
for s in range(3):
    enc = tok(ex[s], return_tensors="pt").to("cuda")
    out = model(**enc, labels=enc["input_ids"]); out.loss.backward()
    opt.step(); opt.zero_grad()
    print(f"  step {s}: loss = {out.loss.item():.4f}")
print("VRAM pic:", round(torch.cuda.max_memory_allocated()/1e9, 2), "GB")
print("SMOKE_BNB_OK")
