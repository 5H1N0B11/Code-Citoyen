# -*- coding: utf-8 -*-
"""
Module d'analyse critique pour MistralAI - Version complète et vérifiée
Ce fichier contient toutes les fonctions nécessaires pour le fact-checking
"""

import os
import sys
import logging
import asyncio
from typing import List, Dict, Any, Optional
from pathlib import Path
import json
from datetime import datetime

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Configuration des chemins
try:
    current_dir = Path(__file__).parent.absolute()
    project_root = current_dir.parent.parent.absolute()
    if str(project_root) not in sys.path:
        sys.path.append(str(project_root))
    logger.info("Configuration des chemins réussie")
except Exception as e:
    logger.error(f"Erreur de configuration des chemins: {str(e)}")
    sys.exit(1)

# Import de MistralAI
try:
    from mistralai import Mistral
    logger.info("Package mistralai chargé avec succès")
except ImportError as e:
    logger.error(f"Erreur critique: Impossible de charger mistralai: {str(e)}")
    logger.error("Veuillez installer avec: pip install mistralai --upgrade")
    sys.exit(1)

# Configuration centrale
class Config:
    DEFAULT_MODEL = "mistral-small-latest"
    TIMEOUT = 30
    MAX_RETRIES = 3
    RETRY_DELAY = 2

class MistralAnalysisError(Exception):
    """Exception personnalisée pour les erreurs d'analyse"""
    pass

def get_mistral_client(api_key: Optional[str] = None) -> Mistral:
    """
    Initialise et retourne un client Mistral

    Args:
        api_key: Clé API MistralAI (optionnelle)

    Returns:
        Client Mistral initialisé

    Raises:
        MistralAnalysisError: Si l'initialisation échoue
    """
    api_key = api_key or os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise MistralAnalysisError("Clé API MistralAI non configurée")

    try:
        client = Mistral(api_key=api_key)
        logger.info("Client Mistral initialisé avec succès")
        return client
    except Exception as e:
        raise MistralAnalysisError(f"Erreur d'initialisation du client: {str(e)}")

def clean_text(text: str) -> str:
    """Nettoie un texte en supprimant les espaces superflus"""
    if not text:
        return ""
    return ' '.join(text.split()).strip()

def validate_text(text: str) -> bool:
    """Valide qu'un texte n'est pas vide et contient des caractères valides"""
    return bool(text and isinstance(text, str) and len(clean_text(text)) > 0)

def format_response(response: Any) -> str:
    """Formate une réponse de l'API pour un affichage propre"""
    if not response:
        return "Aucune réponse valide reçue"

    if isinstance(response, str):
        return clean_text(response)

    if hasattr(response, 'choices') and len(response.choices) > 0:
        if hasattr(response.choices[0], 'message') and hasattr(response.choices[0].message, 'content'):
            return clean_text(response.choices[0].message.content)

    return clean_text(str(response))

async def analyze_affirmation(
    client: Mistral,
    affirmation: str,
    mode: str = "GENERAL",
    model: str = Config.DEFAULT_MODEL
) -> Dict[str, Any]:
    """
    Analyse une affirmation avec MistralAI

    Args:
        client: Client Mistral initialisé
        affirmation: Texte à analyser
        mode: Mode d'analyse (GENERAL ou STATISTIQUE)
        model: Modèle à utiliser

    Returns:
        Dictionnaire avec les résultats de l'analyse
    """
    if not validate_text(affirmation):
        raise MistralAnalysisError("Affirmation invalide")

    try:
        if mode == "STATISTIQUE":
            system_prompt = "Vous êtes un assistant spécialisé dans la vérification des statistiques."
            user_prompt = f"Vérifiez cette statistique: {affirmation}"
        else:
            system_prompt = "Vous êtes un assistant généraliste."
            user_prompt = f"Vérifiez cette affirmation: {affirmation}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        response = await client.chat(
            model=model,
            messages=messages,
            timeout=Config.TIMEOUT
        )

        return {
            "affirmation": affirmation,
            "analyse": format_response(response),
            "mode": mode,
            "model": model,
            "status": "success"
        }

    except Exception as e:
        raise MistralAnalysisError(f"Erreur d'analyse: {str(e)}")

