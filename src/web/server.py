import os
import sys
import asyncio
import logging
import re
import threading
import json
import subprocess
import webbrowser
from pathlib import Path
from typing import List, Dict, Any, Union, Optional
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Ensure project root is in path for imports
current_dir = Path(__file__).parent.absolute()
project_root = current_dir.parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

# Imports from project modules
from src.core.orchestrator import AnalysisOrchestrator
from src.ingestion.vtt_parser import ingest_from_local_vtt
from src.tools.context_fetcher import fetch_speaker_background, guess_speakers_from_filename
from src.tools.news_fetcher import fetch_context_news
from src.utils import Config, validate_text, format_affirmation, AnalysisError, ApiHealthManager
from src.ingestion.youtube_parser import extract_video_id, get_youtube_metadata, fetch_youtube_transcript_as_sentences
from src.core.stream_engine import background_analyze_task
from src.core.history_manager import HistoryManager

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- RÉDUCTION DU BRUIT DANS LA CONSOLE ---
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("src.core.providers.groq_provider").setLevel(logging.WARNING)
logging.getLogger("src.core.providers.mistral_provider").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.WARNING)  # Désactive les logs de requêtes web (GET /status)
logging.getLogger("primp").setLevel(logging.WARNING)     # Désactive les logs d'URL de DuckDuckGo

# Flask App setup
app = Flask(__name__, 
            template_folder=str(project_root / 'src' / 'web' / 'templates'),
            static_folder=str(project_root / 'src' / 'web' / 'static'))

app.config['UPLOAD_FOLDER'] = project_root / 'data' / 'uploads'
app.config['UPLOAD_FOLDER'].mkdir(exist_ok=True, parents=True)

# API Status global state
API_STATUS = {
    "mistral": {"status": "unknown", "message": "Vérification non effectuée."},
    "groq": {"status": "unknown", "message": "Vérification non effectuée."}
}

# Global State
history_manager = HistoryManager()
history_lock = threading.Lock()

background_loop: Optional[asyncio.AbstractEventLoop] = None
orchestrator: Optional[AnalysisOrchestrator] = None
result_dir = project_root / 'src' / 'results'
result_dir.mkdir(exist_ok=True, parents=True)

current_analysis_future = None
current_analysis_task: Optional[asyncio.Task] = None  # asyncio.Task réel (annulable depuis n'importe quel thread)
task_lock = threading.Lock()


async def _cancellable_wrapper(coro) -> None:
    """
    Enveloppe la coroutine principale et stocke le Task asyncio courant
    dans current_analysis_task afin qu'il soit annulable depuis n'importe quel thread
    via background_loop.call_soon_threadsafe(task.cancel).
    """
    global current_analysis_task
    this_task = asyncio.current_task()
    with task_lock:
        current_analysis_task = this_task
    try:
        await coro
    except asyncio.CancelledError:
        logger.info("[Gestion Tâches] Tâche annulée proprement (CancelledError reçue).")
    finally:
        with task_lock:
            if current_analysis_task is this_task:
                current_analysis_task = None


def cancel_current_analysis():
    """
    Annule l'analyse en cours de façon fiable, qu'elle soit démarrée ou non.
    - Avant démarrage : annule le concurrent.futures.Future.
    - Après démarrage : annule l'asyncio.Task via call_soon_threadsafe (seul moyen sûr cross-thread).
    """
    global current_analysis_future, current_analysis_task
    with task_lock:
        task = current_analysis_task
        future = current_analysis_future
        current_analysis_task = None
        current_analysis_future = None

    if task is not None and background_loop is not None and not background_loop.is_closed():
        background_loop.call_soon_threadsafe(task.cancel)
        logger.info("[Gestion Tâches] asyncio.Task.cancel() envoyé via call_soon_threadsafe.")
    elif future is not None and not future.done():
        future.cancel()
        logger.info("[Gestion Tâches] concurrent.futures.Future.cancel() (tâche pas encore démarrée).")

# ==============================================================================
# BACKGROUND LOOP & INITIALIZATION
# ==============================================================================

def start_background_loop(loop: asyncio.AbstractEventLoop):
    """Runs the background asyncio loop forever."""
    asyncio.set_event_loop(loop)
    loop.run_forever()

