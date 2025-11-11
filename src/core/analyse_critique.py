#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module d'analyse critique pour MistralAI - Version corrigée et complète

Ce module contient toutes les fonctions nécessaires pour l'analyse critique des affirmations
en utilisant l'API MistralAI. Il est conçu pour être :
- Modulaire : chaque fonction a une responsabilité unique
- Robuste : gestion complète des erreurs
- Documenté : commentaires exhaustifs
- Testable : fonctions pures et effets de bord minimisés
- Maintenable : code propre et bien structuré
"""

# =============================================
# IMPORTS
# =============================================
import os
import sys
import logging
import asyncio
from typing import List, Dict, Any, Optional, Union
from pathlib import Path
import json
from datetime import datetime
import re
from functools import wraps

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# =============================================
# CLASSES DE CONFIGURATION ET D'ERREURS
# =============================================
class Config:
    """
    Classe de configuration centrale pour l'application

    Cette classe contient toutes les constantes de configuration utilisées dans l'application.
    Centraliser la configuration permet :
    - Une maintenance plus facile
    - Une évolution plus simple
    - Une cohérence dans tout le projet
    - Une modification aisée des paramètres
    """
    DEFAULT_MODEL = "mistral-small-latest"
    TIMEOUT = 30
    MAX_RETRIES = 3
    RETRY_DELAY = 2
    MAX_TOKENS = 1000
    TEMPERATURE = 0.7
    MIN_CLAIM_LENGTH = 10
    MAX_CLAIM_LENGTH = 500

class MistralAnalysisError(Exception):
    """
    Exception personnalisée pour les erreurs d'analyse

    Créer des exceptions personnalisées permet :
    - Une meilleure gestion des erreurs spécifiques
    - Une identification plus facile des problèmes
    - Une séparation claire des différents types d'erreurs
    - Une documentation plus précise des erreurs
    """
    pass

# =============================================
# DÉCORATEURS
# =============================================
def retry(max_attempts: int = Config.MAX_RETRIES, delay: int = Config.RETRY_DELAY):
    """
    Décorateur pour implémenter une logique de réessai

    Ce décorateur permet d'implémenter facilement une logique de réessai
    pour les fonctions asynchrones qui peuvent échouer temporairement.

    Args:
        max_attempts: Nombre maximal de tentatives
        delay: Délai entre les tentatives en secondes

    Returns:
        function: Décorateur pour les fonctions asynchrones
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts:
                        logger.warning(f"Tentative {attempt} échouée. Réessai dans {delay} secondes...")
                        await asyncio.sleep(delay)
                    continue
            logger.error(f"Toutes les {max_attempts} tentatives ont échoué")
            raise last_exception
        return wrapper
    return decorator

# =============================================
# FONCTIONS UTILITAIRES
# =============================================
def validate_text(text: Union[str, Dict]) -> bool:
    """
    Valide qu'un texte ou dictionnaire d'affirmation est valide

    Args:
        text: Le texte ou dictionnaire à valider

    Returns:
        bool: True si le texte est valide, False sinon
    """
    if isinstance(text, dict):
        return isinstance(text.get('affirmation'), str) and \
               Config.MIN_CLAIM_LENGTH < len(text['affirmation'].strip()) <= Config.MAX_CLAIM_LENGTH
    elif isinstance(text, str):
        return Config.MIN_CLAIM_LENGTH < len(text.strip()) <= Config.MAX_CLAIM_LENGTH
    return False

def format_affirmation(affirmation: Union[str, Dict]) -> str:
    """
    Formate une affirmation pour l'analyse

    Args:
        affirmation: L'affirmation à formater

    Returns:
        str: L'affirmation formatée
    """
    if isinstance(affirmation, dict):
        return affirmation.get('affirmation', '').strip()
    return str(affirmation).strip()

def format_response(response: Any) -> str:
    """
    Formate une réponse de l'API pour un affichage propre

    Args:
        response: La réponse brute de l'API

    Returns:
        str: La réponse formatée
    """
    if not response:
        return "Aucune réponse valide reçue"

    if isinstance(response, str):
        return response.strip()

    if hasattr(response, 'choices') and len(response.choices) > 0:
        if hasattr(response.choices[0], 'message') and hasattr(response.choices[0].message, 'content'):
            return response.choices[0].message.content.strip()

    return str(response).strip()

def get_mistral_client(api_key: Optional[str] = None) -> Any:
    """
    Initialise et retourne un client Mistral

    Args:
        api_key: Clé API MistralAI (optionnelle)

    Returns:
        Any: Client Mistral initialisé

    Raises:
        MistralAnalysisError: Si l'initialisation échoue
    """
    try:
        from mistralai.client import Mistral
    except ImportError as e:
        raise MistralAnalysisError(f"Erreur critique: Impossible de charger mistralai: {str(e)}")

    api_key = api_key or os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise MistralAnalysisError("Clé API MistralAI non configurée")

    try:
        client = Mistral(api_key=api_key)
        logger.info("Client Mistral initialisé avec succès")
        return client
    except Exception as e:
        raise MistralAnalysisError(f"Erreur d'initialisation du client: {str(e)}")

