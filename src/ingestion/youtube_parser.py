import re
import logging
from typing import List, Dict, Any, Optional
import tempfile
import os
import requests
from datetime import datetime
import yt_dlp

from src.ingestion.vtt_parser import parse_vtt_to_raw_cues, reconstitute_sentences

logger = logging.getLogger(__name__)

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
    """Fetches the YouTube video title and upload date using yt-dlp for robustness."""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'force_generic_extractor': False, # Let it use the youtube extractor
        # Add a small delay between requests to avoid being rate-limited (429)
        'sleep_requests': 1,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            title = info_dict.get('title', 'Unknown Title')
            upload_date_str = info_dict.get('upload_date') # Format: YYYYMMDD
            if upload_date_str:
                date_obj = datetime.strptime(upload_date_str, '%Y%m%d')
                date_str = date_obj.strftime('%Y-%m-%d')
            else:
                date_str = "Date inconnue"
            return title, date_str
    except Exception as e:
        logger.error(f"Failed to fetch YouTube metadata with yt-dlp: {e}")
        return "Unknown Title", "Date inconnue"

def fetch_youtube_transcript_as_sentences(video_id: str) -> List[Dict[str, Any]]:
    """Fetches YouTube transcript using yt-dlp to download the VTT file, then parses it."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'writesubtitles': True,
            'subtitleslangs': ['fr'], # Prioritize French only to reduce requests and avoid unnecessary English attempts
            'writeautomaticsub': True,
            'subtitlesformat': 'vtt', # Explicitly request VTT format
            # Use a fixed name for easier discovery. yt-dlp will add lang and extension.
            'outtmpl': os.path.join(tmpdir, 'subtitle'),
            # Add a small delay between requests to avoid being rate-limited (429)
            'sleep_requests': 1,
        }
        
        # --- NOUVEAU : Gestion du Proxy pour contourner les blocages IP ---
        proxy = os.environ.get('YOUTUBE_PROXY')
        if proxy:
            logger.info(f"Utilisation du proxy pour yt-dlp : {proxy}")
            ydl_opts['proxy'] = proxy
        
        vtt_filepath = None
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Use download() which is more explicit for this action, even with skip_download=True
                ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
            
            # Find the downloaded .vtt file robustly by scanning the directory
            downloaded_files = os.listdir(tmpdir)
            logger.info(f"Files found in temp dir '{tmpdir}': {downloaded_files}")
            vtt_files = [f for f in downloaded_files if f.endswith('.vtt')]
            
            if not vtt_files:
                # This is the point of failure. Provide a more helpful error.
                raise Exception("yt-dlp executed without error, but no VTT file was created. This could be due to an IP block by YouTube, or the video having no French subtitles available (manual or automatic).")

            # Prioritize any French subtitles (.fr, .fr-CA, .fr-FR) or fallback broadly
            french_file = next((f for f in vtt_files if '.fr' in f.lower() or 'french' in f.lower()), None)
            if french_file:
                vtt_filepath = os.path.join(tmpdir, french_file)
                logger.info(f"Fichier de sous-titres Francophone trouvé : {vtt_filepath}")
            else:
                # If no french, take the first one found (likely english or the only one)
                vtt_filepath = os.path.join(tmpdir, vtt_files[0])
                logger.info(f"Aucun sous-titre '.fr' trouvé. Utilisation du premier fichier disponible : {vtt_filepath}")

            # --- Read and Parse the VTT file ---
            with open(vtt_filepath, 'r', encoding='utf-8') as f:
                vtt_content = f.read()

            if not vtt_content or not vtt_content.strip().startswith("WEBVTT"):
                 raise Exception("Downloaded content is not a valid VTT transcript.")

            raw_cues = parse_vtt_to_raw_cues(vtt_content)
            return reconstitute_sentences(raw_cues)
            
        except Exception as e:
            # This will now catch the more descriptive exception from above, or an exception from ydl.download()
            logger.error(f"Error fetching YouTube transcript with yt-dlp: {e}")
            raise e