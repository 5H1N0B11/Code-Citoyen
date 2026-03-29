import os
import re
import argparse
import logging
from typing import List, Dict, Any

import nltk
from nltk.tokenize import sent_tokenize
import ssl

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def _ensure_nltk_punkt():
    """
    Checks if the NLTK 'punkt' tokenizer is available and downloads it if not.
    Handles potential SSL errors during download.
    """
    try:
        # Check if 'punkt' is already available
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        print("Le tokenizer 'punkt' de NLTK n'est pas trouvé. Téléchargement en cours...")
        try:
            nltk.download('punkt')
            print("Téléchargement de 'punkt' terminé.")
        except Exception as e:
            print(f"Erreur lors du téléchargement de 'punkt': {e}")
            # Fallback for SSL issues on some systems
            try:
                print("Tentative avec une configuration SSL non vérifiée (fallback)...")
                ssl._create_default_https_context = ssl._create_unverified_context
                nltk.download('punkt')
                print("Téléchargement de 'punkt' (fallback) terminé.")
            except Exception as inner_e:
                print(f"Échec du téléchargement de 'punkt' même en fallback. Erreur: {inner_e}")
                print("Veuillez installer 'punkt' manuellement en exécutant: python -m nltk.downloader punkt")
                raise

# Ensure data is ready on module import
_ensure_nltk_punkt()

def get_asr_engine_name():
    """Returns the name of the ASR engine used."""
    return "Local VTT Parser (v5.0 - NLTK Sentence Reconstitution)"

def _vtt_time_to_seconds(time_str: str) -> float:
    """Converts a VTT timestamp (HH:MM:SS.ms or MM:SS.ms) to seconds."""
    if not time_str:
        return 0.0
    parts = time_str.split(':')
    try:
        if len(parts) == 3:
            h, m, s_ms = parts
            s, ms = (s_ms.split('.') + ['0'])[:2]
            return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, '0')[:3]) / 1000.0
        elif len(parts) == 2:
            m, s_ms = parts
            s, ms = (s_ms.split('.') + ['0'])[:2]
            return int(m) * 60 + int(s) + int(ms.ljust(3, '0')[:3]) / 1000.0
    except (ValueError, IndexError):
        logging.warning(f"Could not parse VTT timestamp: '{time_str}'.")
        return 0.0
    return 0.0

def _normalize_text(text: str) -> str:
    """Normalizes text by removing extra whitespace and newlines."""
    return ' '.join(text.split())

def parse_vtt_to_raw_cues(vtt_content: str) -> List[Dict[str, Any]]:
    """
    Parses VTT content into a raw list of cues.
    Implémente un dédoublonnage intelligent par mots pour les sous-titres 
    automatiques (rolling captions) qui répètent les lignes précédentes.
    """
    lines = vtt_content.strip().splitlines()
    raw_cues = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if '-->' in line:
            try:
                start_str, _ = [t.strip() for t in line.split('-->')]
                start_time = _vtt_time_to_seconds(start_str)

                i += 1
                text_lines = []
                while i < len(lines) and lines[i].strip() and '-->' not in lines[i]:
                    text_lines.append(lines[i].strip())
                    i += 1

                if text_lines:
                    full_text = " ".join(text_lines)
                    speaker_match = re.search(r'<v[.\s]([^>]+)>', full_text)
                    speaker = speaker_match.group(1).strip() if speaker_match else None
                    cleaned_text = _normalize_text(re.sub(r'<[^>]+>', '', full_text))

                    if cleaned_text:
                        raw_cues.append({
                            "start": start_time,
                            "text": cleaned_text,
                            "speaker": speaker
                        })
                continue
            except (ValueError, IndexError):
                pass
        i += 1
        
    # --- DÉDOUBLONNAGE INTELLIGENT AU NIVEAU DES MOTS (Spécial YouTube Auto-Subs) ---
    dedup_cues = []
    last_words = []
    
    for cue in raw_cues:
        current_text = cue['text']
        if not current_text:
            continue
            
        curr_words = current_text.split()
        if not curr_words or curr_words == last_words:
            continue
            
        # Cherche le chevauchement (overlap) exact de mots
        overlap_count = 0
        min_words = min(len(last_words), len(curr_words))
        for j in range(min_words, 0, -1):
            if last_words[-j:] == curr_words[:j]:
                overlap_count = j
                break
                
        if overlap_count > 0:
            new_words = curr_words[overlap_count:]
            if new_words:
                dedup_cues.append({ "start": cue['start'], "text": " ".join(new_words), "speaker": cue['speaker'] })
        else:
            dedup_cues.append({ "start": cue['start'], "text": " ".join(curr_words), "speaker": cue['speaker'] })
        
        last_words = curr_words
        
    return dedup_cues

