#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script principal pour le fact-checking en console.

Ce script est le point d'entrée principal pour l'application de fact-checking. Il gère :
- L'interaction avec l'utilisateur via un menu
- La collecte des affirmations depuis différentes sources (manuel, fichier, vtt)
- L'orchestration de l'analyse via une fonction centrale
"""

# =============================================
# IMPORTS ET CONFIGURATION INITIALE
# =============================================

# Imports standards
import sys
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any, Union, Optional
import json
import os
from datetime import datetime, timedelta
import readline

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('fact_checker.log')
    ]
)
logger = logging.getLogger(__name__)

# Configuration des chemins
try:
    current_dir = Path(__file__).parent.absolute()
    project_root = current_dir.parent.parent
    if str(project_root) not in sys.path:
        sys.path.append(str(project_root))
    result_dir = project_root / "src" / "results"
    result_dir.mkdir(exist_ok=True, parents=True)
    logger.info("Configuration des chemins réussie")
except Exception as e:
    logger.error(f"Erreur de configuration des chemins: {str(e)}")
    sys.exit(1)

# Imports spécifiques au projet
from src.ingestion.vtt_parser import ingest_from_local_vtt
from src.tools.context_fetcher import fetch_speaker_background, guess_speakers_from_filename
from src.utils import validate_text, format_affirmation
from src.core.history_manager import HistoryManager
from src.prompts import templates as prompts
from src.core.orchestrator import AnalysisOrchestrator

# =============================================
# CONSTANTES ET CONFIGURATIONS
# =============================================

DEFAULT_AFFIRMATIONS = [
    "La Terre est plate.", "Le changement climatique est causé par l'activité humaine.",
    "75% des Français pensent que l'IA va améliorer leur vie.", "Paris est la capitale de la France.",
    "La Lune est faite de fromage.", "Quitter l'Islam n'est pas risquer sa vie, d'après les textes",
    "La France a le droit de suspendre la Convention Européenne des Droits de l'Homme",
    "Depuis qu'on a le métro, la criminalité a augmenté",
    "Les jeunes d'aujourd'hui ne lisent plus de livres.",
    "Depuis qu'on a mis des caméras de surveillance, les accidents de voiture ont augmenté.",
    "Le grand professeur X a dit que le vaccin était inutile, donc je ne le prends pas.",
    "On ne peut pas écouter ce que dit ce politicien, il a été mis en examen il y a 10 ans.",
    "Le taux de chômage en France est de 7,3%.", "La France est le pays le plus taxé d'Europe.",
    "L'eucharistie est un sacrement pour toutes les églises protestantes.",
    "Les pyramides d'Égypte ont été construites par des esclaves.",
    "En France, la majorité pénale est fixée à 18 ans.", "La Terre est une Sphère.",
    "Les Russes ont fait des crimes de guerres en Ukraine.", "Le Hamas execute son propre peuple.",
    "Manger du chocolat rend génial.", "Tu devrais toujours vérifier tes sources avant de partager."
]

COLORS = {
    'success': '\033[92m', 'error': '\033[91m', 'warning': '\033[93m',
    'info': '\033[94m', 'reset': '\033[0m'
}

# =============================================
# FONCTIONS D'AFFICHAGE ET DE SAUVEGARDE
# =============================================

def generate_summary(result: Dict[str, Any]) -> str:
    """Génère un résumé concis d'une phrase à partir d'un résultat d'analyse complet."""
    if result.get("status") == "error":
        return f"Erreur: {result.get('error_message', 'Inconnue')}"

    analysis_data = result.get("result", {}).get("analyse", {})
    verdict = analysis_data.get("verdict", "INCONNU")
    category = result.get("result", {}).get("category", "INCONNUE")
    explanation = analysis_data.get("explanation_short", "Pas d'explication.")
    bias = analysis_data.get("biais_detecte", "AUCUN")

    summary = f"[{verdict} / {category}]"
    if bias and bias != "AUCUN":
        summary += f" BIAIS: {bias}."

    summary += f" {explanation}"

    return summary.strip()