async def initialize_orchestrator_async():
    """Initializes the orchestrator inside the background loop."""
    global orchestrator
    try:
        if Config.LLM_MODE == "local":
            orchestrator = await AnalysisOrchestrator.create()
        else:
            api_key = os.environ.get("MISTRAL_API_KEY")
            if not api_key:
                logger.error("MISTRAL_API_KEY environment variable is not set.")
                return
            orchestrator = await AnalysisOrchestrator.create(api_key=api_key)
        logger.info(f"AnalysisOrchestrator initialized successfully in background loop (mode={Config.LLM_MODE}).")
    except Exception as e:
        logger.exception(f"Failed to initialize orchestrator: {e}")

def ensure_background_loop():
    """Ensures the background loop is running and orchestrator is initialized."""
    global background_loop
    if background_loop is None:
        background_loop = asyncio.new_event_loop()
        t = threading.Thread(target=start_background_loop, args=(background_loop,), daemon=True)
        t.start()
        logger.info("Background event loop started.")
        
        # Initialize orchestrator in the background loop
        future = asyncio.run_coroutine_threadsafe(initialize_orchestrator_async(), background_loop)
        try:
            future.result(timeout=20)
        except Exception as e:
            # Set status to error if initialization fails
            API_STATUS["mistral"]["status"] = "error"
            API_STATUS["mistral"]["message"] = f"Échec de l'initialisation : {e}"
            API_STATUS["groq"]["status"] = "error" # Assuming similar failure can occur for Groq
            logger.error(f"Timeout or error waiting for orchestrator initialization: {e}")

# ==============================================================================
# THREAD-SAFE HISTORY HELPERS
# ==============================================================================

def safe_add_history(item: Dict[str, Any]):
    with history_lock:
        history_manager.add_to_history(item)

def safe_update_history(item_id: int, updates: Dict[str, Any]):
    with history_lock:
        history_manager.update_item(item_id, updates)

def safe_get_history() -> List[Dict[str, Any]]:
    with history_lock:
        return history_manager.get_history()

def safe_clear_history():
    with history_lock:
        history_manager.clear_history()

def safe_get_formatted_history(limit: int = 5, speaker: Optional[str] = None) -> List[Dict[str, str]]:
    """Historique conversationnel formaté.
    Si `speaker` est fourni, on filtre sur ses interventions précédentes (P7) —
    la liste sera moins fournie mais plus pertinente pour la détection de
    contradictions intra-débat.
    """
    with history_lock:
        if speaker:
            return history_manager.get_formatted_history_by_speaker(speaker, limit=10)
        return history_manager.get_formatted_history(limit)

# ==============================================================================
# ROUTES
# ==============================================================================

@app.route('/')
def index():
    # Update API_STATUS from ApiHealthManager before rendering
    health_manager = ApiHealthManager()
    health_manager.check_and_update_fallback("groq")
    health_manager.check_and_update_fallback("mistral")
    
    groq_health = health_manager.get_provider_health("groq")
    mistral_health = health_manager.get_provider_health("mistral")

    API_STATUS["mistral"].update({
        "status": "ok" if not mistral_health["fallback_active"] else "fallback_active",
        "message": "Mistral API est opérationnelle." if not mistral_health["fallback_active"] else f"Mistral est en mode fallback (cooldown restant {health_manager.get_cooldown_remaining('mistral'):.0f}s).",
        "error_count": mistral_health["error_count"]
    })
    API_STATUS["groq"].update({
        "status": "ok" if not groq_health["fallback_active"] else "fallback_active",
        "message": "Groq API est opérationnelle." if not groq_health["fallback_active"] else f"Groq est en mode fallback (cooldown restant {health_manager.get_cooldown_remaining('groq'):.0f}s).",
        "error_count": groq_health["error_count"]
    })

    return render_template('index.html', api_status=API_STATUS)

@app.route('/app')
def mobile_app():
    health_manager = ApiHealthManager()
    health_manager.check_and_update_fallback("groq")
    health_manager.check_and_update_fallback("mistral")
    groq_health = health_manager.get_provider_health("groq")
    mistral_health = health_manager.get_provider_health("mistral")
    api_status = {
        "mistral": {"status": "ok" if not mistral_health["fallback_active"] else "fallback_active"},
        "groq":    {"status": "ok" if not groq_health["fallback_active"] else "fallback_active"},
    }
    return render_template('app.html', api_status=api_status)

