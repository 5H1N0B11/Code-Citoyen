#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script principal pour le fact-checking en direct - Version refactorisée

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
from datetime import datetime
import argparse
import readline
from collections import deque

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
    result_dir = current_dir / "results"
    result_dir.mkdir(exist_ok=True, parents=True)
    project_root = current_dir.parent
    if str(project_root) not in sys.path:
        sys.path.append(str(project_root))
    logger.info("Configuration des chemins réussie")
except Exception as e:
    logger.error(f"Erreur de configuration des chemins: {str(e)}")
    sys.exit(1)

# Imports spécifiques au projet
from src.core.orchestrator import AnalysisOrchestrator
from src.core.ingestion_pipeline import ingest_from_local_vtt
from src.core.context_fetcher import fetch_speaker_background, guess_speakers_from_filename
from src.utils import validate_text, format_affirmation

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
# CLASSES UTILITAIRES
# =============================================

class HistoryManager:
    """Gestionnaire d'historique des affirmations."""
    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self.history = deque(maxlen=max_size)
        self.history_file = result_dir / "history.json"
        self.load_history()

    def add_to_history(self, item: Dict[str, Any]) -> None:
        self.history.append(item)
        self.save_history()

    def get_history(self) -> List[Dict[str, Any]]:
        return list(self.history)

    def save_history(self) -> None:
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(list(self.history), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde de l'historique: {str(e)}")

    def load_history(self) -> None:
        try:
            if self.history_file.exists():
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.history = deque(json.load(f), maxlen=self.max_size)
        except Exception as e:
            logger.error(f"Erreur lors du chargement de l'historique: {str(e)}")
            self.history = deque(maxlen=self.max_size)

class AffirmationProcessor:
    """Processeur d'affirmations, gérant la logique de traitement."""
    def __init__(self, orchestrator: AnalysisOrchestrator):
        self.orchestrator = orchestrator
        self.history_manager = HistoryManager()

    async def process_affirmation(self, affirmation: Union[str, Dict], global_context: Optional[str] = None) -> Dict[str, Any]:
        """Traite une affirmation unique de manière robuste."""
        try:
            if not validate_text(affirmation):
                raise ValueError("Affirmation invalide ou vide")
            
            # La logique de contexte historique sera ajoutée ici (Tâche 1.2)
            # history = self.history_manager.get_recent_history()
            # result = await self.orchestrator.analyze(affirmation, history=history, global_context=global_context)
            
            result = await self.orchestrator.analyze(affirmation, global_context=global_context)

            processed_result = {
                "timestamp": datetime.now().isoformat(),
                "affirmation": format_affirmation(affirmation),
                "result": result
            }
            self.history_manager.add_to_history(processed_result)
            return processed_result

        except Exception as e:
            error_msg = str(e)
            aff_text = format_affirmation(affirmation)
            error_report = {
                "timestamp": datetime.now().isoformat(),
                "affirmation": aff_text,
                "status": "error",
                "error_type": type(e).__name__,
                "error_message": error_msg,
            }
            self.history_manager.add_to_history(error_report)
            return error_report

    async def process_batch(self, affirmations: List[Union[str, Dict]], global_context: Optional[str] = None) -> List[Dict[str, Any]]:
        """Traite un lot d'affirmations en parallèle contrôlé."""
        tasks = [self.process_affirmation(aff, global_context=global_context) for aff in affirmations]
        results_raw = await asyncio.gather(*tasks)
        return [{"id": i, **res} for i, res in enumerate(results_raw, 1)]

# =============================================
# FONCTIONS D'AFFICHAGE ET DE SAUVEGARDE
# =============================================

def display_results(results: List[Dict[str, Any]]) -> None:
    """Affiche les résultats de manière formatée dans la console."""
    print("\n" + "="*80 + "\n" + "RAPPORT D'ANALYSE".center(80) + "\n" + "="*80 + "\n")
    for result in results:
        if result.get("status") == "error":
            color, aff_text, analysis, category = COLORS['error'], result.get('affirmation', 'N/A'), f"Erreur: {result.get('error_message', 'Inconnue')}", "ERREUR"
        else:
            color, aff_text, analysis, category = COLORS['success'], result.get('result', {}).get('affirmation', 'N/A'), result.get('result', {}).get('analyse', 'N/A'), result.get('result', {}).get('category', 'N/A')
        
        print(f"\n{color}ID: {result.get('id', '')}{COLORS['reset']}\nAffirmation: {aff_text}\nCatégorie: {category}\n" + "-"*60 + f"\nAnalyse:\n{analysis}\n" + "-"*60)

    stats = {"total": len(results), "success": sum(1 for r in results if r.get("result", {}).get("status") == "success"), "errors": sum(1 for r in results if r.get("status") == "error")}
    print("\n" + "="*80 + f"\nSTATISTIQUES: {stats['success']} réussites, {stats['errors']} erreurs sur {stats['total']} analyses\n" + "="*80 + "\n")

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
# NOUVELLE FONCTION CENTRALE DE TRAITEMENT
# =============================================

async def run_analysis_and_save(processor: AffirmationProcessor, affirmations: List[Union[str, Dict]], mode_name: str, source_identifier: str, global_context: Optional[str] = None) -> None:
    """
    Fonction centrale qui orchestre l'analyse, l'affichage et la sauvegarde.
    
    Args:
        processor: L'instance du processeur d'affirmations.
        affirmations: La liste des affirmations à analyser.
        mode_name: Le nom du mode (ex: "vtt", "fichier").
        source_identifier: Un identifiant pour la source (ex: nom du fichier).
        global_context: Le contexte global de la discussion.
    """
    if not affirmations:
        print("Aucune affirmation à traiter.")
        return

    print(f"\nTraitement de {len(affirmations)} affirmations en mode '{mode_name}'...")
    results = await processor.process_batch(affirmations, global_context=global_context)
    display_results(results)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_path = result_dir / f"resultats_{mode_name}_{source_identifier}_{timestamp}.json"
    save_results_to_file(results, str(result_path))

# =============================================
# MODES DE FONCTIONNEMENT (SIMPLIFIÉS)
# =============================================

async def interactive_mode(processor: AffirmationProcessor) -> None:
    """Mode interactif pour une analyse phrase par phrase."""
    print("\n" + "="*80 + "\n" + "MODE INTERACTIF".center(80) + "\n" + "="*80)
    print("\nEntrez une affirmation à vérifier. 'quit' ou 'q' pour quitter.")
    while True:
        try:
            user_input = input("\n> ").strip()
            if not user_input: continue
            if user_input.lower() in ('quit', 'exit', 'q'): break
            
            # Le mode interactif est le seul qui appelle process_affirmation directement
            print("\nTraitement de l'affirmation...")
            result = await processor.process_affirmation(user_input)
            display_results([{"id": 1, **result}])
        except (KeyboardInterrupt, EOFError):
            print("\nFin du mode interactif.")
            break
        except Exception as e:
            print(f"{COLORS['error']}Erreur: {str(e)}{COLORS['reset']}")

async def batch_mode(processor: AffirmationProcessor) -> None:
    """Mode pour coller un lot d'affirmations."""
    print("\n" + "="*80 + "\n" + "MODE BATCH".center(80) + "\n" + "="*80)
    print("\nCollez vos affirmations (une par ligne), puis Ctrl+D (Linux/macOS) ou Ctrl+Z+Enter (Windows) pour terminer:")
    try:
        affirmations = [line.strip() for line in sys.stdin if line.strip()]
        await run_analysis_and_save(processor, affirmations, "batch", "manuel")
    except Exception as e:
        print(f"{COLORS['error']}Erreur en mode batch: {str(e)}{COLORS['reset']}")

async def file_mode(processor: AffirmationProcessor) -> None:
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
        await run_analysis_and_save(processor, affirmations, "fichier", file_path.stem)
    except Exception as e:
        print(f"{COLORS['error']}Erreur en mode fichier: {str(e)}{COLORS['reset']}")

async def vtt_mode(processor: AffirmationProcessor) -> None:
    """Mode pour analyser une transcription de fichier .vtt."""
    print("\n" + "="*80 + "\n" + "MODE VTT (TRANSCRIPTION)".center(80) + "\n" + "="*80)
    try:
        file_path_str = input("\nChemin du fichier .vtt > ").strip()
        file_path = Path(file_path_str)
        if not file_path.is_file() or file_path.suffix.lower() != '.vtt':
            print(f"{COLORS['error']}Erreur: '{file_path}' n'est pas un fichier .vtt valide.{COLORS['reset']}")
            return

        affirmations = ingest_from_local_vtt(str(file_path))
        if not affirmations:
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

        global_context = ""
        if speaker_names:
            print("\nRecherche du background des participants...")
            backgrounds = await asyncio.gather(*(fetch_speaker_background(name, processor.semaphore) for name in speaker_names))
            global_context = "\n".join(backgrounds)
            print("\n" + "-"*40 + "\nCONTEXTE GLOBAL IDENTIFIÉ :\n" + global_context + "\n" + "-"*40 + "\n")
        
        await run_analysis_and_save(processor, affirmations, "vtt", file_path.stem, global_context)
    except Exception as e:
        print(f"{COLORS['error']}Erreur en mode VTT: {str(e)}{COLORS['reset']}")

async def default_mode(processor: AffirmationProcessor) -> None:
    """Mode exécutant une analyse sur des affirmations prédéfinies."""
    print("\n" + "="*80 + "\n" + "MODE PAR DÉFAUT".center(80) + "\n" + "="*80)
    try:
        await run_analysis_and_save(processor, DEFAULT_AFFIRMATIONS, "default", "default")
    except Exception as e:
        print(f"{COLORS['error']}Erreur en mode par défaut: {str(e)}{COLORS['reset']}")

# =============================================
# FONCTION PRINCIPALE (MAIN)
# =============================================

async def main() -> None:
    """Fonction principale qui initialise et lance le menu."""
    try:
        print("\n" + "="*80 + "\n" + "FACT CHECKER - ANALYSE CRITIQUE".center(80) + "\n" + "="*80)
        orchestrator = await AnalysisOrchestrator.create()
        processor = AffirmationProcessor(orchestrator=orchestrator)

        menu_options = {
            "1": ("Mode interactif", interactive_mode),
            "2": ("Mode batch (coller le texte)", batch_mode),
            "3": ("Mode fichier (lire un .txt)", file_mode),
            "4.": ("Mode VTT (lire une transcription)", vtt_mode),
            "5": ("Mode par défaut", default_mode),
            "6": ("Quitter", None)
        }

        while True:
            print("\nMENU PRINCIPAL:")
            for key, (desc, _) in menu_options.items(): print(f"{key}. {desc}")
            
            choice = input("\nChoisissez une option (1-6): ").strip()
            
            if choice in menu_options:
                desc, func = menu_options[choice]
                if func:
                    await func(processor)
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