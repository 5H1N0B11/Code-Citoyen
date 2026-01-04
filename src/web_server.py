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
from youtube_transcript_api import YouTubeTranscriptApi

import requests
from bs4 import BeautifulSoup

# Ensure project root is in path for imports
current_dir = Path(__file__).parent.absolute()
project_root = current_dir.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

# Imports from project modules
from src.core.orchestrator import AnalysisOrchestrator
from src.core.ingestion_pipeline import ingest_from_local_vtt, reconstitute_sentences
from src.core.context_fetcher import fetch_speaker_background, guess_speakers_from_filename
from src.utils import Config, validate_text, format_affirmation, AnalysisError
from src.live_fact_checker import HistoryManager

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
# CORE LOGIC
# ==============================================================================

def extract_video_id(url: str) -> Optional[str]:
    patterns = [
        r'(?:v=|/)([0-9A-Za-z_-]{11}).*',
        r'(?:youtu\.be/)([0-9A-Za-z_-]{11})',
        r'(?:embed/)([0-9A-Za-z_-]{11})'
    ]
    for pattern in patterns:
        query = re.search(pattern, url)
        if query:
            return query.group(1)
    return None

def get_youtube_metadata(video_id: str) -> tuple[str, str]:
    """Fetches the YouTube video title and upload date."""
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Get Title
        title = "Unknown Title"
        meta_title = soup.find("meta", property="og:title")
        if meta_title:
            title = meta_title["content"]
        else:
            title_tag = soup.title
            if title_tag:
                title = title_tag.string.replace(" - YouTube", "")
        
        # Get Date
        date_str = "Date inconnue"
        meta_date = soup.find("meta", itemprop="datePublished")
        if meta_date:
            date_str = meta_date["content"] # Format YYYY-MM-DD
            
        return title, date_str

    except Exception as e:
        logger.error(f"Failed to fetch YouTube metadata: {e}")
        return "Unknown Title", "Date inconnue"

def fetch_youtube_transcript_as_sentences(video_id: str) -> List[Dict[str, Any]]:
    try:
        yt = YouTubeTranscriptApi()
        transcript_list = yt.list(video_id)
        transcript = None
        
        # Prioritize French, then English
        try:
             transcript = transcript_list.find_transcript(['fr', 'en'])
        except:
             pass
             
        if not transcript:
             try:
                 transcript = transcript_list.find_generated_transcript(['fr', 'en'])
             except:
                 pass
                 
        if not transcript:
             for t in transcript_list:
                 transcript = t
                 break
        
        if not transcript:
            raise Exception("No transcript found for this video.")

        raw_data = transcript.fetch()
        
        cleaned_cues = []
        for item in raw_data:
             # Handle both object (newer API) and dict (older API) just in case, 
             # though we know it's likely an object now.
             text = item.text if hasattr(item, 'text') else item.get('text', '')
             start = item.start if hasattr(item, 'start') else item.get('start', 0.0)
             
             cleaned_cues.append({
                 'text': text.replace('\n', ' '),
                 'start': start,
                 'speaker': None
             })
             
        return reconstitute_sentences(cleaned_cues)

    except Exception as e:
        logger.error(f"Error fetching YouTube transcript: {e}")
        raise e

async def background_analyze_task(sentences: List[Dict[str, Any]], video_id: str, global_context: str = ""):
    """Task running in background loop to analyze sentences."""
    if not orchestrator:
        logger.error("Orchestrator not ready.")
        return

    results_list = []
    logger.info(f"Starting background analysis for {len(sentences)} sentences.")
    
    # Define filename early for incremental saving
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = result_dir / f"web_youtube_{video_id}_{timestamp_str}.json"

    for i in range(len(sentences)):
        sentence_dict = sentences[i]
        affirmation_text = sentence_dict['text']
        if len(affirmation_text) < 10:
            continue

        # Construct future context (look-ahead 3 sentences)
        future_window = sentences[i+1 : i+4]
        future_context = " ".join([s['text'] for s in future_window])

        # Construct previous context (immediate previous sentence)
        previous_context = sentences[i-1]['text'] if i > 0 else None

        try:
            # Get full history (up to 1000 items) to provide cumulative context
            hist = safe_get_formatted_history(limit=1000)
            
            # Analyze (Async call to Mistral)
            current_result = await orchestrator.analyze(
                affirmation=affirmation_text,
                history=hist,
                global_context=global_context,
                future_context=future_context,
                previous_context=previous_context
            )
            
            processed_result = {
                "timestamp": datetime.now().isoformat(),
                "affirmation": format_affirmation(affirmation_text),
                "result": current_result,
                "video_timestamp": sentence_dict['start']
            }
            
            safe_add_history(processed_result)
            results_list.append(processed_result)

            # Incremental Save: Update the file after each successful analysis
            try:
                with open(output_filename, 'w', encoding='utf-8') as f:
                    json.dump(results_list, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Failed to save incremental results: {e}")
            
        except Exception as e:
            logger.error(f"Error analyzing sentence: {e}")
            continue

    logger.info(f"Analysis complete. Results fully saved to {output_filename}")

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
        sentences = fetch_youtube_transcript_as_sentences(video_id)
        
        if not sentences:
            return jsonify({"error": "Could not extract sentences from transcript"}), 400

        safe_clear_history()

        # START NEW CONTEXT LOGIC
        # 1. Fetch Metadata (Title + Date)
        video_title, video_date = get_youtube_metadata(video_id)
        logger.info(f"Fetched Video Title: {video_title}, Date: {video_date}")
        
        # 2. Spawn a background preparation task to fetch bio and then start analysis
        #    We do this because fetch_speaker_background is async and we are in a synchronous flask route.
        async def prepare_and_run(vid, sents, title, date):
            guessed_names = guess_speakers_from_filename(title)
            speaker_names = guessed_names if guessed_names else []
            
            base_global_context = f"VIDÉO : {title}\nDATE DE DIFFUSION : {date}\n"
            if speaker_names:
                backgrounds = await asyncio.gather(*(fetch_speaker_background(name, background_loop) for name in speaker_names))
                base_global_context += "\n".join(backgrounds)
            
            logger.info(f"Global Context Prepared: {base_global_context[:100]}...")
            await background_analyze_task(sents, vid, base_global_context)

        asyncio.run_coroutine_threadsafe(
            prepare_and_run(video_id, sentences, video_title, video_date),
            background_loop
        )
        # END NEW CONTEXT LOGIC
        
        return jsonify({
            "message": "Analysis started in background", 
            "video_id": video_id,
            "sentence_count": len(sentences),
            "video_title": video_title,
            "video_date": video_date
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
                    backgrounds = await asyncio.gather(*(fetch_speaker_background(name, background_loop) for name in speaker_names))
                    base_global_context = "\n".join(backgrounds)
                
                # Use same analysis logic as YouTube
                await background_analyze_task(sentences, filename_stem, base_global_context)
                
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