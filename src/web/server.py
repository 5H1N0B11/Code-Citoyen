import os
import sys
import asyncio
import logging
import re
import threading
import json
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

# Global State
history_manager = HistoryManager()
history_lock = threading.Lock()
analysis_semaphore = asyncio.Semaphore(Config.MAX_CONCURRENT_REQUESTS)

background_loop: Optional[asyncio.AbstractEventLoop] = None
orchestrator: Optional[AnalysisOrchestrator] = None
result_dir = project_root / 'src' / 'results'
result_dir.mkdir(exist_ok=True, parents=True)

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
    return render_template('index.html')

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
        async def prepare_and_run(vid):
            # Exécution asynchrone (Mission 2) : ne bloque plus le serveur Flask
            try:
                sents = await asyncio.to_thread(fetch_youtube_transcript_as_sentences, vid)
                if not sents:
                    logger.error("Could not extract sentences from transcript")
                    return
                title, date = await asyncio.to_thread(get_youtube_metadata, vid)
                logger.info(f"Fetched Video Title: {title}, Date: {date}")
            except Exception as e:
                logger.error(f"Failed to fetch YouTube data: {e}")
                return

            guessed_names = guess_speakers_from_filename(title)
            speaker_names = guessed_names if guessed_names else []
            
            base_global_context = f"VIDÉO : {title}\nDATE DE DIFFUSION : {date}\n"
            if speaker_names:
                backgrounds = await asyncio.gather(*(fetch_speaker_background(name, analysis_semaphore) for name in speaker_names))
                base_global_context += "\n".join(backgrounds)
            
            logger.info(f"Global Context Prepared: {base_global_context[:100]}...")
            await background_analyze_task(
                sents, vid, base_global_context,
                orchestrator, result_dir,
                safe_add_history, safe_get_history, safe_get_formatted_history
            )

        asyncio.run_coroutine_threadsafe(
            prepare_and_run(video_id),
            background_loop
        )
        # END NEW CONTEXT LOGIC
        
        return jsonify({
            "message": "Analysis started in background", 
            "video_id": video_id
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

    try:
        sentences = ingest_from_local_vtt(str(filepath))
        safe_clear_history()
        
        # Prepare context (requires async, so we do it in background too or sync wait)
        # To keep it simple, we'll spawn a background task that does context fetching + analysis
        
        async def process_vtt_task(fpath, sentences, filename_stem):
            try:
                guessed_names = guess_speakers_from_filename(filename_stem)
                speaker_names = guessed_names if guessed_names else []
                
                base_global_context = ""
                if speaker_names:
                    # fetch_speaker_background needs a loop, we are in background_loop
                    backgrounds = await asyncio.gather(*(fetch_speaker_background(name, analysis_semaphore) for name in speaker_names))
                    base_global_context = "\n".join(backgrounds)
                
                # Use same analysis logic as YouTube
                await background_analyze_task(
                    sentences, filename_stem, base_global_context,
                    orchestrator, result_dir,
                    safe_add_history, safe_get_history, safe_get_formatted_history
                )
                
            finally:
                if os.path.exists(fpath):
                    os.remove(fpath)

        asyncio.run_coroutine_threadsafe(
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
    # Initialize background loop before app start (optional, as routes will ensure it)
    ensure_background_loop()
    app.run(host='0.0.0.0', port=5000, debug=True)
