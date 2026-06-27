#!/usr/bin/env python3
"""Harnais d'évaluation du JUGEMENT du bot (isolé de la sélection/ASR).

Pour chaque claim du maître-étalon, on envoie `claim_clean` à /analyze et on compare
la catégorie / le verdict / le biais retournés aux valeurs attendues. Déterministe
(temperature 0). Écrit un rapport markdown + un résumé JSON.

Usage: python data/eval/run_judgment_eval.py data/eval/gold/<id>.json
"""
import sys, json, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SERVER = "http://localhost:5000"

# Tolérances : verdicts "proches" comptent pour 0.5
SOFT = {("VRAI", "IMPRECIS"), ("FAUX", "TROMPEUR"), ("TROMPEUR", "IMPRECIS"),
        ("CONTESTE", "NON_VERIFIABLE")}

# Canonicalisation des noms de biais (synonymes EN/FR) vs bias_list pour un matcher honnête.
try:
    import sys as _sys
    _sys.path.insert(0, str(ROOT.parent.parent))
    from src.prompts.bias_list import BIAS_LIST
    _BIAS_KEYS = list(BIAS_LIST.keys())
except Exception:
    _BIAS_KEYS = []

import re as _re
# Tokens génériques à ignorer (présents dans beaucoup de noms de biais) pour ne comparer
# que les tokens DISTINCTIFS (ex. "hominem", "ancrage", "paille").
_BIAS_STOP = {"biais", "effet", "attaque", "appel", "sophisme", "argument", "erreur",
              "personnelle", "des", "les", "une", "aux", "par", "sur", "pour"}

def _sig_tokens(name):
    toks = _re.findall(r"[a-zàâçéèêëîïôûùüÿœ]+", (name or "").lower())
    return {t for t in toks if len(t) >= 3 and t not in _BIAS_STOP}

def bias_match(got, exp):
    """Deux noms de biais désignent-ils le même sophisme ? Comparaison par tokens distinctifs
    (gère FR/EN, parenthèses, reformulations : 'Attaque personnelle (Ad Hominem)' == 'Attaque Ad Hominem')."""
    if not got or not exp:
        return False
    g, e = _sig_tokens(got), _sig_tokens(exp)
    if not g or not e:
        return False
    inter = g & e
    return len(inter) >= 2 or inter == min((g, e), key=len)

def norm_verdict(v):
    v = (v or "").upper().replace("-", "_")
    for a, b in [("É", "E"), ("é", "e"), ("È", "E"), ("è", "e")]:
        v = v.replace(a, b)
    return v.strip()

def post(path, payload):
    req = urllib.request.Request(SERVER + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())

def main():
    gold_path = Path(sys.argv[1])
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    vid, title = gold["video_id"], gold.get("title", "")
    claims = gold["claims"]

    # Repartir d'un historique propre pour éviter la contamination inter-claims
    try:
        post("/clear_history", {})
    except Exception:
        pass

    # Éval PARALLÈLE (web ACTIVÉ) : les recherches web réseau se chevauchent pendant
    # que le LLM (sérialisé par le GPU) tourne → bien plus rapide, mesure représentative.
    import os
    from concurrent.futures import ThreadPoolExecutor

    def evaluate_claim(c):
        exp_cat = (c.get("category") or "").upper()
        exp_verd = norm_verdict(c.get("expected_verdict"))
        exp_bias = c.get("expected_bias")
        try:
            res = post("/analyze", {"affirmation": c["claim_clean"], "global_context": title})
            r = res.get("result", {}); a = r.get("analyse", {}) if isinstance(r.get("analyse"), dict) else {}
            got_cat = (r.get("category") or "").upper()
            got_verd = norm_verdict(a.get("verdict"))
            got_bias = a.get("biais_detecte")
        except Exception as e:
            got_cat, got_verd, got_bias = f"ERR:{e}", "", None
        cm = got_cat == exp_cat
        if got_verd == exp_verd:
            vm = 1.0
        elif (got_verd, exp_verd) in SOFT or (exp_verd, got_verd) in SOFT:
            vm = 0.5
        else:
            vm = 0.0
        bm = bool(exp_bias) and bias_match(got_bias, exp_bias)
        row = {"id": c["id"], "claim": c["claim_clean"][:80],
               "cat": f"{got_cat}{'=' if cm else '≠'}{exp_cat}",
               "verd": f"{got_verd}{'=' if vm==1 else '~' if vm==0.5 else '≠'}{exp_verd}",
               "bias": f"{got_bias or '-'} / {exp_bias or '-'}"}
        return {"cm": bool(cm), "vm": vm, "has_bias": bool(exp_bias), "bm": bm, "row": row}

    workers = int(os.environ.get("EVAL_WORKERS", "6"))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(evaluate_claim, claims))
    rows = [x["row"] for x in results]
    cat_ok = sum(1 for x in results if x["cm"])
    verd_score = sum(x["vm"] for x in results)
    bias_total = sum(1 for x in results if x["has_bias"])
    bias_ok = sum(1 for x in results if x["bm"])

    n = len(claims)
    summ = {"video_id": vid, "n": n,
            "cat_acc": round(100*cat_ok/n, 1) if n else 0,
            "verd_acc": round(100*verd_score/n, 1) if n else 0,
            "bias_acc": round(100*bias_ok/bias_total, 1) if bias_total else None,
            "ts": time.strftime("%Y%m%d_%H%M%S")}

    (ROOT / "runs" / f"{vid}_{summ['ts']}.json").write_text(
        json.dumps({"summary": summ, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [f"# Eval {vid} — {summ['ts']}", "",
          f"- Catégorie : **{summ['cat_acc']}%**  ({cat_ok}/{n})",
          f"- Verdict : **{summ['verd_acc']}%**",
          f"- Biais : **{summ['bias_acc']}%**  ({bias_ok}/{bias_total})" if bias_total else "- Biais : n/a", "",
          "| id | claim | cat (got≷exp) | verdict | biais got/exp |",
          "|----|-------|---------------|---------|----------------|"]
    for r in rows:
        md.append(f"| {r['id']} | {r['claim']} | {r['cat']} | {r['verd']} | {r['bias']} |")
    (ROOT / "reports" / f"{vid}_{summ['ts']}.md").write_text("\n".join(md), encoding="utf-8")

    print(json.dumps(summ, ensure_ascii=False))

if __name__ == "__main__":
    main()
