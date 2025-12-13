import os
import re
import argparse
import logging
import difflib
from typing import List, Dict, Any

# NÉCESSITE : Rien d'autre que Python. Nous lisons un fichier local.

def get_asr_engine_name():
    """Retourne le nom du moteur ASR utilisé (local VTT parser) pour l'affichage dans l'orchestrateur."""
    return "Lecteur de fichier VTT local (Parser v3.1 - Speaker Aware)"

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

def _normalize_text(text: str) -> str:
    """Normalise le texte en supprimant les espaces multiples et les sauts de ligne."""
    return ' '.join(text.split())

def _clean_for_compare(text: str) -> str:
    """Nettoie le texte pour la comparaison (minuscules, sans ponctuation)."""
    return re.sub(r'[\W_]+', '', text).lower()

def parse_vtt(vtt_content: str) -> List[Dict[str, Any]]:
    """
    Extrait le texte, les horodatages et les locuteurs d'un contenu VTT.

    Cette fonction est conçue pour gérer les fichiers VTT générés par des services de transcription
    en direct (comme YouTube), qui ont souvent des sous-titres cumulatifs ou défilants.

    Logique de traitement :
    - Nettoie les balises de formatage VTT (ex: <c.color>).
    - Fusionne les entrées de sous-titres consécutives qui se chevauchent. Cette fusion est
      basée sur une détection de suffixe/préfixe commun, une alternative performante à des
      calculs plus lourds comme la distance de Levenshtein, bien adaptée aux sous-titres
      défilants.
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
                    
                    # Extraction du locuteur (Format: <v Nom du locuteur>)
                    speaker = None
                    # Gère <v Nom> et <v.Nom>
                    speaker_match = re.search(r'<v[.\s]([^>]+)>', full_text)
                    if speaker_match:
                        speaker = speaker_match.group(1)
                    # Fallback : Détection du format "NOM: Paroles" si pas de balise <v>
                    elif ':' in full_text:
                        potential_speaker = full_text.split(':', 1)[0]
                        if len(potential_speaker) < 20 and potential_speaker.isupper():
                            speaker = potential_speaker.strip()

                    cleaned_text = _normalize_text(re.sub(r'<[^>]+>', '', full_text))

                    if cleaned_text and cleaned_text not in seen_texts:
                        new_entry = {
                            "start": start_time,
                            "end": end_time,
                            "text": cleaned_text.strip(),
                            "speaker": speaker
                        }
                        
                        # Logique de fusion V3.1 - Robuste avec difflib et Speaker
                        if entries:
                            last_entry = entries[-1]
                            last_text = last_entry['text']
                            new_text = new_entry['text']
                            clean_last = _clean_for_compare(last_text)
                            clean_new = _clean_for_compare(new_text)

                            # Règle 0 : Si le locuteur change, on ne fusionne PAS
                            if last_entry.get('speaker') != new_entry.get('speaker'):
                                entries.append(new_entry)
                                seen_texts.add(cleaned_text)
                                continue

                            # Cas 1: Le nouveau texte est une extension/remplacement de l'ancien
                            # On compare les versions nettoyées pour ignorer la ponctuation/casse
                            if clean_last in clean_new and clean_last != clean_new:
                                last_entry['text'] = new_text.strip()
                                last_entry['end'] = new_entry['end']
                                # Mise à jour du speaker si manquant avant
                                if not last_entry.get('speaker') and new_entry.get('speaker'):
                                    last_entry['speaker'] = new_entry['speaker']
                            # Cas 2: Le nouveau texte est redondant
                            elif clean_new in clean_last:
                                pass # On ignore
                            
                            # Cas 2b : Heuristique temporelle (déplacée APRÈS la vérification de contenu)
                            # Si le texte n'est ni une suite ni une redondance, on regarde le temps.
                            elif (new_entry['start'] - last_entry['end']) > 2.0:
                                entries.append(new_entry)
                                seen_texts.add(cleaned_text)
                                continue

                            else:
                                # Cas 3: Utilisation de difflib pour trouver le meilleur chevauchement
                                sm = difflib.SequenceMatcher(None, last_text, new_text, autojunk=False)
                                match = sm.find_longest_match(0, len(last_text), 0, len(new_text))
                                
                                # Heuristique : le match doit être significatif et commencer au début du nouveau texte
                                is_significant_overlap = match.size > 10 or match.size > 0.4 * len(new_text)
                                
                                if match.b == 0 and is_significant_overlap:
                                    combined_text = last_text[:match.a] + new_text
                                    last_entry['text'] = combined_text.strip()
                                    last_entry['end'] = new_entry['end']
                                else:
                                    entries.append(new_entry)
                        else:
                            entries.append(new_entry) # C'est la toute première entrée
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
            
        print("✅ Fichier VTT lu. Nettoyage et parsing (v3.1 - avec Speaker)...")
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
            spk = f"[{entry['speaker']}] " if entry.get('speaker') else ""
            print(f"- {spk}[{entry['start']:.2f}s] {entry['text']}")
        print(f"\nTotal de {len(entries)} entrées extraites.")
    else:
        print("\nAucune entrée n'a pu être extraite. Vérifiez le fichier.")