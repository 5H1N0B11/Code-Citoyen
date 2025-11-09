# debug_ingestion.py

from yt_dlp import YoutubeDL
from youtube_transcript_api import YouTubeTranscriptApi

TEST_VIDEO_ID = "NO8cUqaYxOM"  # ID de la vidéo d'Éric Zemmour

print("--- Démarrage du Débogage Ingestion ---")

# 1. Test de la librairie YouTube Transcript
try:
    print("Test 1: Tentative d'appel à YouTubeTranscriptApi.get_transcript...")
    # La fonction devrait exister, même si la vidéo n'a pas de sous-titres
    transcript = YouTubeTranscriptApi.get_transcript(TEST_VIDEO_ID, languages=['fr', 'en'], continue_after_error=True)
    if isinstance(transcript, list):
        print("✅ SUCCESS: La fonction get_transcript est accessible et fonctionne.")
    else:
        print("⚠️ AVERTISSEMENT: La fonction est accessible, mais n'a pas trouvé de transcription.")
except AttributeError:
    print("❌ ÉCHEC: La fonction get_transcript n'existe PAS. Le package est corrompu/obsolète.")
except Exception as e:
    print(f"⚠️ AVERTISSEMENT: Fonction accessible, mais erreur : {e}")

print("-" * 30)

# 2. Test de l'initialisation de yt-dlp
try:
    print("Test 2: Tentative d'initialisation de yt-dlp...")
    ydl = YoutubeDL({'format': 'bestaudio', 'quiet': True})
    print("✅ SUCCESS: YoutubeDL s'initialise correctement.")
except Exception as e:
    print(f"❌ ÉCHEC: Erreur d'initialisation de YoutubeDL : {e}")

print("--- Fin du Débogage ---")
