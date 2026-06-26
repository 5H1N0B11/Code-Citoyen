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

    rows, cat_ok, verd_score, bias_ok, bias_total = [], 0, 0.0, 0, 0
    for c in claims:
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
        cat_ok += cm; verd_score += vm
        if exp_bias:
            bias_total += 1
            if got_bias and (got_bias.split("(")[0].strip().lower() in exp_bias.lower()
                             or exp_bias.split("(")[0].strip().lower() in (got_bias or "").lower()):
                bias_ok += 1
        rows.append({"id": c["id"], "claim": c["claim_clean"][:80],
                     "cat": f"{got_cat}{'=' if cm else '≠'}{exp_cat}",
                     "verd": f"{got_verd}{'=' if vm==1 else '~' if vm==0.5 else '≠'}{exp_verd}",
                     "bias": f"{got_bias or '-'} / {exp_bias or '-'}"})
        time.sleep(0.3)

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
