import os
import re
import tempfile
from typing import List

# NÉCESSITE : pip install yt-dlp setuptools-rust numpy torch torchaudio openai-whisper
# Assurez-vous que FFmpeg est installé sur votre système (ex: sudo apt install ffmpeg)

try:
    import whisper
    import torch
    from yt_dlp import YoutubeDL
except ImportError as e:
    print(f"Erreur: Librairie requise manquante. Veuillez installer les dépendances nécessaires.")
    print(f"Détails: {e}")
    exit(1)


# --- CONFIGURATION WHISPER FORCEE CPU (Suite au problème GTX 970/sm_52) ---
# Nous utilisons le CPU car la version actuelle de PyTorch n'est pas compatible avec l'architecture sm_52 de la GTX 970.
# Le modèle 'small' est choisi pour réduire le temps de calcul CPU.
WHISPER_MODEL_NAME = "small" 
DEVICE = "cpu"

print(f"🤖 Moteur ASR sélectionné: Whisper ({WHISPER_MODEL_NAME})")
print(f"⚙️ Périphérique de calcul: {DEVICE} (Mode Forcé)")
# ---

def load_whisper_model():
    """Charge le modèle Whisper une seule fois en mémoire (en mode CPU)."""
    try:
        # Charger le modèle sur le CPU, sans tentative de bascule GPU/CUDA
        model = whisper.load_model(WHISPER_MODEL_NAME, device=DEVICE) 
        return model
    except Exception as e:
        print(f"Erreur fatale lors du chargement du modèle Whisper en CPU : {e}")
        return None

# Charger le modèle globalement au démarrage (si le module est importé)
WHISPER_MODEL = load_whisper_model()


def clean_transcript(text: str) -> List[str]:
    """Nettoie la transcription et la découpe en phrases pour le Fact-Checker."""
    
    # 1. Nettoyage de base (retrait des espaces multiples, bruits de micro, etc.)
    text = re.sub(r'\[.*?\]', '', text)  # Retire les annotations entre crochets ([musique], [applause])
    text = re.sub(r'\s+', ' ', text).strip()
    
    # 2. Découpage en phrases basées sur la ponctuation forte
    sentences = re.split(r'(?<=[.?!;])\s+', text)
    
    # 3. Filtrage et nettoyage final de chaque phrase
    cleaned_sentences = [
        s.strip() for s in sentences if s.strip()
    ]
    
    return cleaned_sentences


def transcribe_audio_to_statements(audio_path: str) -> List[str]:
    """Transcrit l'audio et renvoie une liste d'affirmations nettoyées."""
    if WHISPER_MODEL is None:
        print("Erreur: Le moteur Whisper n'a pas pu être initialisé.")
        return []

    print(f"🎙️ Transcription en cours de : {os.path.basename(audio_path)}...")
    
    try:
        # Déclenche la transcription (langue française explicitée pour le modèle multilingue 'small')
        result = WHISPER_MODEL.transcribe(audio_path, language="fr", verbose=False) 
        
        transcript = result["text"]
        print("✅ Transcription réussie.")
        
        # Le Fact-Checker est exigeant : on coupe le texte en phrases pour les traiter en batch
        return clean_transcript(transcript)
        
    except Exception as e:
        print(f"Erreur lors de la transcription Whisper : {e}")
        return []


def ingest_from_url(url: str, delete_audio=True) -> List[str]:
    """Télécharge l'audio depuis une URL et lance la transcription."""
    
    # Utilisation d'un dossier temporaire pour stocker l'audio
    with tempfile.TemporaryDirectory() as tmpdir:
        audio_output_path = os.path.join(tmpdir, "audio_stream.mp3")
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': audio_output_path,
            'quiet': True,
            'verbose': False,
            # Limite de temps pour ne pas télécharger des heures de vidéo lors des tests
            'max_filesize': 500 * 1024 * 1024, # 500 MB max (pour l'audio)
        }
        
        try:
            print(f"⬇️ Téléchargement/Extraction de l'audio depuis l'URL : {url}...")
            # Note: yt-dlp gère les URL de YouTube, Twitter, et de nombreux autres sites
            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
                
            if not os.path.exists(audio_output_path):
                print("Erreur: Le fichier audio n'a pas été créé (URL invalide ou échec FFmpeg).")
                return []
            
            statements = transcribe_audio_to_statements(audio_output_path)
            
            if delete_audio and os.path.exists(audio_output_path):
                os.remove(audio_output_path)
                
            return statements
            
        except Exception as e:
            print(f"Erreur lors de l'ingestion de l'URL : {e}")
            return []


# --- Exemple d'utilisation du module ---
if __name__ == '__main__':
    
    # ATTENTION : Cette exécution est en mode CPU et peut prendre du temps sur des longues vidéos.
    # Remplacez par une URL YouTube ou un chemin de fichier audio local
    TEST_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ" # Rick Astley (Anglais), idéal pour un test rapide
    
    if WHISPER_MODEL:
        print("--- Démarrage de l'Ingestion de Test ---")
        statements = ingest_from_url(TEST_URL)
        print("\n--- RÉSULTAT DE L'INGESTION ---")
        for i, stmt in enumerate(statements):
            print(f"[{i+1}] {stmt}")
        print("-------------------------------")
    else:
        print("Impossible d'exécuter le test car le modèle Whisper n'a pas pu être chargé.")