@app.route('/cancel', methods=['POST'])
def cancel_analysis():
    """Arrête l'analyse en cours (appelé par le client mobile)."""
    cancel_current_analysis()
    logger.info("[Mobile] Analyse annulée par le client.")
    return jsonify({"message": "cancelled"})

@app.route('/api/status', methods=['GET'])
def get_api_status():
    """Returns the current status of the external APIs."""
    health_manager = ApiHealthManager()
    
    # Ensure cooldowns are checked before returning status
    health_manager.check_and_update_fallback("groq")
    health_manager.check_and_update_fallback("mistral")

    groq_health = health_manager.get_provider_health("groq")
    mistral_health = health_manager.get_provider_health("mistral")

    current_api_status = {
        "mistral": {
            "status": "ok" if not mistral_health["fallback_active"] else "fallback_active",
            "message": "Mistral API est opérationnelle." if not mistral_health["fallback_active"] else f"Mistral est en mode fallback (cooldown restant {health_manager.get_cooldown_remaining('mistral'):.0f}s).",
            "error_count": mistral_health["error_count"],
        },
        "groq": {
            "status": "ok" if not groq_health["fallback_active"] else "fallback_active",
            "message": "Groq API est opérationnelle." if not groq_health["fallback_active"] else f"Groq est en mode fallback (cooldown restant {health_manager.get_cooldown_remaining('groq'):.0f}s).",
            "error_count": groq_health["error_count"]
        }
    }
    return jsonify(current_api_status)


def _download_youtube_audio(video_id: str) -> Path:
    """Télécharge l'audio d'une vidéo YouTube en MP3 dans data/audio/.
    Réutilise le fichier s'il existe déjà."""
    audio_dir = project_root / 'data' / 'audio'
    audio_dir.mkdir(parents=True, exist_ok=True)
    target = audio_dir / f"{video_id}.mp3"
    if target.exists():
        logger.info(f"[Audio] Réutilisation de {target}")
        return target

    import yt_dlp
    ydl_opts = {
        'quiet': True, 'no_warnings': True,
        'format': 'bestaudio/best',
        'outtmpl': str(audio_dir / '%(id)s.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '128',
        }],
    }
    proxy = os.environ.get('YOUTUBE_PROXY')
    if proxy:
        ydl_opts['proxy'] = proxy
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
    if not target.exists():
        raise FileNotFoundError(f"Audio MP3 introuvable après téléchargement: {target}")
    return target


