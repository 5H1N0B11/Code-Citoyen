#!/usr/bin/env python3
"""Construit le dataset de distillation (SFT) à partir des maîtres-étalons.

v2 — MIROIR DE L'INFÉRENCE : le bot fait DEUX appels (classification = 1 mot, puis
analyse = JSON). On émet donc 2 exemples par claim, pour que le LoRA améliore les deux
appels réels. Réduit l'écart train/inference (reco research_sota.md).

Env HELDOUT="id1,id2" : exclut ces vidéos (split train/test honnête).
Env OUT=chemin : fichier de sortie (défaut data/eval/dataset/sft.jsonl).
Usage : python data/eval/build_dataset.py
"""
import json, glob, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GOLD = ROOT / "gold"
OUT = Path(os.environ.get("OUT", str(ROOT / "dataset" / "sft.jsonl")))
OUT.parent.mkdir(parents=True, exist_ok=True)
HELDOUT = set(x for x in os.environ.get("HELDOUT", "").split(",") if x)

import sys as _sys
_sys.path.insert(0, str(ROOT.parent.parent))
try:
    from src.prompts.templates import get_sophisme_naming_prompt, SOPHISMES_DEBAT
except Exception:
    get_sophisme_naming_prompt, SOPHISMES_DEBAT = None, []

SYS_CLASSIF = (
    "Tu classes une affirmation de débat politique dans UNE catégorie parmi : "
    "STATISTIQUE, JURIDIQUE, FAIT_HISTORIQUE, DOCTRINE, CONSENSUS_SCIENCE, LOGIQUE, OPINION, NON_FAIT. "
    "Un chiffre/taux/budget = STATISTIQUE. Le contenu d'une loi/règlement = JURIDIQUE. Un sophisme/"
    "attaque personnelle = LOGIQUE. Un jugement de valeur assumé = OPINION. Une idéologie/croyance = "
    "DOCTRINE. Réponds le nom EXACT de la catégorie et RIEN d'autre."
)
SYS_ANALYSE = (
    "Tu es un fact-checker neutre et rigoureux. À partir d'une affirmation et de ses sources, produis "
    "un verdict JSON strict {\"verdict\": ..., \"biais_detecte\": ... ou null, \"explanation_short\": ...}. "
    "Verdicts : VRAI, FAUX, TROMPEUR, IMPRECIS, CONTESTE, NON_VERIFIABLE, BIAIS, OPINION. "
    "Confirme un fait vrai (VRAI) aussi nettement que tu démens un faux. Si un chiffre est exact mais "
    "arrondi/sorti de son contexte → IMPRECIS ou TROMPEUR, pas FAUX. N'invente aucune source."
)

def build():
    n_clf = n_ana = n_name = 0
    used = []
    with open(OUT, "w", encoding="utf-8") as f:
        for gp in sorted(glob.glob(str(GOLD / "*.json"))):
            vid = Path(gp).stem
            if vid in HELDOUT:
                continue
            used.append(vid)
            gold = json.loads(Path(gp).read_text(encoding="utf-8"))
            for c in gold.get("claims", []):
                claim = c.get("claim_clean", "")
                if not claim:
                    continue
                # 1) Exemple CLASSIFICATION (mirroir de l'appel classification du bot)
                f.write(json.dumps({"messages": [
                    {"role": "system", "content": SYS_CLASSIF},
                    {"role": "user", "content": f"AFFIRMATION : {claim}"},
                    {"role": "assistant", "content": c.get("category", "")},
                ], "meta": {"video_id": vid, "claim_id": c.get("id"), "kind": "classif"}},
                    ensure_ascii=False) + "\n")
                n_clf += 1
                # 2) Exemple ANALYSE (verdict calibré)
                srcs = c.get("sources") or []
                src_block = ("\nSOURCES :\n" + "\n".join(f"- {u}" for u in srcs)) if srcs else ""
                out = {"verdict": c.get("expected_verdict"),
                       "biais_detecte": c.get("expected_bias"),
                       "explanation_short": c.get("rationale", "")}
                f.write(json.dumps({"messages": [
                    {"role": "system", "content": SYS_ANALYSE},
                    {"role": "user", "content": f"AFFIRMATION : {claim}{src_block}"},
                    {"role": "assistant", "content": json.dumps(out, ensure_ascii=False)},
                ], "meta": {"video_id": vid, "claim_id": c.get("id"), "kind": "analyse"}},
                    ensure_ascii=False) + "\n")
                n_ana += 1
                # 3) Exemple NOMMAGE DE SOPHISME (miroir EXACT de _name_sophisme) — anti-oubli
                if get_sophisme_naming_prompt and SOPHISMES_DEBAT:
                    eb = c.get("expected_bias")
                    target = None
                    if eb and eb in SOPHISMES_DEBAT:
                        target = eb                                   # positif : le bon sophisme
                    elif c.get("category") in ("STATISTIQUE", "JURIDIQUE", "FAIT_HISTORIQUE") and n_ana % 3 == 0:
                        target = "AUCUN"                              # négatif équilibré : pas de sophisme
                    if target:
                        f.write(json.dumps({"messages": [
                            {"role": "user", "content": get_sophisme_naming_prompt(claim)},
                            {"role": "assistant", "content": json.dumps({"sophisme": target}, ensure_ascii=False)},
                        ], "meta": {"video_id": vid, "claim_id": c.get("id"), "kind": "naming"}},
                            ensure_ascii=False) + "\n")
                        n_name += 1
    print(f"OK : {n_clf} classif + {n_ana} analyse + {n_name} nommage = {n_clf+n_ana+n_name} total → {OUT}")
    print(f"Vidéos incluses ({len(used)}) : {used}")
    if HELDOUT:
        print(f"Held-out exclus : {sorted(HELDOUT)}")

if __name__ == "__main__":
    build()
