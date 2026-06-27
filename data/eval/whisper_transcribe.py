#!/usr/bin/env python3
"""Transcription Whisper (le VRAI pipeline du bot) d'une vidéo YouTube → transcript propre.
Bien meilleur que les sous-titres VTT auto (noms/chiffres corrects) ET aligné sur l'inférence.
Usage: WHISPER_DEVICE=cuda|cpu python data/eval/whisper_transcribe.py <video_id>
"""
import sys, os
os.environ.setdefault("WHISPER_DEVICE", "cpu")
os.environ.setdefault("WHISPER_COMPUTE_TYPE", "int8")
sys.path.insert(0, ".")
from pathlib import Path
import yt_dlp
from src.ingestion.audio_parser import transcribe_audio_streaming

vid = sys.argv[1]
audio_dir = Path("data/audio"); audio_dir.mkdir(parents=True, exist_ok=True)
target = audio_dir / f"{vid}.mp3"
if not target.exists():
    print(f"[{vid}] téléchargement audio…")
    opts = {"quiet": True, "no_warnings": True, "format": "bestaudio/best",
            "outtmpl": str(audio_dir / "%(id)s.%(ext)s"),
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "128"}]}
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([f"https://www.youtube.com/watch?v={vid}"])

print(f"[{vid}] transcription Whisper ({os.environ['WHISPER_DEVICE']})…")
segs = []
transcribe_audio_streaming(str(target), lambda item: segs.append(item))

def ts(s):
    s = float(s or 0); return f"{int(s//60):02d}:{int(s%60):02d}"

out = f"data/eval/inputs/{vid}_transcript.txt"
Path(out).write_text("\n".join(f"[{ts(x.get('start'))}] {x.get('text','').strip()}" for x in segs), encoding="utf-8")
print(f"[{vid}] {len(segs)} segments Whisper → {out}")