@app.route('/process_youtube', methods=['POST'])
def process_youtube():
    ensure_background_loop()

    data = request.json
    url = data.get('url')
    if not url:
        return jsonify({"error": "Missing 'url'"}), 400

    # Flags optionnels (défaut : tout en local pour ne pas dépendre des sous-titres
    # auto YouTube qui sont bruités).
    use_whisper = bool(data.get('use_whisper', True))
    use_diarization = bool(data.get('use_diarization', True))

    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({"error": "Invalid YouTube URL"}), 400

    try:
        logger.info(f"Processing YouTube Video ID: {video_id} (whisper={use_whisper}, diarize={use_diarization})")

        # Récupération synchrone du titre et de la date pour l'interface utilisateur
        title, date = get_youtube_metadata(video_id)
        logger.info(f"Fetched Video Title: {title}, Date: {date}")

        # Arrêter la tâche d'analyse de la vidéo précédente si elle tourne encore
        cancel_current_analysis()

        # Reset complet : mémoire + fichier history.json
        safe_clear_history()
        history_file = result_dir / 'history.json'
        try:
            if history_file.exists():
                history_file.unlink()
                logger.info("[Reset] Fichier history.json supprimé pour la nouvelle session.")
        except Exception as e:
            logger.warning(f"[Reset] Impossible de supprimer history.json : {e}")

        # START NEW CONTEXT LOGIC
        async def prepare_and_run(vid, v_title, v_date):
            try:
                # Status item visible pendant que Whisper transcrit en
                # streaming. Plus de blocage : l'analyse LLM démarre dès
                # la 1ère phrase qui sort du modèle.
                status_item_id = None
                if use_whisper:
                    safe_add_history({
                        "timestamp": datetime.now().isoformat(),
                        "type": "processing_status",
                        "stage": "whisper",
                        "message": "🎙️ Transcription Whisper en streaming — l'analyse démarre dès la 1ère phrase…",
                        "video_timestamp": 0.0,
                    })
                    status_item_id = safe_get_history()[-1]["id"]

                # Queue de phrases — alimentée en streaming par Whisper
                # (use_whisper) ou en batch par le parser VTT (sinon).
                sentence_queue: asyncio.Queue = asyncio.Queue()
                loop = asyncio.get_running_loop()

                # Préparation contexte : noms d'invités via heuristique sur le titre
                guessed_names = guess_speakers_from_filename(v_title)
                speaker_names = guessed_names if guessed_names else []
                base_global_context = f"VIDÉO : {v_title}\nDATE DE DIFFUSION : {v_date}\n"
                search_subject = " ".join(speaker_names) if speaker_names else v_title

                # Récupération contexte d'actualité (10-20s) AVANT de lancer
                # le pipeline car Phase 0 (extract_topic) en a besoin.
                logger.info("Récupération du contexte d'actualité…")
                news_context = await fetch_context_news(orchestrator, v_date, specific_subject=search_subject)
                base_global_context += f"\nCONTEXTE D'ACTUALITÉ (Recherche Automatique) :\n{news_context}\n\n"
                safe_add_history({
                    "timestamp": datetime.now().isoformat(),
                    "type": "context_update",
                    "news_context": news_context,
                    "video_timestamp": 0.0
                })
                if speaker_names:
                    backgrounds = await asyncio.gather(*(fetch_speaker_background(orchestrator, name) for name in speaker_names))
                    base_global_context += "\n".join(backgrounds)
                logger.info(f"Global Context Prepared: {base_global_context[:100]}...")

                # ===== PRODUCER : alimente la queue =====
                async def produce_via_whisper():
                    audio_path = await asyncio.to_thread(_download_youtube_audio, vid)
                    counter = {"n": 0}

                    # === DIARISATION + IDENTIFICATION DES LOCUTEURS ===
                    # 1) Diarisation sur l'audio complet → "Locuteur N" + empreintes vocales.
                    # 2) Reconnaissance vocale INSTANTANÉE via la base d'empreintes (VoiceprintDB) :
                    #    une voix déjà vue est nommée dès t=0, avant qu'un nom soit prononcé.
                    # 3) Pour les inconnus : identification par le LLM sur le contexte (liaison à la
                    #    volée), puis ré-étiquetage rétroactif + sauvegarde de l'empreinte (auto-apprentissage).
                    speaker_lookup = None
                    centroids = {}
                    name_map = {}          # "Locuteur N" -> vrai nom (rempli au fil de l'eau)
                    labeled_lines = []     # accumulation "[Locuteur N] texte" pour l'identification LLM
                    id_state = {"done": False}
                    vdb = None
                    if use_diarization:
                        if status_item_id is not None:
                            safe_update_history(status_item_id, {
                                "message": "🗣️ Identification des locuteurs (diarisation locale)…",
                            })
                        from src.ingestion.audio_parser import diarize_audio_to_lookup
                        from src.ingestion.voiceprints import VoiceprintDB, MATCH_THRESHOLD
                        speaker_lookup, centroids = await asyncio.to_thread(diarize_audio_to_lookup, str(audio_path))
                        # Reconnaissance vocale immédiate (base auto-construite)
                        try:
                            vdb = VoiceprintDB()
                            for lbl, emb in centroids.items():
                                nom, score = vdb.match(emb, candidates=speaker_names or None)
                                if nom and score >= MATCH_THRESHOLD:
                                    name_map[lbl] = nom
                                    logger.info(f"[Voix reconnue] {lbl} → {nom} (sim {score:.2f})")
                        except Exception as e:
                            logger.warning(f"Reconnaissance vocale indisponible : {e}")

                    def _relabel_history(mapping):
                        """Ré-étiquette rétroactivement les items déjà affichés (passé → vrai nom)."""
                        for it in safe_get_history():
                            sp = it.get("speaker")
                            if sp in mapping and it.get("id") is not None:
                                safe_update_history(it["id"], {"speaker": mapping[sp]})

                    async def _identify_unknowns():
                        """1 appel LLM : nomme les Locuteurs encore anonymes via le contexte,
                        sauvegarde leurs empreintes (auto-apprentissage), ré-étiquette le passé."""
                        if id_state["done"]:
                            return
                        id_state["done"] = True
                        unknown = [l for l in centroids if l not in name_map]
                        if not unknown or not labeled_lines:
                            return
                        mapping = await orchestrator.identify_speakers(
                            "\n".join(labeled_lines[:45]), ", ".join(speaker_names))
                        applied = {}
                        for lbl, nom in mapping.items():
                            if lbl in centroids and lbl not in name_map:
                                name_map[lbl] = nom
                                applied[lbl] = nom
                                # Anti-pollution : on ne PERSISTE l'empreinte que si le nom est
                                # corroboré par le titre (sinon on l'affiche, mais on ne l'apprend pas).
                                corroborated = any(
                                    tok and (tok.lower() in nom.lower() or nom.lower() in tok.lower())
                                    for tok in (speaker_names or []))
                                if vdb is not None and nom.lower() != "journaliste" and corroborated:
                                    try:
                                        vdb.add(nom, centroids[lbl])
                                    except Exception:
                                        pass
                        if vdb is not None and applied:
                            try:
                                vdb.save()
                            except Exception:
                                pass
                        if applied:
                            logger.info(f"[Locuteurs identifiés] {applied}")
                            _relabel_history(applied)

                    def on_segment(item):
                        counter["n"] += 1
                        lbl = None
                        if speaker_lookup is not None:
                            lbl = speaker_lookup(float(item.get("start", 0.0)))
                        spk = name_map.get(lbl, lbl) if lbl else item.get("speaker")
                        text = item.get("text", "").strip()
                        if lbl:
                            labeled_lines.append(f"[{lbl}] {text}")
                            # Déclenche l'identification LLM une fois assez de contexte accumulé.
                            if not id_state["done"] and len(labeled_lines) >= 30:
                                asyncio.run_coroutine_threadsafe(_identify_unknowns(), loop)
                        tx_item = {
                            "id": counter["n"],
                            "timestamp": datetime.now().isoformat(),
                            "affirmation": text,
                            "status": "pending",
                            "video_timestamp": float(item.get("start", 0.0)),
                            "type": "transcription",
                            "speaker": spk,
                        }
                        # Push thread-safe depuis le thread Whisper vers la queue asyncio
                        asyncio.run_coroutine_threadsafe(sentence_queue.put(tx_item), loop)

                    if status_item_id is not None:
                        safe_update_history(status_item_id, {
                            "message": "🎙️ Transcription Whisper en streaming — l'analyse démarre dès la 1ère phrase…",
                        })
                    from src.ingestion.audio_parser import transcribe_audio_streaming
                    await asyncio.to_thread(transcribe_audio_streaming, str(audio_path), on_segment)
                    # Vidéo courte (<30 segments) : identifier quand même en fin de transcription.
                    if use_diarization and not id_state["done"]:
                        await _identify_unknowns()
                    await sentence_queue.put(None)
                    if status_item_id is not None:
                        safe_update_history(status_item_id, {
                            "stage": "done_transcription",
                            "message": f"✅ Transcription terminée : {counter['n']} segments. Analyse en cours…",
                        })

                async def produce_via_vtt():
                    sents = await asyncio.to_thread(fetch_youtube_transcript_as_sentences, vid)
                    if not sents:
                        logger.error("Could not extract sentences from transcript")
                        await sentence_queue.put(None)
                        return
                    for i, sentence in enumerate(sents):
                        await sentence_queue.put({
                            "id": i + 1,
                            "timestamp": datetime.now().isoformat(),
                            "affirmation": sentence.get('text', '').strip(),
                            "status": "pending",
                            "video_timestamp": float(sentence.get('start', 0.0)),
                            "type": "transcription",
                            "speaker": sentence.get('speaker'),
                        })
                    await sentence_queue.put(None)

                # ===== Producer + Consumer en parallèle =====
                producer = produce_via_whisper() if use_whisper else produce_via_vtt()
                consumer = background_analyze_task(
                    sentence_queue, vid, base_global_context,
                    orchestrator, result_dir,
                    safe_add_history, safe_update_history, safe_get_history, safe_get_formatted_history
                )
                try:
                    await asyncio.gather(producer, consumer)
                except Exception as e:
                    logger.error(f"[{vid}] Pipeline error: {e}")
                    safe_add_history({
                        "timestamp": datetime.now().isoformat(),
                        "type": "error",
                        "message": f"Erreur pipeline : {e}",
                        "video_timestamp": 0.0
                    })
            except Exception as e:
                logger.exception(f"[{vid}] Error in prepare_and_run: {e}")

        global current_analysis_future
        with task_lock:
            current_analysis_task = None  # sera mis à jour par _cancellable_wrapper
            current_analysis_future = asyncio.run_coroutine_threadsafe(
                _cancellable_wrapper(prepare_and_run(video_id, title, date)),
                background_loop
            )
        # END NEW CONTEXT LOGIC
        
        return jsonify({
            "message": "Analysis started in background", 
            "video_id": video_id,
            "video_title": title
        })

    except Exception as e:
        logger.exception("Error processing YouTube video")
        return jsonify({"error": str(e)}), 500

