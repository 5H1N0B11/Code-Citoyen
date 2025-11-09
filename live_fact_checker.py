import asyncio
import time
import os
import sys
import argparse
import re # Ajout nécessaire pour re.split()
from typing import List, Dict, Any

PROJECT_NAME = "Codecitoyen"
SEPARATOR = "=" * 80

# --- Importations des modules du projet ---
try:
    # On importe les fonctions nécessaires du module d'analyse
    from Analyse_Critique_IA import (
        get_mistral_client,      # Client (Importation corrigée)
        ask_ma,                   # Mode 'ask' (avec gestion du 'skip')
        fact_checker_batch_async, # La fonction de façade pour le Batch (ASYNC)
        afficher_rapport_final    # La fonction d'affichage du Batch (Importée de Analyse_Critique_IA.py)
    )
    # On importe le module d'ingestion (Brique 1)
    from ingestion_pipeline import (
        ingest_from_local_vtt,
        LOCAL_VTT_FILE,
        get_asr_engine_name # Assurez-vous qu'elle existe dans ingestion_pipeline.py
    )
    # On importe le module de Fact-Checking (Brique 4)
    from Fact_Checker import fact_check_affirmations 
    
except ImportError as e:
    print("ERREUR CRITIQUE D'IMPORTATION : Assurez-vous que tous les fichiers/fonctions sont présents et nommés correctement.")
    print(f"Vérifiez en particulier 'Analyse_Critique_IA.py', 'ingestion_pipeline.py' et 'Fact_Checker.py'.")
    print(f"Détail : {e}")
    sys.exit(1)

# --- Configuration & Initialisation du Client Mistral (Client V1.0.0+) ---
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")

if not MISTRAL_API_KEY:
    print("ERREUR: La variable d'environnement MISTRAL_API_KEY n'est pas définie.")
    sys.exit(1)
    
# Initialisation du client Mistral
try:
    mistral_client = get_mistral_client(MISTRAL_API_KEY)
except Exception as e:
    print(f"Erreur lors de l'initialisation du client Mistral : {e}")
    sys.exit(1)


# --- Fonctions d'Orchestration ---

def get_affirmations_from_vtt() -> List[Dict[str, Any]]:
    """Récupère et prépare les affirmations du fichier VTT pour le batch."""
    affirmations_list = ingest_from_local_vtt(LOCAL_VTT_FILE) 
    
    if not affirmations_list:
        print("❌ ERREUR: Aucune affirmation extraite du VTT.")
        return []
        
    print(f"✅ {len(affirmations_list)} affirmations extraites et prêtes pour le Fact-Checking.")
    return [{"affirmation": a} for a in affirmations_list]


def get_user_input() -> List[Dict[str, Any]]:
    """Récupère les affirmations en mode manuel (Ctrl+D pour valider)."""
    
    print(SEPARATOR)
    print("Mode Fact-Checker Manuel")
    print("Entrez les affirmations (une par ligne), puis validez avec Ctrl+D (ou Ctrl+Z sous Windows) :")
    
    try:
        saisie = sys.stdin.read().strip() 

        if not saisie or saisie.lower() == 'quit':
            print("Aucune affirmation saisie ou sortie demandée. Arrêt du programme.")
            return []

        affirmations = re.split(r'\s*\n+\s*', saisie)
        affirmations = [a.strip() for a in affirmations if a.strip()]
        
        if not affirmations:
            print("Aucune affirmation valide trouvée après le nettoyage.")
            return []

        return [{"affirmation": a} for a in affirmations]
        
    except EOFError:
        print("\nSortie forcée par l'utilisateur (Ctrl+D ou Ctrl+Z).")
        return []
    except Exception as e:
        print(f"Une erreur inattendue est survenue lors de la saisie manuelle : {e}")
        return []