# =============================================
# CLASSE PRINCIPALE D'ANALYSE
# =============================================
class MistralAnalyzer:
    """
    Classe principale pour l'analyse avec MistralAI

    Cette classe encapsule toute la logique d'analyse et fournit
    une interface simple pour l'analyse des affirmations.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialise l'analyseur

        Args:
            api_key: Clé API MistralAI (optionnelle)
        """
        self.client = get_mistral_client(api_key)
        logger.info("MistralAnalyzer initialisé avec succès")

    @retry()  # Maintenant que le décorateur est défini, on peut l'utiliser
    async def analyze(self, affirmation: Union[str, Dict], mode: str = "GENERAL") -> Dict[str, Any]:
        """
        Analyse une affirmation avec la stratégie spécifiée

        Args:
            affirmation: Affirmation à analyser
            mode: Mode d'analyse (GENERAL ou STATISTIQUE)

        Returns:
            Dict[str, Any]: Résultat de l'analyse

        Raises:
            MistralAnalysisError: Si l'analyse échoue
        """
        if not validate_text(affirmation):
            raise MistralAnalysisError("Affirmation invalide ou vide")

        try:
            formatted_aff = format_affirmation(affirmation)

            if mode == "STATISTIQUE":
                system_prompt = "Vous êtes un assistant spécialisé dans la vérification des statistiques."
                user_prompt = f"Vérifiez cette statistique: {formatted_aff}"
            else:
                system_prompt = "Vous êtes un assistant généraliste spécialisé dans la vérification des faits."
                user_prompt = f"Vérifiez cette affirmation: {formatted_aff}"

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            response = await self.client.chat(
                model=Config.DEFAULT_MODEL,
                messages=messages,
                timeout=Config.TIMEOUT
            )

            return {
                "affirmation": formatted_aff,
                "analyse": format_response(response),
                "mode": mode,
                "model": Config.DEFAULT_MODEL,
                "status": "success"
            }

        except Exception as e:
            raise MistralAnalysisError(f"Erreur d'analyse: {str(e)}")

    async def batch_analyze(self, affirmations: List[Union[str, Dict]], mode: str = "GENERAL") -> List[Dict[str, Any]]:
        """
        Analyse un lot d'affirmations

        Args:
            affirmations: Liste d'affirmations à analyser
            mode: Mode d'analyse

        Returns:
            List[Dict[str, Any]]: Liste des résultats d'analyse
        """
        results = []
        for i, aff in enumerate(affirmations, 1):
            try:
                result = await self.analyze(aff, mode)
                results.append({
                    "id": i,
                    **result
                })
            except Exception as e:
                error_msg = str(e)
                aff_text = format_affirmation(aff)
                results.append({
                    "id": i,
                    "affirmation": aff_text,
                    "analyse": error_msg,
                    "status": "error",
                    "error": error_msg
                })
        return results

# =============================================
# FONCTIONS SUPPLÉMENTAIRES
# =============================================
async def fact_checker_batch_async(
    client: Any,
    affirmations: List[Union[str, Dict]],
    model: str = Config.DEFAULT_MODEL
) -> List[Dict[str, Any]]:
    """
    Fonction de vérification de batch asynchrone pour le fact-checking

    Args:
        client: Client Mistral initialisé
        affirmations: Liste d'affirmations à analyser
        model: Modèle à utiliser

    Returns:
        List[Dict[str, Any]]: Liste des résultats d'analyse
    """
    results = []
    for i, aff in enumerate(affirmations, 1):
        try:
            analyzer = MistralAnalyzer()  # Crée une nouvelle instance de l'analyseur
            result = await analyzer.analyze(aff, "GENERAL")
            results.append({
                "id": i,
                **result
            })
        except Exception as e:
            error_msg = str(e)
            aff_text = format_affirmation(aff)
            results.append({
                "id": i,
                "affirmation": aff_text,
                "analyse": error_msg,
                "status": "error",
                "error": error_msg
            })
    return results

def afficher_rapport_final(results: List[Dict[str, Any]], mode: str = None) -> None:
    """
    Affiche un rapport final formaté des résultats

    Args:
        results: Liste des résultats à afficher
        mode: Mode d'affichage (optionnel)
    """
    print("\n" + "="*80)
    print("RAPPORT FINAL D'ANALYSE".center(80))
    if mode:
        print(f"Mode: {mode}".center(80))
    print("="*80 + "\n")

    for result in results:
        status_color = "\033[92m" if result.get("status") == "success" else "\033[91m"
        reset_color = "\033[0m"

        aff_text = format_affirmation(result.get('affirmation', ''))
        analysis = result.get('analyse', 'Aucune analyse disponible')

        print(f"\n{status_color}ID: {result.get('id', '')}{reset_color}")
        print(f"Affirmation: {aff_text}")
        print("-"*60)
        print("Analyse:")
        print(analysis)
        if result.get("status") == "error":
            print(f"{status_color}Erreur: {result.get('error', '')}{reset_color}")
        print("-"*60)

    print("\n" + "="*80)
    stats = {
        "total": len(results),
        "success": sum(1 for r in results if r.get("status") == "success"),
        "errors": sum(1 for r in results if r.get("status") == "error")
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
    client: Any,
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
        str: Réponse formatée

    Raises:
        MistralAnalysisError: Si la question échoue
    """
    if not isinstance(question, str) or not question.strip():
        raise MistralAnalysisError("Question invalide ou vide")

    try:
        analyzer = MistralAnalyzer()  # Crée une nouvelle instance de l'analyseur
        # Utilise la méthode analyze avec un prompt spécifique pour les questions
        response = await analyzer.analyze({"affirmation": question}, "QUESTION")
        return response.get('analyse', '')
    except Exception as e:
        raise MistralAnalysisError(f"Erreur lors de la question: {str(e)}")