@app.route('/status', methods=['GET'])
def get_analysis_status():
    return jsonify({"results": safe_get_history()})

@app.route('/analyze', methods=['POST'])
def analyze_affirmation():
    ensure_background_loop()
    
    data = request.json
    if not data or 'affirmation' not in data:
        return jsonify({"error": "Missing 'affirmation'"}), 400

    affirmation_input = data['affirmation']
    global_context = data.get('global_context')
    formatted_history = safe_get_formatted_history()

    # Define the async job
    async def do_analyze():
        return await orchestrator.analyze(
            affirmation=affirmation_input,
            history=formatted_history,
            global_context=global_context
        )

    try:
        # Submit and wait
        future = asyncio.run_coroutine_threadsafe(do_analyze(), background_loop)
        result = future.result(timeout=120) # 120s : le pipeline local complet (classif + web + analyse) dépasse 60s sur un 14B
        
        processed_result = {
            "timestamp": datetime.now().isoformat(),
            "affirmation": format_affirmation(affirmation_input),
            "result": result
        }
        safe_add_history(processed_result)
        
        return jsonify(processed_result)

    except Exception as e:
        logger.exception("Analysis error")
        return jsonify({"error": str(e)}), 500


@app.route('/upload_audio', methods=['POST'])
def upload_audio_file():
    """Téléverse un fichier audio (MP3/MP4/WAV) et lance le pipeline complet
    Whisper + diarisation locale + analyse LLM. Tout en local."""
    ensure_background_loop()

    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Invalid file"}), 400

    # Flag diarisation (défaut : oui)
    use_diarization = request.form.get('diarize', 'true').lower() == 'true'

    filename = secure_filename(file.filename)
    filepath = app.config['UPLOAD_FOLDER'] / filename
    file.save(filepath)

    cancel_current_analysis()
    safe_clear_history()

    async def process_audio_task(fpath: str, filename_stem: str):
        try:
            safe_add_history({
                "timestamp": datetime.now().isoformat(),
                "type": "processing_status",
                "stage": "whisper",
                "message": "🎙️ Transcription Whisper en streaming — l'analyse démarre dès la 1ère phrase…",
                "video_timestamp": 0.0,
            })
            status_item_id = safe_get_history()[-1]["id"]

            sentence_queue: asyncio.Queue = asyncio.Queue()
            loop = asyncio.get_running_loop()

            # Contexte d'actualité (~10-20s) avant de lancer Whisper, car
            # Phase 0 (extract_topic) en a besoin.
            guessed_names = guess_speakers_from_filename(filename_stem)
            speaker_names = guessed_names if guessed_names else []
            base_global_context = f"FICHIER : {filename_stem}\n"
            search_subject = " ".join(speaker_names) if speaker_names else filename_stem

            logger.info("[Audio] Récupération du contexte d'actualité...")
            news_context = await fetch_context_news(orchestrator, filename_stem, specific_subject=search_subject)
            base_global_context += f"\nCONTEXTE D'ACTUALITÉ (Recherche Automatique) :\n{news_context}\n\n"
            safe_add_history({
                "timestamp": datetime.now().isoformat(),
                "type": "context_update",
                "news_context": news_context,
                "video_timestamp": 0.0,
            })
            if speaker_names:
                backgrounds = await asyncio.gather(*(fetch_speaker_background(orchestrator, name) for name in speaker_names))
                base_global_context += "\n" + "\n".join(backgrounds)

            # Producer Whisper streaming : push chaque segment dans la queue
            # dès qu'il sort du modèle.
            counter = {"n": 0}

            def on_segment(item):
                counter["n"] += 1
                tx_item = {
                    "id": counter["n"],
                    "timestamp": datetime.now().isoformat(),
                    "affirmation": item.get("text", "").strip(),
                    "status": "pending",
                    "video_timestamp": float(item.get("start", 0.0)),
                    "type": "transcription",
                    "speaker": item.get("speaker"),
                }
                asyncio.run_coroutine_threadsafe(sentence_queue.put(tx_item), loop)

            async def produce_whisper():
                from src.ingestion.audio_parser import transcribe_audio_streaming
                logger.info(f"[Audio] Whisper streaming sur {fpath} (diarize={use_diarization})...")
                await asyncio.to_thread(transcribe_audio_streaming, fpath, on_segment)
                await sentence_queue.put(None)
                safe_update_history(status_item_id, {
                    "stage": "done_transcription",
                    "message": f"✅ Transcription terminée : {counter['n']} segments. Analyse en cours…",
                })

            consumer = background_analyze_task(
                sentence_queue, filename_stem, base_global_context,
                orchestrator, result_dir,
                safe_add_history, safe_update_history, safe_get_history, safe_get_formatted_history,
            )

            await asyncio.gather(produce_whisper(), consumer)
        finally:
            try:
                if os.path.exists(fpath):
                    os.remove(fpath)
            except Exception:
                pass

    global current_analysis_future
    with task_lock:
        current_analysis_task = None
        current_analysis_future = asyncio.run_coroutine_threadsafe(
            _cancellable_wrapper(process_audio_task(str(filepath), Path(filename).stem)),
            background_loop,
        )

    return jsonify({
        "message": "Audio processing started",
        "filename": filename,
        "diarize": use_diarization,
    })


