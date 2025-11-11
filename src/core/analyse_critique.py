#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module d'analyse critique pour MistralAI.

Ce module contient toutes les fonctions nécessaires pour l'analyse critique des affirmations
en utilisant l'API MistralAI. Il est conçu pour être :
- Modulaire : chaque fonction a une responsabilité unique
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
import re
from functools import wraps

# Imports depuis notre nouveau module utilitaire
from .utils import (
    Config, AnalysisError, validate_text,
    format_affirmation, format_response
)
# Import des prompts pour la logique en deux phases
from .prompts_templates import get_system_prompt_classify, get_specialized_system_prompt

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# =============================================
# ALIAS D'ERREUR SPÉCIFIQUE
# =============================================
# On peut créer un alias pour garder la spécificité si besoin
MistralAnalysisError = AnalysisError

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
def get_mistral_client(api_key: Optional[str] = None) -> Any:
    """Initialise et retourne un client Mistral

    Args:
        api_key: Clé API MistralAI (optionnelle)

    Returns:
        Any: Client Mistral initialisé

    Raises:
        MistralAnalysisError: Si l'initialisation échoue ou si la clé API est manquante.
    """
    try:
        # LA VRAIE CORRECTION FINALE : L'import se fait depuis la racine du package, pas depuis .client
        from mistralai import Mistral
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
class CritiqueAnalyzer:
    """
    Classe principale pour l'analyse avec MistralAI

    Cette classe encapsule toute la logique d'analyse et fournit
    une interface simple pour l'analyse des affirmations.
    """

    def __init__(self, client: Any, semaphore: asyncio.Semaphore):
        """
        Initialise l'analyseur avec un client déjà créé.
        Le constructeur est maintenant privé et ne doit pas être appelé directement.
        Utilisez la méthode de classe `create` à la place.

        Args:
            client: Une instance du client Mistral.
            semaphore: Un sémaphore pour limiter les appels API concurrents.
        """
        self.client = client
        self.semaphore = semaphore

    @classmethod
    async def create(cls, api_key: Optional[str] = None) -> "CritiqueAnalyzer":
        """
        Méthode de fabrique asynchrone pour créer une instance de CritiqueAnalyzer.
        C'est la méthode publique à utiliser pour l'instanciation.

        Args:
            api_key: Clé API MistralAI (optionnelle).

        Returns:
            Une nouvelle instance de CritiqueAnalyzer.
        """
        client = await asyncio.to_thread(get_mistral_client, api_key)
        # Le sémaphore est créé ici et partagé par toutes les méthodes de l'instance
        semaphore = asyncio.Semaphore(1) # SOLUTION FINALE : On force le traitement séquentiel des appels API pour éviter le rate limiting.
        analyzer = cls(client, semaphore)
        logger.info("CritiqueAnalyzer initialisé avec succès")
        return analyzer

    @retry()  # Maintenant que le décorateur est défini, on peut l'utiliser
    async def analyze(self, affirmation: Union[str, Dict], history: List[str] = None) -> Dict[str, Any]:
        """
        Analyse une affirmation en utilisant la stratégie en deux phases :
        1. Classification pour déterminer la catégorie de l'affirmation.
        2. Analyse spécialisée basée sur la catégorie trouvée.

        Args:
            affirmation: Affirmation à analyser
            history: Liste des affirmations précédentes pour le contexte.

        Returns:
            Dict[str, Any]: Résultat de l'analyse

        Raises:
            MistralAnalysisError: Si l'analyse échoue
        """
        if not validate_text(affirmation):
            raise MistralAnalysisError("Affirmation invalide ou vide")

        formatted_aff = format_affirmation(affirmation)
        
        # Préparation du contexte pour le prompt
        history_context = ""
        if history:
            history_text = "\n".join([f"- {h}" for h in history])
            history_context = f"CONTEXTE DE LA CONVERSATION PRÉCÉDENTE (pour référence uniquement) :\n{history_text}\n\n---\n\n"

        try:
            # --- PHASE 1: CLASSIFICATION ---
            logger.info(f"Phase 1: Classification de '{formatted_aff[:30]}...'")
            classification_messages = [
                {"role": "system", "content": get_system_prompt_classify()},
                {"role": "user", "content": f"{history_context}AFFIRMATION À CLASSER : \"{formatted_aff}\""}
            ]
            
            async with self.semaphore: # Attend une place dans le sémaphore
                logger.info(f"-> Appel API (Classification) pour '{formatted_aff[:20]}...'")
                classification_response = await self.client.chat.complete_async(
                    model=Config.DEFAULT_MODEL,
                    messages=classification_messages,
                    temperature=0.0
                )
            
            category_raw = format_response(classification_response)
            # Extrait la catégorie, ex: de "[LOGIQUE]" à "LOGIQUE"
            # Correction pour gérer les réponses "sales" de l'IA (ex: "RÉPONSE UNIQUE : [STATISTIQUE]")
            match = re.search(r'\[\s*([^\]]+?)\s*\]', category_raw)
            category = match.group(1).strip() if match else category_raw.strip()

            logger.info(f"Phase 1: Catégorie déterminée -> {category}")

            # --- PHASE 2: ANALYSE SPÉCIALISÉE ---
            logger.info(f"Phase 2: Lancement de l'analyse spécialisée pour la catégorie '{category}'")
            system_prompt = get_specialized_system_prompt(category)
            user_prompt = f"{history_context}Affirmation à analyser: \"{formatted_aff}\""

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            async with self.semaphore: # Attend une place dans le sémaphore
                logger.info(f"-> Appel API (Analyse) pour '{formatted_aff[:20]}...'")
                response = await self.client.chat.complete_async(
                    model=Config.DEFAULT_MODEL,
                    messages=messages,
                )

            return {
                "affirmation": formatted_aff,
                "analyse": format_response(response),
                "category": category, # On retourne la catégorie !
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
                result = await self.analyze(aff)
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
    analyzer: "CritiqueAnalyzer",
    affirmations: List[Union[str, Dict]],
    model: str = Config.DEFAULT_MODEL
) -> List[Dict[str, Any]]:
    """
    Fonction de vérification de batch asynchrone pour le fact-checking

    Args:
        analyzer: Une instance de CritiqueAnalyzer déjà initialisée.
        affirmations: Liste d'affirmations à analyser
        model: Modèle à utiliser

    Returns:
        List[Dict[str, Any]]: Liste des résultats d'analyse
    """
    results = []
    for i, aff in enumerate(affirmations, 1):
        try:
            result = await analyzer.analyze(aff)
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

async def ask_ma(
    analyzer: "CritiqueAnalyzer",
    question: str,
    model: str = Config.DEFAULT_MODEL
) -> str:
    """
    Pose une question simple à l'IA

    Args:
        analyzer: Une instance de CritiqueAnalyzer déjà initialisée.
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
        # Utilise la méthode analyze avec un prompt spécifique pour les questions
        response = await analyzer.analyze(question)
        return response.get('analyse', '')
    except Exception as e:
        raise MistralAnalysisError(f"Erreur lors de la question: {str(e)}")
