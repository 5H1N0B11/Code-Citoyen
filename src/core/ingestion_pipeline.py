import os
import re
import argparse
import logging
from typing import List, Dict, Any

# NÉCESSITE : Rien d'autre que Python. Nous lisons un fichier local.

def get_asr_engine_name():
    """Retourne le nom du moteur ASR utilisé (local VTT parser) pour l'affichage dans l'orchestrateur."""
    return "Lecteur de fichier VTT local (Parser v3)"

def _vtt_time_to_seconds(time_str: str) -> float:
    """Convertit un horodatage VTT (HH:MM:SS.ms) en secondes."""
    if not time_str:
        return 0.0
    parts = time_str.split(':')
    try:
        if len(parts) == 3:
            h, m, s_ms = parts
            s, ms = (s_ms.split('.') + ['0'])[:2]
            return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0
        elif len(parts) == 2:
            m, s_ms = parts # Format MM:SS.ms
            s, ms = (s_ms.split('.') + ['0'])[:2]
            return int(m) * 60 + int(s) + int(ms) / 1000.0
    except (ValueError, IndexError) as e:
        # Log l'erreur pour le débogage au lieu de retourner silencieusement 0.0
        logging.warning(f"Impossible de parser l'horodatage VTT: '{time_str}'. Erreur: {e}")
        return 0.0
    return 0.0

def parse_vtt(vtt_content: str) -> List[Dict[str, Any]]:
    """
    Extrait le texte et les horodatages d'un contenu VTT.
    
    Cette fonction est conçue pour gérer les fichiers VTT générés par des services
    de transcription en direct (comme YouTube), qui ont souvent des sous-titres
    cumulatifs (chaque nouvelle entrée contient le texte de la précédente plus du nouveau texte).

    Logique de traitement :
    - Nettoie les balises de formatage VTT (ex: <c.color>).
    - Fusionne les entrées de sous-titres consécutives qui se chevauchent ou se complètent.
    - Ignore les entrées de texte dupliquées pour ne conserver que les segments uniques et progressifs.
    """
    lines = vtt_content.strip().splitlines()
    entries = []
    seen_texts = set()
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Cherche une ligne d'horodatage
        if '-->' in line:
            try:
                start_str, end_str = [t.strip() for t in line.split('-->')]
                start_time = _vtt_time_to_seconds(start_str)
                end_time = _vtt_time_to_seconds(end_str)
                
                i += 1
                text_lines = []
                # Les lignes suivantes jusqu'à la prochaine ligne vide ou d'horodatage sont le texte
                while i < len(lines) and lines[i].strip() and '-->' not in lines[i]:
                    text_lines.append(lines[i].strip())
                    i += 1
                
                if text_lines:
                    # Nettoie les balises VTT comme <c.color> ou <v Nom>
                    full_text = " ".join(text_lines)
                    cleaned_text = re.sub(r'<[^>]+>', '', full_text).strip()

                    if cleaned_text and cleaned_text not in seen_texts:
                        new_entry = {
                            "start": start_time,
                            "end": end_time,
                            "text": cleaned_text
                        }
                        # Fusionner avec l'entrée précédente si le nouveau texte est une continuation
                        # (le texte précédent est contenu dans le nouveau)
                        if entries and entries[-1]['text'] in new_entry['text']:
                            entries[-1]['end'] = new_entry['end']
                            entries[-1]['text'] = new_entry['text']
                        else:
                            entries.append(new_entry)
                        seen_texts.add(cleaned_text)
                continue # Passe à la prochaine ligne après avoir traité un bloc de texte
            except (ValueError, IndexError) as e:
                # Ignore les lignes d'horodatage mal formées
                pass
        
        i += 1
        
    return entries

def ingest_from_local_vtt(file_path: str) -> List[Dict[str, Any]]:
    """
    Lit le fichier .vtt local et le parse en une liste d'entrées avec horodatages.
    """
    print(f"\n--- Démarrage de l'Ingestion (Mode Lecture Locale) ---")
    print(f"🔍 Lecture du fichier : {file_path}")
    
    try:
        if not os.path.exists(file_path):
            print(f"❌ ERREUR: Le fichier VTT local n'a pas été trouvé à cet emplacement.")
            return []

        with open(file_path, 'r', encoding='utf-8') as f:
            vtt_content = f.read()
            
        print("✅ Fichier VTT lu. Nettoyage et parsing (v3 - avec horodatages)...")
        return parse_vtt(vtt_content)
            
    except Exception as e:
        print(f"Erreur lors de la lecture du fichier VTT : {e}")
        return []

# --- Exemple d'utilisation du module (gardé pour les tests locaux) ---
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Parse un fichier VTT local pour en extraire le dialogue avec horodatages.")
    parser.add_argument('file_path', type=str, help="Chemin vers le fichier .vtt à analyser.")
    args = parser.parse_args()
    
    entries = ingest_from_local_vtt(args.file_path)
    
    if entries:
        print(f"\n--- RÉSULTAT DE L'INGESTION (5 premières entrées) ---\n")
        for entry in entries[:5]:
            print(f"- [{entry['start']:.2f}s - {entry['end']:.2f}s] {entry['text']}")
        print(f"\nTotal de {len(entries)} entrées extraites.")
    else:
        print("\nAucune entrée n'a pu être extraite. Vérifiez le fichier.")