def display_results(results: List[Dict[str, Any]]) -> None:
    """Affiche les résultats de manière formatée dans la console."""
    print("\n" + "="*80 + "\n" + "RAPPORT D'ANALYSE".center(80) + "\n" + "="*80 + "\n")
    for result in results:
        aff_text = result.get('affirmation', 'N/A')
        
        video_ts = result.get('video_timestamp')
        ts_display = f" [Video: {timedelta(seconds=int(video_ts))}]" if video_ts is not None else ""
        
        print(f"\n{COLORS['info']}ID: {result.get('id', '')}{ts_display}{COLORS['reset']}\nAffirmation: {aff_text}")

        if result.get("status") == "error":
            color = COLORS['error']
            print(f"{color}  -> Erreur: {result.get('error_message', 'Inconnue')}{COLORS['reset']}")
        else:
            res_data = result.get('result', {})
            analysis = res_data.get('analyse', {})
            verdict = analysis.get("verdict", "N/A")
            category = res_data.get("category", "N/A")
            explanation = analysis.get("explanation_long", "N/A")
            bias = analysis.get("biais_detecte", "AUCUN")
            bias_expl = analysis.get("bias_explanation", "")

            print(f"  - Verdict: {COLORS['success']}{verdict}{COLORS['reset']}")
            print(f"  - Catégorie: {category}")
            if bias and bias != "AUCUN":
                print(f"  - Biais Détecté: {COLORS['warning']}{bias}{COLORS['reset']} ({bias_expl})")
            print(f"  - Explication: {explanation}")

    stats = {"total": len(results), "success": sum(1 for r in results if r.get("status") != "error"), "errors": sum(1 for r in results if r.get("status") == "error")}
    print("\n" + "="*80 + f"\nSTATISTIQUES: {stats['success']} réussites, {stats['errors']} erreurs sur {stats['total']} analyses\n" + "="*80 + "\n")

def display_live_summary(result: Dict[str, Any]) -> None:
    """Affiche un résumé concis d'un seul résultat pour le mode direct."""
    color = COLORS['error'] if result.get("status") == "error" else COLORS['success']
    summary = generate_summary(result)
    print(f"{color}  └── ANALYSE LIVE : {summary}{COLORS['reset']}")

def save_results_to_file(results: List[Dict[str, Any]], filename: str) -> None:
    """Sauvegarde les résultats dans un fichier JSON."""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        logger.info(f"Résultats sauvegardés dans {filename}")
        print(f"Résultats sauvegardés dans : {filename}")
    except Exception as e:
        logger.error(f"Erreur lors de la sauvegarde des résultats: {str(e)}")
        print(f"{COLORS['error']}Erreur lors de la sauvegarde des résultats: {str(e)}{COLORS['reset']}")

# =============================================
# FONCTION CENTRALE DE TRAITEMENT
# =============================================

async def run_analysis_and_save(orchestrator: AnalysisOrchestrator, history_manager: HistoryManager, affirmations: List[Union[str, Dict]], mode_name: str, source_identifier: str, global_context: Optional[str] = None) -> None:
    """
    Fonction centrale qui orchestre l'analyse, l'affichage et la sauvegarde.
    """
    if not affirmations:
        print("Aucune affirmation à traiter.")
        return

    print(f"\nTraitement de {len(affirmations)} affirmations en mode '{mode_name}'...")
    
    results = []
    for i, aff in enumerate(affirmations, 1):
        try:
            history = history_manager.get_formatted_history()
            result = await orchestrator.analyze(affirmation=aff, history=history, global_context=global_context)
            
            processed_result = {
                "id": i,
                "timestamp": datetime.now().isoformat(),
                "affirmation": format_affirmation(aff),
                "result": result
            }
            if isinstance(aff, dict):
                if 'start' in aff:
                    processed_result['video_timestamp'] = aff['start']
                if 'speaker' in aff:
                    processed_result['speaker'] = aff['speaker']
            
            history_manager.add_to_history(processed_result)
            results.append(processed_result)

        except Exception as e:
            error_msg = str(e)
            aff_text = format_affirmation(aff)
            error_report = {
                "id": i,
                "timestamp": datetime.now().isoformat(),
                "affirmation": aff_text,
                "status": "error",
                "error_type": type(e).__name__,
                "error_message": error_msg,
            }
            history_manager.add_to_history(error_report)
            results.append(error_report)

    display_results(results)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_path = result_dir / f"resultats_{mode_name}_{source_identifier}_{timestamp}.json"
    save_results_to_file(results, str(result_path))