@app.route('/upload_vtt', methods=['POST'])
def upload_vtt_file():
    ensure_background_loop()
    
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    if file.filename == '' or not file.filename.endswith('.vtt'):
        return jsonify({"error": "Invalid file"}), 400
    
    filename = secure_filename(file.filename)
    filepath = app.config['UPLOAD_FOLDER'] / filename
    file.save(filepath)
    
    # Arrêter toute tâche d'analyse en cours
    cancel_current_analysis()

    try:
        sentences = ingest_from_local_vtt(str(filepath))
        safe_clear_history()

        async def process_vtt_task(fpath, sentences_list, filename_stem):
            try:
                # --- Création du producteur de phrases pour le VTT ---
                sentence_queue = asyncio.Queue()
                for i, sentence in enumerate(sentences_list):
                    transcription_item = {
                        "id": i + 1,
                        "timestamp": datetime.now().isoformat(),
                        "affirmation": sentence.get('text', '').strip(),
                        "status": "pending",
                        "video_timestamp": float(sentence.get('start', 0.0)),
                        "type": "transcription"
                    }
                    await sentence_queue.put(transcription_item)
                await sentence_queue.put(None) # Signal de fin

                # --- Préparation du contexte ---
                guessed_names = guess_speakers_from_filename(filename_stem)
                speaker_names = guessed_names if guessed_names else []
                
                base_global_context = f"FICHIER : {filename_stem}\n"
                
                # Respect absolu du DIRECT : On utilise UNIQUEMENT le nom du fichier à T=0
                search_subject = " ".join(speaker_names) if speaker_names else filename_stem

                # 2. Recherche ciblée
                logger.info("Récupération du contexte d'actualité pour VTT...")
                news_context = await fetch_context_news(orchestrator, filename_stem, specific_subject=search_subject)
                base_global_context += f"\nCONTEXTE D'ACTUALITÉ (Recherche Automatique) :\n{news_context}\n\n"

                # Envoi du contexte d'actualité au frontend pour affichage au survol
                safe_add_history({
                    "timestamp": datetime.now().isoformat(),
                    "type": "context_update",
                    "news_context": news_context,
                    "video_timestamp": 0.0
                })

                if speaker_names:
                    backgrounds = await asyncio.gather(*(fetch_speaker_background(orchestrator, name) for name in speaker_names))
                    base_global_context += "\n" + "\n".join(backgrounds)
                
                # --- Lancement de l'analyse ---
                await background_analyze_task(
                    sentence_queue, filename_stem, base_global_context,
                    orchestrator, result_dir,
                    safe_add_history, safe_update_history, safe_get_history, safe_get_formatted_history
                )
                
            finally:
                if os.path.exists(fpath):
                    os.remove(fpath) # Clean up the uploaded file

        global current_analysis_future
        with task_lock:
            current_analysis_task = None  # sera mis à jour par _cancellable_wrapper
            current_analysis_future = asyncio.run_coroutine_threadsafe(
                _cancellable_wrapper(process_vtt_task(str(filepath), sentences, Path(filename).stem)),
                background_loop
            )

        return jsonify({"message": "VTT processing started", "sentence_count": len(sentences)})

    except Exception as e:
        if os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({"error": str(e)}), 500

