#!/usr/bin/env python3
"""
Script de test d'intégration — simulation live.

Simule un direct en injectant les phrases dans la queue au rythme
des timestamps VTT (accéléré par SPEED_FACTOR).

Usage:
    python scripts/run_live_test.py                          # VTT Zemmour existant
    python scripts/run_live_test.py --url <youtube_url>      # Télécharge et analyse
    python scripts/run_live_test.py --vtt <chemin.vtt>       # VTT local
    python scripts/run_live_test.py --speed 20               # 20x plus vite que le direct
"""
import asyncio
import sys
import json
import logging
import threading
import argparse
import glob
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# --- Chemins ---
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

from src.core.orchestrator import AnalysisOrchestrator
from src.core.stream_engine import background_analyze_task
from src.core.history_manager import HistoryManager
from src.ingestion.vtt_parser import ingest_from_local_vtt

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("primp").setLevel(logging.WARNING)
logger = logging.getLogger("live_test")

RESULT_DIR = PROJECT_ROOT / "data" / "test_results"
RESULT_DIR.mkdir(parents=True, exist_ok=True)

INPUT_DIR = PROJECT_ROOT / "data" / "input"

# ==============================================================================

def download_vtt(url: str) -> Path:
    """Télécharge le VTT d'une vidéo YouTube et retourne le chemin."""
    import yt_dlp
    ydl_opts = {
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitleslangs': ['fr'],
        'subtitlesformat': 'vtt',
        'skip_download': True,
        'outtmpl': str(INPUT_DIR / '%(title)s [%(id)s].%(ext)s'),
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        video_id = info.get('id')
        title = info.get('title', video_id)

    vtts = list(INPUT_DIR.glob(f"*{video_id}*.vtt"))
    if not vtts:
        raise FileNotFoundError(f"VTT introuvable après téléchargement pour {url}")
    return vtts[0], title, info.get('duration', 0)


async def feed_sentences(queue: asyncio.Queue, sentences: List[Dict[str, Any]], speed_factor: float):
    """
    Injecte les phrases dans la queue en respectant les timestamps relatifs.
    L'écart entre deux phrases est divisé par speed_factor.
    Invariant : l'ordre est toujours respecté, aucune phrase n'est sautée.
    """
    logger.info(f"[Producer] Début injection de {len(sentences)} phrases (x{speed_factor} vitesse).")
    prev_ts = sentences[0].get('start', 0.0) if sentences else 0.0

    for sentence in sentences:
        current_ts = sentence.get('start', prev_ts)
        gap = max(0.0, current_ts - prev_ts)
        sleep_time = gap / speed_factor

        if sleep_time > 0:
            await asyncio.sleep(sleep_time)

        await queue.put({
            "affirmation": sentence.get('text', ''),
            "video_timestamp": current_ts,
            "type": "transcription",
            "status": "pending",
            "speaker": sentence.get('speaker'),
            "timestamp": datetime.now().isoformat()
        })
        prev_ts = current_ts

    await queue.put(None)  # Signal de fin — NE PAS RETIRER
    logger.info("[Producer] Toutes les phrases injectées. Signal de fin envoyé.")


async def run_test(vtt_path: Optional[Path], title: str, speed_factor: float,
                   pre_sentences: Optional[List[Dict[str, Any]]] = None):
    """Lance l'analyse complète en mode streaming simulé."""
    logger.info(f"=== TEST LIVE : {title} ===")
    logger.info(f"Vitesse : x{speed_factor}")

    # 1. Source des phrases : VTT, ou phrases déjà transcrites (Whisper)
    if pre_sentences is not None:
        sentences = pre_sentences
        logger.info(f"[Source] {len(sentences)} phrases pré-transcrites (Whisper).")
    else:
        logger.info(f"VTT : {vtt_path}")
        sentences = ingest_from_local_vtt(str(vtt_path))

    if not sentences:
        logger.error("Aucune phrase extraite.")
        return
    logger.info(f"[Parser] {len(sentences)} phrases extraites (durée: {sentences[-1]['start']/60:.1f}min)")

    # 2. Contexte global (titre de la vidéo)
    global_context = f"Titre de l'émission : {title}"

    # 3. Initialiser l'orchestrateur
    logger.info("[Init] Initialisation de l'orchestrateur...")
    orchestrator = await AnalysisOrchestrator.create()
    logger.info("[Init] Orchestrateur prêt.")

    # 4. Historique thread-safe
    history_manager = HistoryManager(result_dir=RESULT_DIR)
    lock = threading.Lock()

    def safe_add(item):
        with lock: history_manager.add_to_history(item)
    def safe_update(item_id, updates):
        with lock: history_manager.update_item(item_id, updates)
    def safe_get():
        with lock: return history_manager.get_history()
    def safe_get_formatted(limit=5, speaker=None):
        with lock:
            if speaker:
                return history_manager.get_formatted_history_by_speaker(speaker, limit=10)
            return history_manager.get_formatted_history(limit)

    # 5. Lancer le producteur et le moteur en parallèle
    queue = asyncio.Queue(maxsize=50)

    producer = asyncio.create_task(
        feed_sentences(queue, sentences, speed_factor)
    )
    consumer = asyncio.create_task(
        background_analyze_task(
            sentence_producer=queue,
            video_id=(vtt_path.stem if vtt_path else title)[:30],
            global_context=global_context,
            orchestrator=orchestrator,
            result_dir=RESULT_DIR,
            safe_add_history=safe_add,
            safe_update_history=safe_update,
            safe_get_history=safe_get,
            safe_get_formatted_history=safe_get_formatted
        )
    )

    start = datetime.now()
    await asyncio.gather(producer, consumer)
    elapsed = (datetime.now() - start).total_seconds()

    logger.info(f"=== ANALYSE TERMINÉE en {elapsed:.0f}s ===")

    # 6. Rapport de résultats
    history = safe_get()
    analyses = [h for h in history if h.get('type') == 'analyse' and h.get('status') == 'done']
    errors = [h for h in history if h.get('status') == 'error']

    logger.info(f"[Résultats] {len(analyses)} analyses réussies, {len(errors)} erreurs")

    print("\n" + "="*80)
    print(f"RÉSULTATS — {title}")
    print("="*80)
    for a in analyses:
        ts = a.get('video_timestamp', 0)
        minutes = int(ts) // 60
        seconds = int(ts) % 60
        result = a.get('result', {})
        category = result.get('category', '?')
        analyse = result.get('analyse', {})
        verdict = analyse.get('verdict', '?')
        short = analyse.get('explanation_short', '')
        biais = analyse.get('biais_detecte')
        biais_str = f" | BIAIS: {biais}" if biais and biais != "AUCUN" else ""
        print(f"\n[{minutes:02d}:{seconds:02d}] [{category}] {a.get('affirmation', '')}")
        print(f"  → {verdict}{biais_str}")
        print(f"  {short}")

    if errors:
        print(f"\n--- {len(errors)} ERREUR(S) ---")
        for e in errors[:5]:
            print(f"  [{e.get('affirmation', '')[:60]}] → {e.get('result', {}).get('error', '?')}")

    # 7. Sauvegarde rapport final
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = RESULT_DIR / f"rapport_{(vtt_path.stem if vtt_path else title)[:40]}_{timestamp_str}.json"
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump({
            "titre": title,
            "speed_factor": speed_factor,
            "duree_analyse_s": elapsed,
            "nb_phrases": len(sentences),
            "nb_analyses": len(analyses),
            "nb_erreurs": len(errors),
            "analyses": analyses,
            "erreurs": errors
        }, f, indent=2, ensure_ascii=False)
    print(f"\nRapport complet : {report_path}")


def main():
    parser = argparse.ArgumentParser(description="Test live CodeCitoyen")
    parser.add_argument('--url', type=str, help="URL YouTube à analyser")
    parser.add_argument('--vtt', type=str, help="Chemin vers un fichier VTT local")
    parser.add_argument('--audio', type=str, help="Chemin vers fichier audio (MP3/WAV/MP4) — transcrit via faster-whisper")
    parser.add_argument('--diarize', action='store_true', help="Activer la diarisation pyannote (nécessite HF_TOKEN)")
    parser.add_argument('--speed', type=float, default=10.0,
                        help="Facteur d'accélération (défaut: 10 = 18min analysées en ~2min)")
    args = parser.parse_args()

    if args.audio:
        from src.ingestion.audio_parser import transcribe_audio_to_sentences
        audio_path = Path(args.audio)
        title = audio_path.stem
        logger.info(f"Transcription de {audio_path} via faster-whisper (diarize={args.diarize})...")
        sentences = transcribe_audio_to_sentences(str(audio_path), with_diarization=args.diarize)
        asyncio.run(run_test(None, title, args.speed, pre_sentences=sentences))
        return

    if args.url:
        logger.info(f"Téléchargement de {args.url}...")
        vtt_path, title, _ = download_vtt(args.url)
        logger.info(f"VTT téléchargé : {vtt_path}")
    elif args.vtt:
        vtt_path = Path(args.vtt)
        title = vtt_path.stem
    else:
        # Utilise le VTT déjà présent dans data/input/
        vtts = list(INPUT_DIR.glob("*.vtt"))
        if not vtts:
            print("Aucun VTT trouvé dans data/input/. Utilisez --url ou --vtt.")
            sys.exit(1)
        vtt_path = vtts[0]
        title = vtt_path.stem
        logger.info(f"VTT auto-détecté : {vtt_path.name}")

    asyncio.run(run_test(vtt_path, title, args.speed))


if __name__ == "__main__":
    main()