def reconstitute_sentences(cues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Reconstructs complete sentences from a list of subtitle cues.
    This version is robust and designed for complete, non-streaming transcripts.
    """
    if not cues:
        return []

    # 1. Create a word-level list with timing and speaker info.
    words_with_timing = []
    for cue in cues:
        text = cue.get('text', '')
        words = text.split()
        if not words:
            continue
        for word in words:
            words_with_timing.append({
                "text": word,
                "start": cue.get('start', 0.0),
                "speaker": cue.get('speaker')
            })

    if not words_with_timing:
        return []

    # 2. Join all words to form the full transcript.
    full_transcript = " ".join([w['text'] for w in words_with_timing])

    # 3. Tokenize the full transcript into sentences.
    sentence_texts = sent_tokenize(full_transcript, language='french')

    # 4. Map sentences back to start times and speakers.
    reconstituted = []
    word_cursor = 0
    
    for sent_text in sentence_texts:
        sent_text_normalized = sent_text.strip()
        if not sent_text_normalized:
            continue

        if word_cursor >= len(words_with_timing):
            break
        
        start_time = words_with_timing[word_cursor]['start']
        speaker = words_with_timing[word_cursor]['speaker']

        reconstituted.append({
            'start': start_time,
            'text': sent_text_normalized,
            'speaker': speaker
        })

        # Advance the cursor by counting the words in the generated sentence.
        # This is an approximation but works well for most cases.
        num_words_in_sentence = len(sent_text_normalized.split())
        word_cursor += num_words_in_sentence

    return reconstituted



def ingest_from_local_vtt(file_path: str) -> List[Dict[str, Any]]:
    """
    Reads a local .vtt file and processes it into a list of complete sentences.
    """
    print(f"\n--- Démarrage de l'Ingestion (Mode Lecture Locale) ---")
    print(f"🔍 Lecture du fichier : {file_path}")
    
    try:
        if not os.path.exists(file_path):
            print(f"❌ ERREUR: Le fichier VTT local n'a pas été trouvé.")
            return []

        with open(file_path, 'r', encoding='utf-8') as f:
            vtt_content = f.read()
            
        print("✅ Fichier VTT lu. Étape 1: Parsing des cues brutes...")
        raw_cues = parse_vtt_to_raw_cues(vtt_content)
        
        print(f"✅ Étape 1 Réussie. {len(raw_cues)} cues brutes extraites.")
        print("✅ Étape 2: Reconstitution des phrases...")
        sentences = reconstitute_sentences(raw_cues)
        
        print(f"✅ Étape 2 Réussie. Total de {len(sentences)} phrases reconstituées.")
        return sentences
            
    except Exception as e:
        print(f"Erreur lors de la lecture ou du traitement du fichier VTT : {e}")
        # To aid debugging, re-raise the exception
        raise

# --- Example usage for local testing ---
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Parse a local VTT file and reconstruct sentences.")
    parser.add_argument('file_path', type=str, help="Path to the .vtt file to analyze.")
    args = parser.parse_args()
    
    final_entries = ingest_from_local_vtt(args.file_path)
    
    if final_entries:
        print(f"\n--- APERÇU DES 5 PREMIÈRES PHRASES RECONSTITUÉES ---\n")
        for entry in final_entries[:5]:
            spk = f"[{entry['speaker']}] " if entry.get('speaker') else ""
            print(f"- [T:{entry['start']:.2f}s] {spk}{entry['text']}")
        print(f"\nTotal de {len(final_entries)} phrases extraites.")
    else:
        print("\nAucune phrase n'a pu être extraite. Vérifiez le fichier.")
