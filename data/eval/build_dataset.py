#!/usr/bin/env python3
"""Construit un dataset de fine-tuning (SFT) à partir des maîtres-étalons.

Chaque claim d'un gold/*.json devient une paire d'entraînement enseignant au modèle
à produire LE verdict idéal (catégorie + verdict + biais + explication) à partir d'une
affirmation propre et de ses sources. Base d'un futur LoRA mistral-nemo (distillation
des étalons construits par recherche web).

Sortie : data/eval/dataset/sft.jsonl  (format messages, compatible Ollama/axolotl/unsloth)
Usage : python data/eval/build_dataset.py
"""
import json, glob
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GOLD = ROOT / "gold"
OUT = ROOT / "dataset" / "sft.jsonl"
OUT.parent.mkdir(parents=True, exist_ok=True)

SYSTEM = (
    "Tu es un fact-checker neutre et rigoureux. À partir d'une affirmation et de ses "
    "sources, produis un verdict au format JSON strict : "
    '{"category": ..., "verdict": ..., "biais_detecte": ... ou null, "explanation_short": ...}. '
    "Verdicts possibles : VRAI, FAUX, TROMPEUR, IMPRECIS, CONTESTE, NON_VERIFIABLE, BIAIS, OPINION. "
    "Confirme un fait vrai (VRAI) aussi nettement que tu démens un faux. "
    "N'invente aucune source ni aucun chiffre."
)

def build():
    n = 0
    with open(OUT, "w", encoding="utf-8") as f:
        for gp in sorted(glob.glob(str(GOLD / "*.json"))):
            gold = json.loads(Path(gp).read_text(encoding="utf-8"))
            for c in gold.get("claims", []):
                srcs = c.get("sources") or []
                src_block = ("\nSOURCES :\n" + "\n".join(f"- {u}" for u in srcs)) if srcs else ""
                user = f"AFFIRMATION : {c['claim_clean']}{src_block}"
                output = {
                    "category": c.get("category"),
                    "verdict": c.get("expected_verdict"),
                    "biais_detecte": c.get("expected_bias"),
                    "explanation_short": c.get("rationale", ""),
                }
                rec = {"messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": user},
                    {"role": "assistant", "content": json.dumps(output, ensure_ascii=False)},
                ], "meta": {"video_id": gold.get("video_id"), "claim_id": c.get("id")}}
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n += 1
    print(f"OK : {n} exemples SFT écrits dans {OUT}")
    print(f"Golds utilisés : {[Path(p).stem for p in sorted(glob.glob(str(GOLD / '*.json')))]}")

if __name__ == "__main__":
    build()