async def fact_checker_batch(affirmations_input: List[Dict[str, Any]], mode: str):
    """
    Orchestre les étapes 4 et 5 (Fact-Checking Web et Analyse Critique IA)
    pour une liste d'affirmations.
    """
    if not affirmations_input:
        print("Aucune affirmation à traiter. Arrêt du batch.")
        return

    # 1. --- Fact-Checking Web (Module 4) ---
    affirmations_seules = [item["affirmation"] for item in affirmations_input]
    resultats_fact_checker = fact_check_affirmations(affirmations_seules) 

    # 2. --- Analyse Critique IA (Module 5) ---
    print(SEPARATOR)
    print("🤖 Démarrage du Module 5 : Analyse Critique IA (Batch Asynchrone MISTRAL)")
    
    # 🚨 CORRECTION : Ajout de l'argument 'mode' manquant
    rapports_finaux = await fact_checker_batch_async(mistral_client, resultats_fact_checker, mode)

    # 3. --- Affichage du Rapport Final ---
    afficher_rapport_final(rapports_finaux, mode)


async def main_async():
    
    # --- Parsing des Arguments de Ligne de Commande ---
    parser = argparse.ArgumentParser(
        description=f"Outil d'orchestration du Fact-Checker Critique {PROJECT_NAME}."
    )
    
    parser.add_argument(
        'mode', 
        nargs='?', # Rend l'argument 'mode' optionnel
        default='manual', # 'manual' est la valeur par défaut
        choices=['manual', 'vtt', 'ask'], 
        help='Mode d\'exécution: manual (défaut), vtt, ou ask (question unique).'
    )
    
    parser.add_argument(
        'question_content', 
        nargs='?', 
        default=None,
        help='Le texte/l\'affirmation à vérifier (requis et mis entre guillemets doubles en mode "ask").'
    )
    
    args = parser.parse_args()
    mode = args.mode
    question_content = args.question_content 

    # --- Vérification de l'argument 'ask' ---
    if mode == 'ask' and not question_content:
        print("ERREUR: Le mode 'ask' nécessite un argument (votre question) entre guillemets doubles.")
        print('Exemple : python live_fact_checker.py ask "Mon affirmation à vérifier"')
        return
    
    # --- Affichage du Moteur (Pour le contexte) ---
    print("🤖 Moteur IA sélectionné: MISTRAL")
    
    try:
        from ingestion_pipeline import get_asr_engine_name
        print(f"🤖 Moteur ASR sélectionné: {get_asr_engine_name()}")
    except ImportError:
        print("🤖 Moteur ASR sélectionné: Lecteur de fichier VTT local (Parser v2)")
    except Exception:
         print("🤖 Moteur ASR sélectionné: Lecteur de fichier VTT local (Parser v2)")
    
    print(SEPARATOR)
    print(f"🤖 Démarrage du projet {PROJECT_NAME} (IA: MISTRAL)")
    print(SEPARATOR)


    if mode == 'ask':
        
        # --- MODE 1 : QUESTION UNIQUE ('ask') ---
        print(SEPARATOR)
        print(f"🤖 Mode Question Unique (Ask) : '{question_content}'")
        
        start_time = time.time()
        
        answer = await ask_ma(mistral_client, question_content) 
        
        end_time = time.time()

        if answer == "SKIP":
            print(f"\n[{time.strftime('%H:%M:%S', time.localtime())}] 🚫 Message de politesse ignoré (skip).")
            return 

        print(SEPARATOR)
        print(f"🤖 Réponse de ma ({PROJECT_NAME}) :")
        print(answer)
        print(SEPARATOR)
        print(f"Temps de réponse de l'IA: {end_time - start_time:.2f} secondes")
        return

    elif mode == 'vtt':
        
        # --- MODE 2 : LECTURE VTT & FACT-CHECKING ---
        print(SEPARATOR)
        print("🤖 Fact-Checker Critique (Mode Ingestion VTT Automatique)")
        affirmations_input = get_affirmations_from_vtt()
        await fact_checker_batch(affirmations_input, mode)

    elif mode == 'manual':
        
        # --- MODE 3 : SAISIE MANUELLE & FACT-CHECKING --
        print(SEPARATOR)
        print("Mode Fact-Checker Manuel")
        affirmations_input = get_user_input()
        await fact_checker_batch(affirmations_input, mode)


# --- Point d'entrée --
if __name__ == '__main__':
    if sys.version_info >= (3, 7):
        if os.name == 'nt':
            import asyncio
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    asyncio.run(main_async())
