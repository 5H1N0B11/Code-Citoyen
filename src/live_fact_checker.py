#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script principal pour le fact-checking en direct - Version complète avec commentaires exhaustifs

Ce script est le point d'entrée principal pour l'application de fact-checking. Il gère :
- L'interaction avec l'utilisateur
- Le traitement des affirmations
- L'affichage des résultats
- La gestion des différents modes d'analyse

Principes respectés :
1. Vérité et neutralité : Le code ne fait que traiter des données sans les altérer
2. Robustesse : Gestion complète des erreurs et des cas limites
3. Maintenabilité : Code bien structuré et documenté
4. Extensibilité : Architecture modulaire
5. Bonne pratiques : Utilisation des patterns de conception, typage fort, etc.
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

# Configuration du logging - Essentielle pour le débogage et le suivi
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('fact_checker.log')
    ]
)
logger = logging.getLogger(__name__)

# Configuration des chemins - Permet une bonne gestion des chemins dans le projet
try:
    current_file = Path(__file__).name
    current_dir = Path(__file__).parent.absolute()
    result_dir = current_dir / "results"
    result_dir.mkdir(exist_ok=True, parents=True)

    # Ajout du chemin parent au path Python pour les imports locaux
    project_root = current_dir.parent
    if str(project_root) not in sys.path:
        sys.path.append(str(project_root))

    logger.info("Configuration des chemins réussie")
except Exception as e:
    logger.error(f"Erreur de configuration des chemins: {str(e)}")
    sys.exit(1)

# Imports spécifiques au projet
from core.analyse_critique import (
    CritiqueAnalyzer
)
from core.utils import (
    validate_text,
    validate_text,
    format_affirmation,
)

# =============================================
# CONSTANTES ET CONFIGURATIONS
# =============================================

# Affirmations par défaut pour les tests et démonstrations
DEFAULT_AFFIRMATIONS = [
    "La Terre est plate.",
    "Le changement climatique est causé par l'activité humaine.",
    "75% des Français pensent que l'IA va améliorer leur vie.",
    "Paris est la capitale de la France.",
    "La Lune est faite de fromage.",
    "Quitter l'Islam n'est pas risquer sa vie, d'après les textes",
    "La France a le droit de suspendre la Convention Européenne des Droits de l'Homme",
    "Depuis qu'on a le métro, la criminalité a augmenté",
    "Les jeunes d'aujourd'hui ne lisent plus de livres.",
    "Depuis qu'on a mis des caméras de surveillance, les accidents de voiture ont augmenté.",
    "Le grand professeur X a dit que le vaccin était inutile, donc je ne le prends pas.",
    "On ne peut pas écouter ce que dit ce politicien, il a été mis en examen il y a 10 ans.",
    "Le taux de chômage en France est de 7,3%.",
    "La France est le pays le plus taxé d'Europe.",
    "L'eucharistie est un sacrement pour toutes les églises protestantes.",
    "Les pyramides d'Égypte ont été construites par des esclaves.",
    "En France, la majorité pénale est fixée à 18 ans.",
    "La Terre est une Sphère.",
    "Les Russes ont fait des crimes de guerres en Ukraine.",
    "Le Hamas execute son propre peuple.",
    "Manger du chocolat rend génial.",
    "Tu devrais toujours vérifier tes sources avant de partager."
]

# Configuration des couleurs pour l'affichage
COLORS = {
    'success': '\033[92m',
    'error': '\033[91m',
    'warning': '\033[93m',
    'info': '\033[94m',
    'reset': '\033[0m'
}

# =============================================
# CLASSES UTILITAIRES
# =============================================