# =============================================
# MODES DE FONCTIONNEMENT
# =============================================

async def interactive_mode(orchestrator: AnalysisOrchestrator, history_manager: HistoryManager) -> None:
    """Mode interactif pour une analyse phrase par phrase."""
    print("\n" + "="*80 + "\n" + "MODE INTERACTIF".center(80) + "\n" + "="*80)
    print("\nEntrez une affirmation à vérifier. 'quit' ou 'q' pour quitter.")
    while True:
        try:
            user_input = input("\n> ").strip()
            if not user_input: continue
            if user_input.lower() in ('quit', 'exit', 'q'): break
            
            print("\nTraitement de l'affirmation...")
            history = history_manager.get_formatted_history()
            result = await orchestrator.analyze(affirmation=user_input, history=history)
            
            processed_result = {
                "timestamp": datetime.now().isoformat(),
                "affirmation": user_input,
                "result": result
            }
            history_manager.add_to_history(processed_result)
            display_live_summary({"id": 1, **processed_result})

        except (KeyboardInterrupt, EOFError):
            print("\nFin du mode interactif.")
            break
        except Exception as e:
            print(f"{COLORS['error']}Erreur: {str(e)}{COLORS['reset']}")

async def batch_mode(orchestrator: AnalysisOrchestrator, history_manager: HistoryManager) -> None:
    """Mode pour coller un lot d'affirmations."""
    print("\n" + "="*80 + "\n" + "MODE BATCH".center(80) + "\n" + "="*80)
    print("\nCollez vos affirmations (une par ligne), puis Ctrl+D (Linux/macOS) ou Ctrl+Z+Enter (Windows) pour terminer:")
    try:
        affirmations = [line.strip() for line in sys.stdin if line.strip()]
        await run_analysis_and_save(orchestrator, history_manager, affirmations, "batch", "manuel")
    except Exception as e:
        print(f"{COLORS['error']}Erreur en mode batch: {str(e)}{COLORS['reset']}")

async def file_mode(orchestrator: AnalysisOrchestrator, history_manager: HistoryManager) -> None:
    """Mode pour analyser les affirmations d'un fichier .txt."""
    print("\n" + "="*80 + "\n" + "MODE FICHIER (.txt)".center(80) + "\n" + "="*80)
    try:
        file_path_str = input("\nChemin du fichier .txt > ").strip()
        file_path = Path(file_path_str)
        if not file_path.is_file():
            print(f"{COLORS['error']}Erreur: Fichier non trouvé '{file_path}'.{COLORS['reset']}")
            return
        with open(file_path, 'r', encoding='utf-8') as f:
            affirmations = [line.strip() for line in f if line.strip()]
        await run_analysis_and_save(orchestrator, history_manager, affirmations, "fichier", file_path.stem)
    except Exception as e:
        print(f"{COLORS['error']}Erreur en mode fichier: {str(e)}{COLORS['reset']}")