@app.route('/history', methods=['GET'])
def get_conversation_history():
    return jsonify(safe_get_history())

@app.route('/clear_history', methods=['POST'])
def clear_conversation_history():
    safe_clear_history()
    return jsonify({"message": "Conversation history cleared"})

if __name__ == '__main__':
    logger.info(f"Démarrage du serveur Web CodeCitoyen (mode LLM = {Config.LLM_MODE})...")
    if Config.LLM_MODE == "local":
        print("\n" + "="*80)
        print(f"🦙 MODE LOCAL — LLM via Ollama ({os.environ.get('OLLAMA_MODEL', 'mistral-nemo:12b')})")
        print("="*80)
        API_STATUS["mistral"] = {"status": "disabled", "message": "Mode local actif — Mistral cloud non utilisé."}
        API_STATUS["groq"] = {"status": "disabled", "message": "Mode local actif — Groq non utilisé."}
    else:
        print("\n" + "="*80)
        print("🚦 DIAGNOSTIC DES API AVANT LANCEMENT DU SERVEUR WEB 🚦")
        print("="*80)
        try:
            result = subprocess.run(
                [sys.executable, "check_api_status.py"],
                capture_output=True, text=True, check=False
            )
            print(result.stderr)
            try:
                status_data = json.loads(result.stdout)
                API_STATUS.update(status_data)
                logger.info(f"État des API mis à jour : {API_STATUS}")
            except (json.JSONDecodeError, TypeError):
                print("⚠️ ERREUR : Impossible de parser la sortie JSON du script de diagnostic.")
                API_STATUS["mistral"] = {"status": "error", "message": "Échec du script de diagnostic."}
                API_STATUS["groq"] = {"status": "error", "message": "Échec du script de diagnostic."}

            if result.returncode != 0:
                print("\n⚠️ ATTENTION : Le serveur web va démarrer, mais les analyses risquent de planter.")
        except FileNotFoundError:
            print("⚠️ AVERTISSEMENT : Le script 'check_api_status.py' est introuvable. Diagnostic ignoré.")
            API_STATUS["mistral"] = {"status": "unknown", "message": "Script de diagnostic introuvable."}
            API_STATUS["groq"] = {"status": "unknown", "message": "Script de diagnostic introuvable."}
        except Exception as e:
            print(f"⚠️ ERREUR : Impossible d'exécuter le diagnostic des API : {e}")

    ApiHealthManager() # Initialize the singleton ApiHealthManager
    ensure_background_loop()
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    threading.Timer(1.5, lambda: webbrowser.open("http://localhost:5000")).start()
    app.run(host='0.0.0.0', port=5000, debug=debug_mode)