class HistoryManager:
    """
    Gestionnaire d'historique des affirmations

    Cette classe gère :
    - Le stockage des affirmations précédentes
    - La récupération de l'historique
    - La sauvegarde et le chargement de l'historique
    """

    def __init__(self, max_size: int = 100):
        """
        Initialise le gestionnaire d'historique

        Args:
            max_size: Taille maximale de l'historique
        """
        self.max_size = max_size
        self.history = deque(maxlen=max_size)
        self.history_file = result_dir / "history.json"

        # Charger l'historique existant
        self.load_history()

    def add_to_history(self, item: Dict[str, Any]) -> None:
        """
        Ajoute un élément à l'historique

        Args:
            item: Élément à ajouter à l'historique
        """
        self.history.append(item)
        self.save_history()

    def get_history(self) -> List[Dict[str, Any]]:
        """
        Récupère l'historique complet

        Returns:
            List[Dict[str, Any]]: Liste des éléments de l'historique
        """
        return list(self.history)

    def save_history(self) -> None:
        """
        Sauvegarde l'historique dans un fichier
        """
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(list(self.history), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde de l'historique: {str(e)}")

    def load_history(self) -> None:
        """
        Charge l'historique depuis un fichier
        """
        try:
            if self.history_file.exists():
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.history = deque(json.load(f), maxlen=self.max_size)
        except Exception as e:
            logger.error(f"Erreur lors du chargement de l'historique: {str(e)}")
            self.history = deque(maxlen=self.max_size)

class AffirmationProcessor:
    """
    Processeur d'affirmations

    Cette classe gère :
    - Le traitement des affirmations
    - La validation des entrées
    - La gestion des erreurs
    """

    def __init__(self, analyzer: CritiqueAnalyzer):
        """
        Initialise le processeur d'affirmations

        Args:
            analyzer: Instance de CritiqueAnalyzer pour l'analyse
        """
        self.analyzer = analyzer
        self.history_manager = HistoryManager()

    async def process_affirmation(self, affirmation: Union[str, Dict], semaphore: asyncio.Semaphore = None) -> Dict[str, Any]:
        """
        Traite une affirmation unique

        Args:
            affirmation: Affirmation à traiter

        Returns:
            Dict[str, Any]: Résultat du traitement
        """
        # Le sémaphore garantit que cette section n'est exécutée que par un nombre limité de tâches à la fois.
        async with semaphore if semaphore else asyncio.Semaphore(1):
            try:
                # Validation de l'affirmation
                if not validate_text(affirmation):
                    raise ValueError("Affirmation invalide ou vide")

                # Analyse de l'affirmation
                result = await self.analyzer.analyze(affirmation)

                # Ajout à l'historique
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

                # Création d'un rapport d'erreur détaillé
                error_report = {
                    "timestamp": datetime.now().isoformat(),
                    "affirmation": aff_text,
                    "status": "error",
                    "error_type": type(e).__name__,
                    "error_message": error_msg,
                    "details": {
                        "type": "str" if isinstance(affirmation, str) else "dict",
                        "length": len(aff_text)
                    }
                }

                # Ajout à l'historique même en cas d'erreur
                self.history_manager.add_to_history(error_report)
                return error_report

    async def process_batch(self, affirmations: List[Union[str, Dict]]) -> List[Dict[str, Any]]:
        """
        Traite un lot d'affirmations

        Args:
            affirmations: Liste d'affirmations à traiter

        Returns:
            List[Dict[str, Any]]: Liste des résultats
        """
        # Création d'une liste de tâches asynchrones
        tasks = [self.process_affirmation(aff) for aff in affirmations]
        # Exécution de toutes les tâches en parallèle
        results_raw = await asyncio.gather(*tasks)
        
        # Ajout de l'ID à chaque résultat
        return [{"id": i, **res} for i, res in enumerate(results_raw, 1)]

# =============================================
# FONCTIONS PRINCIPALES
# =============================================

def display_results(results: List[Dict[str, Any]]) -> None:
    """
    Affiche les résultats de manière formatée

    Args:
        results: Liste des résultats à afficher
    """
    print("\n" + "="*80)
    print("RAPPORT D'ANALYSE".center(80))
    print("="*80 + "\n")

    for result in results:
        status = result.get("status", "unknown")
        color = COLORS.get(status, COLORS['info'])

        aff_text = format_affirmation(result.get('affirmation', {}))
        analysis = result.get('result', {}).get('analyse', 'Aucune analyse disponible')
        category = result.get('result', {}).get('category', 'Non déterminée')

        print(f"\n{color}ID: {result.get('id', '')}{COLORS['reset']}")
        print(f"Affirmation: {aff_text}")
        print(f"Catégorie: {category}")
        print("-"*60)
        print("Analyse:")
        print(analysis)

        if result.get("status") == "error":
            print(f"{COLORS['error']}Erreur: {result.get('error_message', 'Erreur inconnue')}{COLORS['reset']}")
        print("-"*60)

    print("\n" + "="*80)
    stats = {
        "total": len(results),
        "success": sum(1 for r in results if r.get("result", {}).get("status") == "success"),
        "errors": sum(1 for r in results if r.get("status") == "error")
    }
    print(f"STATISTIQUES: {stats['success']} réussites, {stats['errors']} erreurs sur {stats['total']} analyses")
    print("="*80 + "\n")

def save_results_to_file(results: List[Dict[str, Any]], filename: str) -> None:
    """
    Sauvegarde les résultats dans un fichier

    Args:
        results: Liste des résultats à sauvegarder
        filename: Nom du fichier de sortie
    """
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        logger.info(f"Résultats sauvegardés dans {filename}")
    except Exception as e:
        logger.error(f"Erreur lors de la sauvegarde des résultats: {str(e)}")
        print(f"{COLORS['error']}Erreur lors de la sauvegarde des résultats: {str(e)}{COLORS['reset']}")

async def interactive_mode(processor: AffirmationProcessor) -> None:
    """
    Mode interactif pour le fact-checking

    Args:
        processor: Instance de AffirmationProcessor
    """
    print("\n" + "="*80)
    print("MODE INTERACTIF".center(80))
    print("="*80)
    print("\nEntrez vos affirmations à vérifier une par une.")
    print("Entrez 'quit', 'exit' ou 'q' pour terminer.")
    print("Entrez 'history' pour voir l'historique.")
    print("Entrez 'clear' pour effacer l'historique.")

    while True:
        try:
            user_input = input("\n> ").strip()

            if not user_input:
                continue

            if user_input.lower() in ('quit', 'exit', 'q'):
                break

            if user_input.lower() == 'history':
                history = processor.history_manager.get_history()
                print("\nHISTORIQUE DES AFFIRMATIONS:")
                for i, item in enumerate(history, 1):
                    status = item.get("status", "unknown")
                    color = COLORS.get(status, COLORS['info'])
                    print(f"{color}{i}. {item.get('affirmation', 'Inconnu')}{COLORS['reset']}")
                continue

            if user_input.lower() == 'clear':
                processor.history_manager.history.clear()
                processor.history_manager.save_history()
                print("Historique effacé.")
                continue

            # Correction : Traiter chaque affirmation individuellement
            print("\nTraitement de l'affirmation...")
            result = await processor.process_affirmation(user_input)
            display_results([{"id": 1, **result}]) # On l'affiche comme un batch d'un seul élément

        except KeyboardInterrupt:
            print("\nInterrompu par l'utilisateur")
            break
        except Exception as e:
            print(f"{COLORS['error']}Erreur: {str(e)}{COLORS['reset']}")
            continue

async def batch_mode(processor: AffirmationProcessor) -> None:
    """
    Mode batch pour le fact-checking

    Args:
        processor: Instance de AffirmationProcessor
    """
    print("\n" + "="*80)
    print("MODE BATCH".center(80))
    print("="*80)
    print("\nEntrez vos affirmations (une par ligne), puis Ctrl+D pour terminer:")

    try:
        affirmations = []
        while True:
            try:
                line = input().strip()
                if line:
                    affirmations.append(line)
            except EOFError:
                break

        if not affirmations:
            print("Aucune affirmation fournie")
            return

        print(f"\nTraitement de {len(affirmations)} affirmations...")
        results = await processor.process_batch(affirmations)
        display_results(results)

        # Sauvegarde des résultats avec timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_path = result_dir / f"resultats_batch_{timestamp}.json"
        save_results_to_file(results, str(result_path))
        print(f"\nRésultats sauvegardés dans {result_path}")

    except Exception as e:
        print(f"{COLORS['error']}Erreur en mode batch: {str(e)}{COLORS['reset']}")

async def file_mode(processor: AffirmationProcessor) -> None:
    """
    Mode fichier pour traiter les affirmations depuis un fichier texte.

    Args:
        processor: Instance de AffirmationProcessor
    """
    print("\n" + "="*80)
    print("MODE FICHIER".center(80))
    print("="*80)
    print("\nEntrez le chemin complet vers votre fichier d'affirmations (.txt).")
    print("Chaque ligne du fichier sera traitée comme une affirmation.")

    try:
        file_path_str = input("\nChemin du fichier > ").strip()
        file_path = Path(file_path_str)

        if not file_path.is_file():
            print(f"{COLORS['error']}Erreur: Le fichier '{file_path}' n'a pas été trouvé ou n'est pas un fichier valide.{COLORS['reset']}")
            return

        with open(file_path, 'r', encoding='utf-8') as f:
            affirmations = [line.strip() for line in f if line.strip()]

        if not affirmations:
            print("Le fichier est vide ou ne contient aucune affirmation valide.")
            return

        print(f"\nTraitement de {len(affirmations)} affirmations depuis le fichier...")
        results = await processor.process_batch(affirmations)
        display_results(results)

        # Sauvegarde des résultats
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_path = result_dir / f"resultats_fichier_{file_path.stem}_{timestamp}.json"
        save_results_to_file(results, str(result_path))

    except Exception as e:
        print(f"{COLORS['error']}Erreur en mode fichier: {str(e)}{COLORS['reset']}")

async def default_mode(processor: AffirmationProcessor) -> None:
    """
    Mode par défaut avec affirmations prédéfinies

    Args:
        processor: Instance de AffirmationProcessor
    """
    print("\n" + "="*80)
    print("MODE PAR DÉFAUT".center(80))
    print("="*80)
    print("\nExécution avec affirmations par défaut...")

    try:
        results = await processor.process_batch(DEFAULT_AFFIRMATIONS)
        display_results(results)

        # Sauvegarde des résultats
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_path = result_dir / f"resultats_default_{timestamp}.json"
        save_results_to_file(results, str(result_path))
        print(f"\nRésultats sauvegardés dans {result_path}")

    except Exception as e:
        print(f"{COLORS['error']}Erreur en mode par défaut: {str(e)}{COLORS['reset']}")

# =============================================
# FONCTION PRINCIPALE
# =============================================

async def main() -> None:
    """
    Fonction principale du script

    Cette fonction :
    1. Initialise l'analyseur et le processeur
    2. Présente un menu à l'utilisateur
    3. Gère les différents modes de fonctionnement
    4. Capture les erreurs globales
    """
    try:
        print("\n" + "="*80)
        print("FACT CHECKER - ANALYSE CRITIQUE".center(80))
        print("="*80 + "\n")

        # Initialisation de l'analyseur et du processeur
        analyzer = await CritiqueAnalyzer.create()  # Utilisation de la classe renommée
        processor = AffirmationProcessor(analyzer=analyzer)

        # Menu principal
        while True:
            print("\nMENU PRINCIPAL:")
            print("1. Mode interactif - Pour les tests et démonstrations")
            print("2. Mode batch (coller le texte) - Pour le traitement de plusieurs affirmations")
            print("3. Mode fichier (lire un .txt) - Pour les tests en masse")
            print("4. Mode par défaut - Avec affirmations prédéfinies")
            print("5. Quitter")

            choice = input("\nChoisissez une option (1-5): ").strip()

            if choice == "1":
                await interactive_mode(processor)
            elif choice == "2":
                await batch_mode(processor)
            elif choice == "3":
                await file_mode(processor)
            elif choice == "4":
                await default_mode(processor)
            elif choice == "5":
                print("Fin du programme")
                break
            else:
                print(f"{COLORS['error']}Option invalide{COLORS['reset']}")

    except KeyboardInterrupt:
        print("\nInterrompu par l'utilisateur")
    except Exception as e:
        logger.error(f"Erreur critique: {str(e)}", exc_info=True)
        print(f"{COLORS['error']}Erreur critique: {str(e)}{COLORS['reset']}")
        sys.exit(1)

# =============================================
# POINT D'ENTRÉE DU SCRIPT
# =============================================

if __name__ == "__main__":
# Configuration de readline pour une meilleure expérience utilisateur (non-Windows)
    if os.name == 'posix':
        readline.parse_and_bind('tab: complete')
        readline.parse_and_bind('set editing-mode vi')

    # Exécution asynchrone de la fonction principale
    asyncio.run(main())