async def vtt_mode(orchestrator: AnalysisOrchestrator, history_manager: HistoryManager) -> None:
    """Mode pour analyser une transcription de fichier .vtt."""
    print("\n" + "="*80 + "\n" + "MODE VTT (TRANSCRIPTION)".center(80) + "\n" + "="*80)
    try:
        file_path_str = input("\nChemin du fichier .vtt > ").strip()
        file_path = Path(file_path_str)
        if not file_path.is_file() or file_path.suffix.lower() != '.vtt':
            print(f"{COLORS['error']}Erreur: '{file_path}' n'est pas un fichier .vtt valide.{COLORS['reset']}")
            return

        history_manager.clear_history()
        sentences = ingest_from_local_vtt(str(file_path))
        if not sentences:
            print("Le fichier VTT est vide ou n'a pas pu être parsé.")
            return

        print("\n--- Contexte de la discussion ---")
        guessed_names = guess_speakers_from_filename(file_path.stem)
        speaker_names = []
        if guessed_names:
            print(f"Participants potentiels détectés : {', '.join(guessed_names)}")
            if input("Utiliser ces noms ? (o/n) > ").lower().strip() == 'o':
                speaker_names = guessed_names
        if not speaker_names:
            names_str = input("Entrez les noms des participants (séparés par une virgule) > ").strip()
            speaker_names = [name.strip() for name in names_str.split(',') if name.strip()]

        base_global_context = ""
        if speaker_names:
            print("\nRecherche du background des participants...")
            backgrounds = await asyncio.gather(*(fetch_speaker_background(name, orchestrator.semaphore) for name in speaker_names))
            base_global_context = "\n".join(backgrounds)
            print("\n" + "-"*40 + "\nCONTEXTE GLOBAL IDENTIFIÉ :\n" + base_global_context + "\n" + "-"*40 + "\n")

        await run_analysis_and_save(orchestrator, history_manager, sentences, "vtt", file_path.stem, base_global_context)

    except Exception as e:
        print(f"{COLORS['error']}Erreur en mode VTT: {str(e)}{COLORS['reset']}")

async def default_mode(orchestrator: AnalysisOrchestrator, history_manager: HistoryManager) -> None:
    """Mode exécutant une analyse sur des affirmations prédéfinies."""
    print("\n" + "="*80 + "\n" + "MODE PAR DÉFAUT".center(80) + "\n" + "="*80)
    try:
        await run_analysis_and_save(orchestrator, history_manager, DEFAULT_AFFIRMATIONS, "default", "default")
    except Exception as e:
        print(f"{COLORS['error']}Erreur en mode par défaut: {str(e)}{COLORS['reset']}")

# =============================================
# FONCTION PRINCIPALE (MAIN)
# =============================================

async def main() -> None:
    """Fonction principale qui initialise et lance le menu."""
    try:
        api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            logger.critical("La variable d'environnement MISTRAL_API_KEY n'est pas définie.")
            print(f"{COLORS['error']}Erreur: La clé API Mistral n'est pas configurée. Veuillez la définir dans la variable d'environnement MISTRAL_API_KEY.{COLORS['reset']}")
            sys.exit(1)

        print("\n" + "="*80 + "\n" + "FACT CHECKER - ANALYSE CRITIQUE".center(80) + "\n" + "="*80)
        orchestrator = await AnalysisOrchestrator.create(api_key=api_key)
        history_manager = HistoryManager(result_dir=result_dir)

        menu_options = {
            "1": ("Mode interactif", interactive_mode),
            "2": ("Mode batch (coller le texte)", batch_mode),
            "3": ("Mode fichier (lire un .txt)", file_mode),
            "4": ("Mode VTT (simuler un direct)", vtt_mode),
            "5": ("Mode par défaut", default_mode),
            "6": ("Quitter", None)
        }

        while True:
            print("\nMENU PRINCIPAL:")
            for key, (desc, _) in menu_options.items():
                print(f"{key}. {desc}")
            
            choice = input("\nChoisissez une option (1-6): ").strip()
            
            if choice in menu_options:
                desc, func = menu_options[choice]
                if func:
                    await func(orchestrator, history_manager)
                else:
                    print("Fin du programme.")
                    break
            else:
                print(f"{COLORS['error']}Option invalide{COLORS['reset']}")

    except (KeyboardInterrupt, EOFError):
        print("\nProgramme interrompu par l'utilisateur. Arrêt.")
    except Exception as e:
        logger.error(f"Erreur critique dans main: {str(e)}", exc_info=True)
        print(f"{COLORS['error']}\nErreur critique inattendue: {str(e)}{COLORS['reset']}")
    finally:
        print("Arrêt du Fact Checker.")
        sys.exit(0)

# =============================================
# POINT D'ENTRÉE DU SCRIPT
# =============================================

if __name__ == "__main__":
    if os.name == 'posix':
        readline.parse_and_bind('tab: complete')
        readline.parse_and_bind('set editing-mode vi')
    asyncio.run(main())
