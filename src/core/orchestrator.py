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
import json
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
    async def analyze(self, affirmation: Union[str, Dict], history: List[Dict[str, str]] = None, global_context: Optional[str] = None, future_context: Optional[str] = None, previous_context: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyse une affirmation en utilisant la stratégie en deux phases :
        1. Classification pour déterminer la catégorie.
        2. Analyse spécialisée basée sur la catégorie.
        """
        if not validate_text(affirmation):
            raise AnalysisError("Affirmation invalide ou vide")

        formatted_aff = format_affirmation(affirmation)
        
        # Construction du header de contexte
        context_parts = []
        if global_context:
            context_parts.append(f"CONTEXTE GLOBAL DE LA DISCUSSION :\n{global_context}")
        
        if previous_context:
            context_parts.append(f"CONTEXTE PRÉCÉDENT (Phrase d'avant) :\n{previous_context}")

        if future_context:
            context_parts.append(f"CONTEXTE FUTUR IMMÉDIAT (Pour désambiguïsation) :\n{future_context}")
            
        context_header = "\n\n---\n\n".join(context_parts) + "\n\n---\n\n" if context_parts else ""

        # L'historique est maintenant une liste de messages structurés
        history_messages = history or []

        async with self.semaphore:
            try:
                # --- PHASE 1: CLASSIFICATION ---
                logger.info(f"STARTING ANALYSIS for: '{formatted_aff[:30]}...'")
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
                
                # Filtrage de l'historique pour éviter les erreurs API (content empty/None)
                if history_messages:
                    valid_history = [
                        msg for msg in history_messages 
                        if msg.get("content") and str(msg.get("content")).strip()
                    ]
                    messages.extend(valid_history)

                messages.append({"role": "user", "content": user_prompt})

                logger.info(f"-> Appel API (Analyse) pour '{formatted_aff[:20]}...' ")
                analysis_response_raw = await asyncio.wait_for(
                    self.provider.complete_chat_async(
                        model=Config.DEFAULT_MODEL,
                        messages=messages,
                    ),
                    timeout=Config.TIMEOUT
                )
                
                # Parsing du JSON retourné par l'LLM
                parsed_analysis = self._parse_llm_json(analysis_response_raw)

                return {
                    "affirmation": formatted_aff,
                    "analyse": parsed_analysis, # Maintenant un dict ou une string nettoyée
                    "raw_response": analysis_response_raw, # On garde la réponse brute au cas où
                    "category": category,
                    "model": Config.DEFAULT_MODEL,
                    "status": "success"
                }

            except Exception as e:
                raise AnalysisError(f"Erreur d'analyse: {str(e)}")

    def _parse_llm_json(self, response_text: str) -> Union[Dict[str, Any], str]:
        """
        Tente de parser une réponse JSON de l'LLM, en nettoyant les balises Markdown.
        Retourne un dictionnaire si succès, sinon la chaîne brute nettoyée.
        """
        cleaned_text = response_text.strip()
        
        # Enlever les blocs de code markdown ```json ... ``` ou ``` ... ```
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned_text, re.DOTALL)
        if match:
            cleaned_text = match.group(1).strip()
        
        # Fonction utilitaire pour tenter le load
        def try_load(text):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                # Tentative de réparation basique : échapper les newlines dans les valeurs
                try:
                    repaired = text.replace('\n', '\\n')
                    return json.loads(repaired)
                except json.JSONDecodeError:
                    return None

        # 1. Tentative sur le texte nettoyé
        res = try_load(cleaned_text)
        if res: return res

        # 2. Tentative d'extraction précise du JSON via { ... }
        start_idx = cleaned_text.find('{')
        end_idx = cleaned_text.rfind('}')
        
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            candidate = cleaned_text[start_idx : end_idx + 1]
            res = try_load(candidate)
            if res: return res

        # 3. Fallback Regex : Si le JSON est cassé, on essaie d'extraire les champs clés
        logger.warning(f"Échec du parsing JSON strict. Tentative d'extraction par Regex.")
        
        try:
            # Regex qui cherche "key": "value" en gérant les quotes échappées basiques
            # On cherche les 4 champs principaux
            verdict_m = re.search(r'"verdict":\s*"([^"]+)"', cleaned_text)
            score_m = re.search(r'"score":\s*"([^"]+)"', cleaned_text)
            # Pour les explications, on essaie d'être permissif sur le contenu (non-greedy jusqu'à la prochaine quote fermante qui semble marquer la fin)
            # C'est fragile mais mieux que rien. On assume que la value ne finit pas par un backslash.
            short_m = re.search(r'"explanation_short":\s*"(.*?)(?<!\\)"', cleaned_text, re.DOTALL)
            long_m = re.search(r'"explanation_long":\s*"(.*?)(?<!\\)"', cleaned_text, re.DOTALL)

            if verdict_m:
                return {
                    "verdict": verdict_m.group(1),
                    "score": score_m.group(1) if score_m else "N/A",
                    "explanation_short": short_m.group(1) if short_m else "Analyse partiellement illisible (erreur de format).",
                    "explanation_long": long_m.group(1) if long_m else cleaned_text
                }
        except Exception:
            pass

        logger.error(f"Échec total du parsing JSON. Retour du texte nettoyé.")
        return cleaned_text

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
