import os
import re
import argparse
import argparse
from typing import List

# NÉCESSITE : Rien d'autre que Python. Nous lisons un fichier local.

# --- CORRECTION : Ajout de la fonction get_asr_engine_name() et suppression du print au niveau racine ---
def get_asr_engine_name():
    """Retourne le nom du moteur ASR utilisé (local VTT parser) pour l'affichage dans l'orchestrateur."""
    return "Lecteur de fichier VTT local (Parser v2)"

# --- Fonctions Utilitaires ---

def clean_transcript(text: str) -> List[str]:
    """Nettoie la transcription et la découpe en phrases pour le Fact-Checker."""
    # Correction des expressions régulières pour Python
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    sentences = re.split(r'(?<=[.?!;])\s+', text)
    cleaned_sentences = [s.strip() for s in sentences if s.strip()]
    return cleaned_sentences

def parse_vtt(vtt_content: str) -> List[str]:
    """
    Extrait et nettoie le texte d'un fichier VTT.
    Version 2 : Gère les en-têtes et la déduplication.
    """
    
    lines = vtt_content.splitlines()
    dialogue_lines = []
    last_line_added = "" # Variable pour vérifier les doublons
    in_header = True # Indicateur pour ignorer l'en-tête
    
    for line in lines:
        # Ignore l'en-tête VTT et les lignes vides
        if line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
            continue
        # Sortir du mode en-tête après la première ligne vide suivant l'en-tête
        if not line.strip():
            in_header = False
            continue
        if in_header:
            continue
            
        # Ignore les horodatages et autres métadonnées (qui commencent par des chiffres, ex: 00:00:00.000 --> 00:00:00.000)
        # Note: Utilisation de la version Python de l'expression régulière
        if re.match(r'\d{2}:\d{2}:\d{2}\.\d{3}', line.strip()):
            continue
        
        # Nettoyage et déduplication
        cleaned_line = re.sub(r'<[^>]+>', '', line).strip() # Retire les balises VTT <c> et les horodatages internes
        if cleaned_line and cleaned_line != last_line_added:
            dialogue_lines.append(cleaned_line)
            last_line_added = cleaned_line
        
    # Concaténer tout le dialogue en un seul bloc de texte
    full_text = " ".join(dialogue_lines)
    
    # Utiliser le nettoyeur de phrases
    return clean_transcript(full_text)

def ingest_from_local_vtt(file_path: str) -> List[str]:
    """Lit le fichier .vtt local et le parse."""
    
    print(f"\n--- Démarrage de l'Ingestion (Mode Lecture Locale) ---")
    print(f"🔍 Lecture du fichier : {file_path}")
    
    try:
        if not os.path.exists(file_path):
            print(f"❌ ERREUR: Le fichier VTT local n'a pas été trouvé à cet emplacement.")
            print("Veuillez vérifier le nom du fichier dans le script.")
            return []

        with open(file_path, 'r', encoding='utf-8') as f:
            vtt_content = f.read()
            
        print("✅ Fichier VTT lu. Nettoyage et parsing (v2)...")
        return parse_vtt(vtt_content)
            
    except Exception as e:
        print(f"Erreur lors de la lecture du fichier VTT : {e}")
        return []

# --- Exemple d'utilisation du module (gardé pour les tests locaux) ---
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Parse un fichier VTT local pour en extraire le dialogue.")
    parser.add_argument('file_path', type=str, help="Chemin vers le fichier .vtt à analyser.")
    args = parser.parse_args()
    
    # On utilise le chemin fourni en argument
    statements = ingest_from_local_vtt(args.file_path)
    
    if statements:
        print("\n--- RÉSULTAT DE L'INGESTION (5 premières phrases) ---\n")
        for s in statements[:5]:
            print(f"- {s}")
        print(f"\nTotal de {len(statements)} phrases extraites.")
    else:
        print("\nAucune phrase n'a pu être extraite. Vérifiez le fichier.")
