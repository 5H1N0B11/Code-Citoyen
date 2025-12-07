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
import asyncio, time
import logging
from pathlib import Path
from typing import List, Dict, Any, Union, Optional
import json
import re
import os
from datetime import datetime, timedelta

from mistralai import Mistral
# On importe RetryError pour mieux gérer les échecs après plusieurs tentatives
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError, retry_if_exception
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
from src.core.ingestion_pipeline import ingest_from_local_vtt
from src.core.context_fetcher import fetch_speaker_background, guess_speakers_from_filename
from src.utils import validate_text, format_affirmation
from src import prompts

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

    def clear_history(self) -> None:
        """Vide l'historique en mémoire et potentiellement le fichier."""
        self.history.clear()
        # Optionnel : supprimer aussi le fichier pour ne pas le recharger au prochain lancement
        if self.history_file.exists():
            try:
                self.history_file.unlink()
                logger.info("Fichier d'historique supprimé.")
            except Exception as e:
                logger.error(f"Erreur lors de la suppression du fichier d'historique: {str(e)}")
        logger.info("Historique vidé.")

    def get_formatted_history(self, limit: int = 5) -> List[Dict[str, str]]:
        """Retourne l'historique récent formaté pour le modèle de chat."""
        formatted_history = []
        recent_history = list(self.history)[-limit:]
        for item in recent_history:
            if item.get("status") == "error":
                continue
            
            affirmation = item.get("affirmation", "N/A")
            analysis = item.get("result", {}).get("analyse", "N/A")

            formatted_history.append({"role": "user", "content": affirmation})
            formatted_history.append({"role": "assistant", "content": analysis})
        return formatted_history

