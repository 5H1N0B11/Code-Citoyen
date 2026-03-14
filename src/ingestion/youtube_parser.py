import re
import logging
from typing import List, Dict, Any, Optional
import requests
from bs4 import BeautifulSoup
from youtube_transcript_api import YouTubeTranscriptApi

from src.ingestion.vtt_parser import reconstitute_sentences

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