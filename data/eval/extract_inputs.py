#!/usr/bin/env python3
"""Extrait le transcript et la sortie actuelle du bot depuis le serveur live (/history)
ou depuis un fichier history.json, vers data/eval/inputs/<id>_*.
Usage: python data/eval/extract_inputs.py <video_id> [history.json]
"""
import sys, json, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
vid = sys.argv[1] if len(sys.argv) > 1 else "F-hsYpOya0M"

def load_history(src):
    if src and Path(src).exists():
        return json.loads(Path(src).read_text(encoding="utf-8"))
    with urllib.request.urlopen("http://localhost:5000/history", timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))

data = load_history(sys.argv[2] if len(sys.argv) > 2 else None)

def ts(s):
    s = float(s or 0); return f"{int(s//60):02d}:{int(s%60):02d}"

# Transcript
tx = [it for it in data if it.get("type") == "transcription"]
tx.sort(key=lambda x: x.get("video_timestamp", 0))
lines = []
for it in tx:
    spk = it.get("speaker")
    pre = f"({spk}) " if spk else ""
    lines.append(f"[{ts(it.get('video_timestamp'))}] {pre}{it.get('affirmation','').strip()}")
(ROOT / "inputs" / f"{vid}_transcript.txt").write_text("\n".join(lines), encoding="utf-8")

# Sortie bot (analyses)
out = []
for it in data:
    if it.get("type") == "analyse" and it.get("status") == "done":
        r = it.get("result", {}); a = r.get("analyse", {})
        if not isinstance(a, dict):
            continue
        out.append({
            "claim": it.get("affirmation", ""),
            "category": r.get("category"),
            "verdict": a.get("verdict"),
            "biais": a.get("biais_detecte"),
            "explanation_short": a.get("explanation_short"),
            "video_timestamp": it.get("video_timestamp"),
            "n_web_sources": (r.get("web_sources") is not None),
        })
(ROOT / "inputs" / f"{vid}_bot_output.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"OK : {len(tx)} segments transcript, {len(out)} analyses bot extraites pour {vid}")
print(f" -> inputs/{vid}_transcript.txt")
print(f" -> inputs/{vid}_bot_output.json")
