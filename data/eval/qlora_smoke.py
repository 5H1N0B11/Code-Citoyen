#!/usr/bin/env python3
"""Smoke test QLoRA sur Blackwell : charge Mistral-Nemo en int4 (torchao, SANS bitsandbytes),
attache un adaptateur LoRA, fait 3 pas d'entraînement. Valide que la stack tourne avant
d'investir dans le dataset complet. Usage: TORCHDYNAMO_DISABLE=1 python data/eval/qlora_smoke.py
"""
import os
os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, TorchAoConfig
from peft import LoraConfig, get_peft_model

BASE = "data/eval/base_model/Mistral-Nemo-Instruct-2407"
print("torch", torch.__version__, "cuda", torch.cuda.is_available())

tok = AutoTokenizer.from_pretrained(BASE)
if tok.pad_token is None:
    tok.pad_token = tok.eos_token

# --- int4 weight-only via torchao (Blackwell-safe, pas de bitsandbytes) ---
try:
    from torchao.quantization import Int4WeightOnlyConfig
    qcfg = TorchAoConfig(quant_type=Int4WeightOnlyConfig(group_size=128))
except Exception as e:
    print("Int4WeightOnlyConfig indispo, fallback string:", e)
    qcfg = TorchAoConfig("int4_weight_only", group_size=128)

print("Chargement du modèle en int4…")
model = AutoModelForCausalLM.from_pretrained(
    BASE, quantization_config=qcfg, torch_dtype=torch.bfloat16, device_map="cuda",
)
print("VRAM après chargement:", round(torch.cuda.memory_allocated()/1e9, 2), "GB")

lora = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.0,
                  target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
                  task_type="CAUSAL_LM")
model = get_peft_model(model, lora)
model.print_trainable_parameters()
model.train()

opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=1e-4)

examples = [
    "AFFIRMATION : La France a un taux de prélèvements obligatoires d'environ 43%.\nVERDICT : VRAI",
    "AFFIRMATION : Les dirigeants politiques sont tous des incompétents.\nVERDICT : BIAIS (Généralisation Hâtive)",
    "AFFIRMATION : Le chômage est à 7,5% selon l'INSEE.\nVERDICT : VRAI",
]
print("\n--- 3 pas d'entraînement ---")
for step in range(3):
    text = examples[step % len(examples)]
    enc = tok(text, return_tensors="pt").to("cuda")
    out = model(**enc, labels=enc["input_ids"])
    out.loss.backward()
    opt.step(); opt.zero_grad()
    print(f"  step {step}: loss = {out.loss.item():.4f}")

print("\nVRAM pic:", round(torch.cuda.max_memory_allocated()/1e9, 2), "GB")
print("SMOKE_OK : int4 + LoRA + backward fonctionnent sur cette machine.")
