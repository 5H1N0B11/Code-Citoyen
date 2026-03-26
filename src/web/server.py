import os
import sys
import asyncio
import logging
import re
import threading
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Union, Optional
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename

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
from src.utils import Config, validate_text, format_affirmation, AnalysisError
from src.ingestion.youtube_parser import extract_video_id, get_youtube_metadata, fetch_youtube_transcript_as_sentences
from src.core.stream_engine import background_analyze_task
from src.core.history_manager import HistoryManager

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
analysis_semaphore = asyncio.Semaphore(Config.MAX_CONCURRENT_REQUESTS)

background_loop: Optional[asyncio.AbstractEventLoop] = None
orchestrator: Optional[AnalysisOrchestrator] = None
result_dir = project_root / 'src' / 'results'
result_dir.mkdir(exist_ok=True, parents=True)

current_analysis_future = None
task_lock = threading.Lock()

def cancel_current_analysis():
    global current_analysis_future
    with task_lock:
        if current_analysis_future and not current_analysis_future.done():
            logger.info("[Gestion Tâches] Annulation de l'analyse en cours pour éviter les fuites (History Leakage).")
            current_analysis_future.cancel()
            current_analysis_future = None

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
        api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            logger.error("MISTRAL_API_KEY environment variable is not set.")
            return
        
        orchestrator = await AnalysisOrchestrator.create(api_key=api_key)
        logger.info("AnalysisOrchestrator initialized successfully in background loop.")
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
            logger.error(f"Timeout or error waiting for orchestrator initialization: {e}")

# ==============================================================================
# THREAD-SAFE HISTORY HELPERS
# ==============================================================================

def safe_add_history(item: Dict[str, Any]):
    with history_lock:
        history_manager.add_to_history(item)

def safe_get_history() -> List[Dict[str, Any]]:
    with history_lock:
        return history_manager.get_history()

def safe_clear_history():
    with history_lock:
        history_manager.clear_history()

def safe_get_formatted_history(limit: int = 5) -> List[Dict[str, str]]:
    with history_lock:
        return history_manager.get_formatted_history(limit)

# ==============================================================================
# ROUTES
# ==============================================================================

@app.route('/')
def index():
    return render_template('index.html', api_status=API_STATUS)

@app.route('/api/status', methods=['GET'])
def get_api_status():
    """Returns the current status of the external APIs."""
    return jsonify(API_STATUS)

@app.route('/process_youtube', methods=['POST'])
def process_youtube():
    ensure_background_loop()
    
    data = request.json
    url = data.get('url')
    if not url:
        return jsonify({"error": "Missing 'url'"}), 400

    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({"error": "Invalid YouTube URL"}), 400

    try:
        logger.info(f"Processing YouTube Video ID: {video_id}")
        
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
                sents = await asyncio.to_thread(fetch_youtube_transcript_as_sentences, vid)
                if not sents:
                    logger.error("Could not extract sentences from transcript")
                    return
            except Exception as e:
                logger.error(f"Failed to fetch YouTube data: {e}")
                return

            guessed_names = guess_speakers_from_filename(v_title)
            speaker_names = guessed_names if guessed_names else []
            
            base_global_context = f"VIDÉO : {v_title}\nDATE DE DIFFUSION : {v_date}\n"
            
            logger.info("Récupération du contexte d'actualité (Monde/Pays) à la date de publication...")
            
            # Respect absolu du DIRECT : On utilise UNIQUEMENT les infos disponibles à T=0 (Titre et Noms)
            search_subject = " ".join(speaker_names) if speaker_names else v_title

            # 2. Recherche ciblée sur le vrai sujet
            news_context = await fetch_context_news(v_date, specific_subject=search_subject)
            base_global_context += f"\nCONTEXTE D'ACTUALITÉ (Recherche Automatique) :\n{news_context}\n\n"

            # Envoi du contexte d'actualité au frontend pour affichage au survol
            safe_add_history({
                "timestamp": datetime.now().isoformat(),
                "type": "context_update",
                "news_context": news_context,
                "video_timestamp": 0.0
            })

            if speaker_names:
                backgrounds = await asyncio.gather(*(fetch_speaker_background(name, analysis_semaphore) for name in speaker_names))
                base_global_context += "\n".join(backgrounds)
            
            logger.info(f"Global Context Prepared: {base_global_context[:100]}...")
            await background_analyze_task(
                sents, vid, base_global_context,
                orchestrator, result_dir,
                safe_add_history, safe_get_history, safe_get_formatted_history
            )

        global current_analysis_future
        with task_lock:
            current_analysis_future = asyncio.run_coroutine_threadsafe(
                prepare_and_run(video_id, title, date),
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
        result = future.result(timeout=60) # Wait up to 60s
        
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
        
        # Prepare context (requires async, so we do it in background too or sync wait)
        # To keep it simple, we'll spawn a background task that does context fetching + analysis
        
        async def process_vtt_task(fpath, sentences, filename_stem):
            try:
                guessed_names = guess_speakers_from_filename(filename_stem)
                speaker_names = guessed_names if guessed_names else []
                
                base_global_context = f"FICHIER : {filename_stem}\n"
                
                # Respect absolu du DIRECT : On utilise UNIQUEMENT le nom du fichier à T=0
                search_subject = " ".join(speaker_names) if speaker_names else filename_stem

                # 2. Recherche ciblée
                logger.info("Récupération du contexte d'actualité pour VTT...")
                news_context = await fetch_context_news(filename_stem, specific_subject=search_subject)
                base_global_context += f"\nCONTEXTE D'ACTUALITÉ (Recherche Automatique) :\n{news_context}\n\n"

                # Envoi du contexte d'actualité au frontend pour affichage au survol
                safe_add_history({
                    "timestamp": datetime.now().isoformat(),
                    "type": "context_update",
                    "news_context": news_context,
                    "video_timestamp": 0.0
                })

                if speaker_names:
                    # fetch_speaker_background needs a loop, we are in background_loop
                    backgrounds = await asyncio.gather(*(fetch_speaker_background(name, analysis_semaphore) for name in speaker_names))
                    base_global_context += "\n" + "\n".join(backgrounds)
                
                # Use same analysis logic as YouTube
                await background_analyze_task(
                    sentences, filename_stem, base_global_context,
                    orchestrator, result_dir,
                    safe_add_history, safe_get_history, safe_get_formatted_history
                )
                
            finally:
                if os.path.exists(fpath):
                    os.remove(fpath)

        global current_analysis_future
        with task_lock:
            current_analysis_future = asyncio.run_coroutine_threadsafe(
                process_vtt_task(str(filepath), sentences, Path(filename).stem),
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
    print("\n" + "="*80)
    print("🚦 DIAGNOSTIC DES API AVANT LANCEMENT DU SERVEUR WEB 🚦")
    print("="*80)
    try:
        result = subprocess.run(
            [sys.executable, "check_api_status.py"],
            capture_output=True, text=True, check=False
        )
        # Affiche la sortie lisible par l'homme (stderr) dans la console du serveur
        print(result.stderr)

        # Parse la sortie JSON (stdout) pour mettre à jour l'état de l'API
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

    print("\n🌐 Démarrage du serveur Web CodeCitoyen...")
    ensure_background_loop()
    app.run(host='0.0.0.0', port=5000, debug=True)