async def fact_checker_batch_async(
    client: Mistral,
    affirmations: List[str],
    model: str = Config.DEFAULT_MODEL
) -> List[Dict[str, Any]]:
    """
    Fonction de vérification de batch asynchrone pour le fact-checking

    Args:
        client: Client Mistral initialisé
        affirmations: Liste d'affirmations à vérifier
        model: Modèle à utiliser

    Returns:
        Liste des résultats de vérification
    """
    results = []
    for i, aff in enumerate(affirmations, 1):
        try:
            result = await analyze_affirmation(client, aff, "GENERAL", model)
            results.append({
                "id": i,
                **result
            })
        except MistralAnalysisError as e:
            logger.error(f"Erreur pour l'affirmation {i}: {str(e)}")
            results.append({
                "id": i,
                "affirmation": aff,
                "analyse": str(e),
                "mode": "GENERAL",
                "model": model,
                "status": "error",
                "error": str(e)
            })
    return results

def afficher_rapport_final(results: List[Dict[str, Any]]) -> None:
    """
    Affiche un rapport final formaté des résultats

    Args:
        results: Liste des résultats à afficher
    """
    print("\n" + "="*80)
    print("RAPPORT FINAL D'ANALYSE".center(80))
    print("="*80 + "\n")

    for result in results:
        status_color = "\033[92m" if result["status"] == "success" else "\033[91m"
        reset_color = "\033[0m"

        print(f"\n{status_color}ID: {result.get('id', '')}{reset_color}")
        print(f"Affirmation: {result['affirmation']}")
        print("-"*60)
        print("Analyse:")
        print(result['analyse'])
        if "error" in result:
            print(f"{status_color}Erreur: {result['error']}{reset_color}")
        print("-"*60)

    print("\n" + "="*80)
    stats = {
        "total": len(results),
        "success": sum(1 for r in results if r["status"] == "success"),
        "errors": sum(1 for r in results if r["status"] == "error")
    }
    print(f"STATISTIQUES: {stats['success']} réussites, {stats['errors']} erreurs sur {stats['total']} analyses")
    print("="*80 + "\n")

def save_results(results: List[Dict[str, Any]], filename: str) -> None:
    """
    Sauvegarde les résultats dans un fichier JSON

    Args:
        results: Liste des résultats à sauvegarder
        filename: Nom du fichier de sortie

    Raises:
        MistralAnalysisError: Si la sauvegarde échoue
    """
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        logger.info(f"Résultats sauvegardés dans {filename}")
    except Exception as e:
        raise MistralAnalysisError(f"Erreur de sauvegarde: {str(e)}")

async def ask_ma(
    client: Mistral,
    question: str,
    model: str = Config.DEFAULT_MODEL
) -> str:
    """
    Pose une question simple à l'IA

    Args:
        client: Client Mistral
        question: Question à poser
        model: Modèle à utiliser

    Returns:
        Réponse formatée
    """
    if not validate_text(question):
        raise MistralAnalysisError("Question invalide ou vide")

    try:
        messages = [{"role": "user", "content": question}]
        response = await client.chat(
            model=model,
            messages=messages,
            timeout=Config.TIMEOUT
        )
        return format_response(response)
    except Exception as e:
        raise MistralAnalysisError(f"Erreur lors de la question: {str(e)}")

async def main():
    """Fonction principale pour démonstration"""
    try:
        client = get_mistral_client()
        affirmations = [
            "La Terre est plate.",
            "Le changement climatique est causé par l'activité humaine.",
            "75% des Français pensent que l'IA va améliorer leur vie."
        ]

        print("Début du fact-checking...")
        results = await fact_checker_batch_async(client, affirmations)
        afficher_rapport_final(results)
        save_results(results, "resultats_fact_checking.json")

    except Exception as e:
        logger.error(f"Erreur principale: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())