class AffirmationProcessor:
    """Processeur d'affirmations, gérant la logique de traitement."""
    def __init__(self, client: Mistral, concurrency_limit: int = 5):
        self.client = client
        self.history_manager = HistoryManager()
        self.semaphore = asyncio.Semaphore(concurrency_limit)

    @retry(
        wait=wait_exponential(multiplier=1, min=4, max=60),
        stop=stop_after_attempt(5),
        # On contourne l'ImportError en inspectant le message de l'exception
        # pour détecter les erreurs de rate limiting (429). C'est une méthode de dernier recours.
        retry=retry_if_exception(lambda e: "429" in str(e) and "Rate limit exceeded" in str(e))
    )
    async def _analyze_with_mistral(self, affirmation: str, history: List[Dict[str, str]], global_context: Optional[str]):
        """Appelle l'API Mistral avec une logique de relance."""
        # Le contexte global est ajouté au prompt système pour plus de poids
        system_message = prompts.SYSTEM_PROMPT
        if global_context:
            system_message += f"\n\nContexte global de la discussion:\n{global_context}"

        user_prompt = prompts.get_user_prompt(affirmation, historique=json.dumps(history, ensure_ascii=False))

        async with self.semaphore:
            chat_response = await self.client.chat.complete_async(
                model="mistral-small-latest",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_prompt},
                ]
            )
            return json.loads(chat_response.choices[0].message.content)

    async def process_affirmation(self, affirmation: Union[str, Dict], global_context: Optional[str] = None) -> Dict[str, Any]:
        """Traite une affirmation unique de manière robuste."""
        try:
            if not validate_text(affirmation):
                raise ValueError("Affirmation invalide ou vide")

            history = self.history_manager.get_formatted_history()
            result = await self._analyze_with_mistral(affirmation, history, global_context)

            processed_result = {
                "timestamp": datetime.now().isoformat(),
                "affirmation": format_affirmation(affirmation),
                "result": result
            }
            self.history_manager.add_to_history(processed_result)
            return processed_result

        except json.JSONDecodeError as e:
            error_msg = f"Erreur de décodage JSON de la réponse de l'API: {str(e)}"
            logger.error(error_msg)
            result = {
                "timestamp": datetime.now().isoformat(),
                "affirmation": format_affirmation(affirmation),
                "status": "error",
                "error_type": "JSONDecodeError",
                "error_message": error_msg,
            }
            self.history_manager.add_to_history(result)
            return result

        except RetryError as e:
            # Spécifiquement pour les erreurs de tenacity après plusieurs essais
            error_msg = f"Échec de l'analyse après plusieurs tentatives (Rate Limit): {e.last_attempt.exception()}"
            logger.error(error_msg)
            result = {
                "timestamp": datetime.now().isoformat(),
                "affirmation": format_affirmation(affirmation),
                "status": "error",
                "error_type": "RetryError",
                "error_message": error_msg,
            }
            self.history_manager.add_to_history(result)
            return result
        except Exception as e:
            error_msg = str(e)
            aff_text = format_affirmation(affirmation)
            error_report = { # type: ignore
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

def generate_summary(result: Dict[str, Any]) -> str:
    """Génère un résumé concis d'une phrase à partir d'un résultat d'analyse complet."""
    if result.get("status") == "error":
        return f"Erreur: {result.get('error_message', 'Inconnue')}"

    analysis_data = result.get("result", {})
    verdict = analysis_data.get("verdict", "INCONNU")
    category = analysis_data.get("category", "INCONNUE")
    explanation = analysis_data.get("explanation", "Pas d'explication.")
    bias = analysis_data.get("bias_detected", "AUCUN")

    summary = f"[{verdict} / {category}]"
    if bias != "AUCUN":
        summary += f" BIAIS: {bias}."

    # Prend la première phrase de l'explication pour un résumé court.
    first_sentence = explanation.split('.')[0] + '.'
    summary += f" {first_sentence}"

    return summary.strip()

def display_results(results: List[Dict[str, Any]]) -> None:
    """Affiche les résultats de manière formatée dans la console."""
    print("\n" + "="*80 + "\n" + "RAPPORT D'ANALYSE".center(80) + "\n" + "="*80 + "\n")
    for result in results:
        aff_text = result.get('affirmation', 'N/A')
        print(f"\n{COLORS['info']}ID: {result.get('id', '')}{COLORS['reset']}\nAffirmation: {aff_text}")

        if result.get("status") == "error":
            color = COLORS['error']
            print(f"{color}  -> Erreur: {result.get('error_message', 'Inconnue')}{COLORS['reset']}")
        else:
            res_data = result.get('result', {})
            verdict = res_data.get("verdict", "N/A")
            category = res_data.get("category", "N/A")
            explanation = res_data.get("explanation", "N/A")
            bias = res_data.get("bias_detected", "AUCUN")
            bias_expl = res_data.get("bias_explanation", "")

            print(f"  - Verdict: {COLORS['success']}{verdict}{COLORS['reset']}")
            print(f"  - Catégorie: {category}")
            if bias != "AUCUN":
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
            display_live_summary({"id": 1, **result}) # Utilise le nouvel affichage résumé
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

        # On vide l'historique pour commencer une nouvelle session d'analyse
        processor.history_manager.clear_history()

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

        base_global_context = ""
        if speaker_names:
            print("\nRecherche du background des participants...")
            backgrounds = await asyncio.gather(*(fetch_speaker_background(name, processor.semaphore) for name in speaker_names))
            base_global_context = "\n".join(backgrounds)
            print("\n" + "-"*40 + "\nCONTEXTE GLOBAL IDENTIFIÉ :\n" + base_global_context + "\n" + "-"*40 + "\n")

        print(f"\nLancement de la simulation de direct pour {len(affirmations)} segments VTT...")

        # --- Nouvelle logique de direct avec buffer de phrases ---
        results = []
        result_counter = 1  # Start with ID 1

        # Construire la transcription complète et propre en premier
        clean_transcript = " ".join([format_affirmation(seg.get('text', '')) for seg in affirmations])
        clean_transcript = " ".join(clean_transcript.split())

        # Ensemble pour stocker les phrases déjà analysées et éviter les doublons
        processed_sentences = set()
        last_processed_end = 0

        for i, segment in enumerate(affirmations):
            start_time = segment.get('start', 0.0)
            next_start_time = affirmations[i+1].get('start', start_time) if i + 1 < len(affirmations) else start_time
            wait_time = next_start_time - start_time

            video_time_str = str(timedelta(seconds=int(start_time)))
            print(f"\n[{video_time_str}] Point de synchronisation...")

            # Analyser le texte depuis la dernière position traitée
            text_to_process = clean_transcript[last_processed_end:]
            sentences_found = re.split(r'(?<=[.?!])\s+', text_to_process)

            if len(sentences_found) > 1: # Au moins une phrase complète trouvée
                phrases_to_process = sentences_found[:-1]
                
                for sentence in phrases_to_process:
                    sentence = sentence.strip()
                    if sentence and validate_text(sentence) and sentence not in processed_sentences:
                        print(f"\n  -> Phrase complète détectée : \"{sentence}\"")
                        print("  -> Lancement de l'analyse...")
                        result = await processor.process_affirmation(sentence, global_context=base_global_context)
                        result_with_id = {"id": result_counter, **result}
                        display_live_summary(result_with_id)
                        results.append(result_with_id)
                        processed_sentences.add(sentence)
                        result_counter += 1
                        # Mettre à jour la position de la dernière analyse
                        last_processed_end += len(sentence) + text_to_process[len(sentence):].find(sentence) + len(sentence) if text_to_process[len(sentence):].find(sentence) != -1 else len(text_to_process)

            # Simuler l'attente jusqu'au prochain segment
            if wait_time > 0:
                wait_td = timedelta(seconds=int(wait_time))
                print(f"\n[... Attente de {wait_td} ...]")
                await asyncio.sleep(wait_time) # Utilisation correcte de l'attente asynchrone

        # Traitement final du contenu restant
        remaining_text = clean_transcript[last_processed_end:].strip()
        if remaining_text and validate_text(remaining_text) and remaining_text not in processed_sentences:
            print("\n  -> Fin du flux. Analyse du contenu final du buffer.")
            print(f"  -> Phrase finale détectée : \"{remaining_text}\"")
            print("  -> Lancement de l'analyse...")
            result = await processor.process_affirmation(remaining_text, global_context=base_global_context)
            result_with_id = {"id": result_counter, **result}
            display_live_summary(result_with_id)
            results.append(result_with_id)

        # Afficher le rapport complet à la fin de la session VTT
        print("\n\n--- FIN DE LA SIMULATION ---")
        display_results(results) # Affiche le rapport complet
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_path = result_dir / f"resultats_vtt_{file_path.stem}_{timestamp}.json"
        save_results_to_file(results, str(result_path))

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
        api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            logger.critical("La variable d'environnement MISTRAL_API_KEY n'est pas définie.")
            print(f"{COLORS['error']}Erreur: La clé API Mistral n'est pas configurée. Veuillez la définir dans la variable d'environnement MISTRAL_API_KEY.{COLORS['reset']}")
            sys.exit(1)

        print("\n" + "="*80 + "\n" + "FACT CHECKER - ANALYSE CRITIQUE".center(80) + "\n" + "="*80)
        processor = AffirmationProcessor(client=Mistral(api_key=api_key))

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