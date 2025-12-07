#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module de l'Orchestrateur d'Analyse Critique.

Ce module contient la classe principale `AnalysisOrchestrator` qui gère
l'ensemble du processus d'analyse d'affirmations en utilisant un fournisseur d'IA.
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
from ..utils import (
    Config, AnalysisError, validate_text,
    format_affirmation
)
# Import du système de provider
from .providers import get_provider, AbstractAIProvider

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
# DÉCORATEURS
# =============================================
def retry(max_attempts: int = Config.MAX_RETRIES, delay: int = Config.RETRY_DELAY):
    """
    Décorateur pour implémenter une logique de réessai pour les fonctions asynchrones.
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
# CLASSE PRINCIPALE DE L'ORCHESTRATEUR
# =============================================
class AnalysisOrchestrator:
    """
    Classe principale pour l'orchestration de l'analyse critique.

    Cette classe encapsule toute la logique d'analyse, de la classification
    à l'analyse spécialisée, et fournit une interface simple.
    """

    def __init__(self, provider: AbstractAIProvider, semaphore: asyncio.Semaphore):
        """
        Initialise l'orchestrateur avec un fournisseur d'IA et un sémaphore.
        Utilisez la méthode de classe `create` pour l'instanciation.
        """
        self.provider = provider
        self.semaphore = semaphore

    @classmethod
    async def create(cls, provider_name: str = Config.DEFAULT_PROVIDER, api_key: Optional[str] = None) -> "AnalysisOrchestrator":
        """
        Méthode de fabrique asynchrone pour créer une instance de AnalysisOrchestrator.
        """
        provider = get_provider(provider_name)
        await provider.initialize(api_key)
        semaphore = asyncio.Semaphore(Config.MAX_CONCURRENT_REQUESTS)
        analyzer = cls(provider, semaphore)
        logger.info("AnalysisOrchestrator initialisé avec succès")
        return analyzer

    @retry()
    async def analyze(self, affirmation: Union[str, Dict], history: List[Dict[str, str]] = None, global_context: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyse une affirmation en utilisant la stratégie en deux phases :
        1. Classification pour déterminer la catégorie.
        2. Analyse spécialisée basée sur la catégorie.
        """
        if not validate_text(affirmation):
            raise AnalysisError("Affirmation invalide ou vide")

        formatted_aff = format_affirmation(affirmation)
        
        # Le contexte global est toujours prioritaire
        context_header = ""
        if global_context:
            context_header = f"CONTEXTE GLOBAL DE LA DISCUSSION :\n{global_context}\n\n---\n\n"

        # L'historique est maintenant une liste de messages structurés
        history_messages = history or []

        async with self.semaphore:
            try:
                # --- PHASE 1: CLASSIFICATION ---
                logger.info(f"Phase 1: Classification de '{formatted_aff[:30]}...'")
                
                # Le message utilisateur pour la classification inclut le contexte global
                classification_user_content = f"{context_header}AFFIRMATION À CLASSER : \"{formatted_aff}\""
                
                classification_messages = [
                    {"role": "system", "content": get_system_prompt_classify()}
                ]
                # L'historique n'est peut-être pas pertinent pour la classification, donc on le laisse en dehors pour l'instant
                # pour ne pas influencer la catégorisation. On se concentre sur l'affirmation elle-même.
                classification_messages.append({"role": "user", "content": classification_user_content})

                logger.info(f"-> Appel API (Classification) pour '{formatted_aff[:20]}...' ")
                category_raw = await asyncio.wait_for(
                    self.provider.complete_chat_async(
                        messages=classification_messages,
                        model=Config.DEFAULT_MODEL,
                        temperature=0.0
                    ),
                    timeout=Config.TIMEOUT
                )
                
                match = re.search(r'(\w+)', category_raw)
                category = match.group(1) if match else category_raw.strip()
                logger.info(f"Phase 1: Catégorie déterminée -> {category}")

                # --- PHASE 2: ANALYSE SPÉCIALISÉE ---
                logger.info(f"Phase 2: Lancement de l'analyse spécialisée pour la catégorie '{category}'")
                system_prompt = get_specialized_system_prompt(category)
                
                # Le prompt utilisateur pour l'analyse inclut le contexte global
                user_prompt = f"{context_header}Affirmation à analyser: \"{formatted_aff}\""

                # Construction des messages pour l'analyse, en incluant l'historique
                messages = [{"role": "system", "content": system_prompt}]
                messages.extend(history_messages)
                messages.append({"role": "user", "content": user_prompt})

                logger.info(f"-> Appel API (Analyse) pour '{formatted_aff[:20]}...' ")
                analysis_response = await asyncio.wait_for(
                    self.provider.complete_chat_async(
                        model=Config.DEFAULT_MODEL,
                        messages=messages,
                    ),
                    timeout=Config.TIMEOUT
                )

                return {
                    "affirmation": formatted_aff,
                    "analyse": analysis_response,
                    "category": category,
                    "model": Config.DEFAULT_MODEL,
                    "status": "success"
                }

            except Exception as e:
                raise AnalysisError(f"Erreur d'analyse: {str(e)}")

    async def batch_analyze(self, affirmations: List[Union[str, Dict]], mode: str = "GENERAL") -> List[Dict[str, Any]]:
        """
        Analyse un lot d'affirmations.
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

async def ask_ma(
    analyzer: "AnalysisOrchestrator",
    question: str,
    model: str = Config.DEFAULT_MODEL
) -> str:
    """
    Pose une question simple à l'IA.
    """
    if not isinstance(question, str) or not question.strip():
        raise AnalysisError("Question invalide ou vide")

    try:
        response = await analyzer.analyze(question)
        return response.get('analyse', '')
    except Exception as e:
        raise AnalysisError(f"Erreur lors de la question: {str(e)}")
