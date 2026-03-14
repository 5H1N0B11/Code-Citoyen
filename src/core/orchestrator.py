#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module de l'Orchestrateur d'Analyse Critique.

Ce module contient la classe principale `AnalysisOrchestrator` qui gère
l'ensemble du processus d'analyse d'affirmations en utilisant une architecture
hybride Groq + Mistral :

  - Phase 0 (Extraction de sujet)  → Groq  (llama3-8b-8192) — rapide, anti-429
  - Phase 1 (Classification)       → Groq  (llama3-8b-8192) — rapide, anti-429
  - Phase 1.5 (Recherche Google)   → fact_checker.py (inchangé)
  - Phase 2 (Analyse spécialisée)  → Mistral (mistral-small-latest) — qualité maximale
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
from .providers.groq_provider import GroqProvider, GROQ_DEFAULT_MODEL
from .providers.mistral_provider import MistralProvider

# Import des prompts pour la logique en deux phases
from ..prompts.templates import get_classification_prompt, get_specialized_system_prompt, get_system_prompt_topic_extraction

# Import du module de fact-checking par recherche Google (NE PAS MODIFIER)
from ..tools.web_search import fetch_fact_check_urls, format_urls_for_prompt, CATEGORIES_AVEC_RECHERCHE

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

    Architecture hybride :
      - self.classification_provider (Groq)  → Phase 0 + Phase 1
      - self.analysis_provider      (Mistral) → Phase 2

    Cette séparation permet d'éviter les erreurs 429 de Mistral en déchargeant
    les appels légers (classification, extraction de sujet) sur Groq.
    """

    def __init__(
        self,
        classification_provider: AbstractAIProvider,
        analysis_provider: AbstractAIProvider,
        semaphore: asyncio.Semaphore
    ):
        """
        Initialise l'orchestrateur avec deux providers distincts et un sémaphore.
        Utilisez la méthode de classe `create` pour l'instanciation.
        """
        self.classification_provider = classification_provider  # Groq — Phase 0 & 1
        self.analysis_provider = analysis_provider              # Mistral — Phase 2
        self.semaphore = semaphore

    @classmethod
    async def create(
        cls,
        provider_name: str = Config.DEFAULT_PROVIDER,
        api_key: Optional[str] = None
    ) -> "AnalysisOrchestrator":
        """
        Méthode de fabrique asynchrone pour créer une instance de AnalysisOrchestrator.

        Initialise systématiquement :
          - GroqProvider   pour la classification (Phase 0 + 1)
          - MistralProvider pour l'analyse finale  (Phase 2)

        Le paramètre `provider_name` est conservé pour compatibilité ascendante
        mais n'influe plus sur le choix des providers internes.
        """
        # --- Provider de classification : Groq ---
        groq_provider = GroqProvider()
        await groq_provider.initialize()  # lit GROQ_API_KEY depuis l'environnement
        logger.info("GroqProvider initialisé (Phase 0 + Phase 1 — Classification).")

        # --- Provider d'analyse : Mistral ---
        mistral_provider = MistralProvider()
        await mistral_provider.initialize(api_key)  # lit MISTRAL_API_KEY depuis l'environnement
        logger.info("MistralProvider initialisé (Phase 2 — Analyse spécialisée).")

        semaphore = asyncio.Semaphore(Config.MAX_CONCURRENT_REQUESTS)
        analyzer = cls(groq_provider, mistral_provider, semaphore)
        logger.info("AnalysisOrchestrator hybride (Groq + Mistral) initialisé avec succès.")
        return analyzer

    # ------------------------------------------------------------------
    # PHASE 0 — Extraction du sujet (via Groq)
    # ------------------------------------------------------------------
    async def _extract_topic(self, text_to_analyze: str) -> Dict[str, Optional[str]]:
        """
        Extrait le sujet principal et le sous-sujet d'un texte donné.
        Utilise Groq (llama3-8b-8192) pour la rapidité.
        """
        topic_messages = [
            {"role": "system", "content": get_system_prompt_topic_extraction()},
            {"role": "user", "content": f"TEXTE À ANALYSER:\n{text_to_analyze}"}
        ]

        try:
            logger.info(f"-> [Groq] Appel API (Extraction de sujet) pour '{text_to_analyze[:50]}...' ")
            topic_raw = await asyncio.wait_for(
                self.classification_provider.complete_chat_async(
                    messages=topic_messages,
                    model=GROQ_DEFAULT_MODEL,
                    temperature=0.0
                ),
                timeout=Config.TIMEOUT
            )

            parsed_topic = self._parse_llm_json(topic_raw)

            if isinstance(parsed_topic, dict):
                return {
                    "sujet_principal": parsed_topic.get("sujet_principal"),
                    "sous_sujet": parsed_topic.get("sous_sujet")
                }
            else:
                logger.error(f"Erreur de format JSON lors de l'extraction du sujet. Réponse brute: {topic_raw[:200]}")
                return {"sujet_principal": None, "sous_sujet": None}
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction du sujet (Groq): {str(e)}")
            return {"sujet_principal": None, "sous_sujet": None}

    # ------------------------------------------------------------------
    # MÉTHODE PUBLIQUE : Extraction du sujet (Phase 0) — appelable séparément
    # ------------------------------------------------------------------
    async def extract_topic(self, global_context: str) -> Dict[str, Optional[str]]:
        """
        Extrait le sujet principal et le sous-sujet depuis le contexte global.
        Retourne un dict avec les clés 'main_topic' et 'sub_topic'.
        Destiné à être appelé UNE SEULE FOIS avant la boucle d'analyse.
        """
        topics = await self._extract_topic(global_context)
        return {
            "main_topic": topics.get("sujet_principal"),
            "sub_topic": topics.get("sous_sujet")
        }

    # ------------------------------------------------------------------
    # MÉTHODE PRINCIPALE D'ANALYSE
    # ------------------------------------------------------------------
    @retry()
    async def analyze(
        self,
        affirmation: Union[str, Dict],
        history: List[Dict[str, str]] = None,
        global_context: Optional[str] = None,
        future_context: Optional[str] = None,
        previous_context: Optional[str] = None,
        main_topic: Optional[str] = None,
        sub_topic: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyse une affirmation via l'architecture hybride Groq + Mistral :

          Phase 0  — Extraction sujet/sous-sujet  → Groq (optionnel si déjà fourni)
          Phase 1  — Classification               → Groq
          Phase 1.5 — Recherche Google            → fact_checker (inchangé)
          Phase 2  — Analyse spécialisée          → Mistral

        Si main_topic et sub_topic sont fournis (pré-calculés avant la boucle),
        la Phase 0 est ignorée pour éviter les appels API redondants.
        """
        if not validate_text(affirmation):
            raise AnalysisError("Affirmation invalide ou vide")

        formatted_aff = format_affirmation(affirmation)

        # --- PHASE 0: EXTRACTION DU SUJET ET SOUS-SUJET via Groq ---
        # Ignorée si main_topic/sub_topic sont déjà fournis (optimisation anti-429)
        if main_topic is None and sub_topic is None and global_context:
            topics = await self._extract_topic(global_context)
            main_topic = topics.get("sujet_principal")
            sub_topic = topics.get("sous_sujet")
            logger.info(f"[Phase 0 — Groq] Sujet principal: {main_topic}, Sous-sujet: {sub_topic}")
        else:
            logger.debug(f"[Phase 0] Ignorée — main_topic/sub_topic déjà fournis : {main_topic!r} / {sub_topic!r}")

        # Construction du header de contexte
        context_parts = []
        if global_context:
            context_parts.append(f"CONTEXTE GÉNÉRAL DE LA DISCUSSION :\n{global_context}")

        if main_topic:
            context_parts.append(f"SUJET PRINCIPAL DE LA DISCUSSION :\n{main_topic}")
        if sub_topic:
            context_parts.append(f"SOUS-SUJET ACTUEL DE LA DISCUSSION :\n{sub_topic}")

        if previous_context:
            context_parts.append(f"DERNIÈRE PHRASE PRONONCÉE AVANT L'AFFIRMATION (CONTEXTE IMMÉDIAT) :\n{previous_context}")

        if future_context:
            context_parts.append(f"TROIS PROCHAINES PHRASES PRONONCÉES APRÈS L'AFFIRMATION (CONTEXTE DE DÉSAMBIGUÏSATION) :\n{future_context}")

        context_header = "\n\n---\n\n".join(context_parts) + "\n\n--=\n\n" if context_parts else ""

        # L'historique est maintenant une liste de messages structurés
        history_messages = history or []

        async with self.semaphore:
            try:
                # --- PHASE 1: CLASSIFICATION via Groq ---
                logger.info(f"STARTING ANALYSIS for: '{formatted_aff[:30]}...'")
                logger.info(f"[Phase 1 — Groq] Classification de '{formatted_aff[:30]}...'")

                classification_user_content = (
                    f"{context_header}"
                    f"L'objectif est de classer la phrase suivante.\n"
                    f"UTILISEZ LE CONTEXTE UNIQUEMENT POUR COMPRENDRE ET DÉSAMBIGUÏSER L'AFFIRMATION, "
                    f"PAS POUR LA VALIDER.\n\n"
                    f"AFFIRMATION À CLASSER : \"{formatted_aff}\""
                )

                classification_messages = [
                    {"role": "system", "content": get_classification_prompt(main_topic=main_topic, sub_topic=sub_topic)},
                    {"role": "user", "content": classification_user_content}
                ]

                logger.info(f"-> [Groq] Appel API (Classification) pour '{formatted_aff[:20]}...' ")
                category_raw = await asyncio.wait_for(
                    self.classification_provider.complete_chat_async(
                        messages=classification_messages,
                        model=GROQ_DEFAULT_MODEL,
                        temperature=0.0
                    ),
                    timeout=Config.TIMEOUT
                )

                match = re.search(r'(\w+)', category_raw)
                category = match.group(1) if match else category_raw.strip()
                logger.info(f"[Phase 1 — Groq] Catégorie déterminée -> {category}")

                # --- PHASE 1.5: RECHERCHE GOOGLE (catégories factuelles ciblées) ---
                web_sources_block = ""
                if category in CATEGORIES_AVEC_RECHERCHE:
                    logger.info(f"[Phase 1.5] Recherche Google pour la catégorie '{category}'")
                    try:
                        urls_found = await asyncio.wait_for(fetch_fact_check_urls(formatted_aff), timeout=10)
                        if urls_found:
                            web_sources_block = format_urls_for_prompt(urls_found)
                            logger.info(f"[Phase 1.5] {len(urls_found)} source(s) web injectée(s) dans le prompt.")
                        else:
                            logger.info("[Phase 1.5] Aucune source web trouvée.")
                    except Exception as e:
                        logger.warning(f"[Phase 1.5] Erreur lors de la recherche Google (non bloquant) : {e}")

                # --- PHASE 2: ANALYSE SPÉCIALISÉE via Mistral ---
                logger.info(f"[Phase 2 — Mistral] Lancement de l'analyse spécialisée pour la catégorie '{category}'")
                system_prompt = get_specialized_system_prompt(category, main_topic=main_topic, sub_topic=sub_topic)

                web_sources_section = f"\n\n---\n\n{web_sources_block}\n\n---\n\n" if web_sources_block else ""

                user_prompt = (
                    f"{context_header}"
                    f"L'objectif est de fact-checker la phrase suivante.\n"
                    f"UTILISEZ LE CONTEXTE UNIQUEMENT POUR COMPRENDRE ET DÉSAMBIGUÏSER L'AFFIRMATION, PAS POUR LA VALIDER. "
                    f"Votre analyse doit se concentrer UNIQUEMENT sur l'AFFIRMATION À ANALYSER."
                    f"{web_sources_section}"
                    f"\nAFFIRMATION À ANALYSER: \"{formatted_aff}\""
                )

                # Construction des messages pour l'analyse, en incluant l'historique
                messages = [{"role": "system", "content": system_prompt}]

                # Filtrage de l'historique pour éviter les erreurs API (content empty/None)
                if history_messages:
                    valid_history = [
                        msg for msg in history_messages
                        if msg is not None and msg.get("content") and str(msg.get("content")).strip()
                    ]
                    messages.extend(valid_history)

                messages.append({"role": "user", "content": user_prompt})

                logger.info(f"-> [Mistral] Appel API (Analyse) pour '{formatted_aff[:20]}...' ")
                analysis_response_raw = await asyncio.wait_for(
                    self.analysis_provider.complete_chat_async(
                        model=Config.DEFAULT_MODEL,
                        messages=messages,
                    ),
                    timeout=Config.TIMEOUT
                )

                # Parsing du JSON retourné par l'LLM
                parsed_analysis = self._parse_llm_json(analysis_response_raw)

                return {
                    "affirmation": formatted_aff,
                    "analyse": parsed_analysis,
                    "raw_response": analysis_response_raw,
                    "category": category,
                    "model": Config.DEFAULT_MODEL,
                    "status": "success",
                    "main_topic": main_topic,
                    "sub_topic": sub_topic,
                    "web_sources": web_sources_block if web_sources_block else None,
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

        def try_load(text):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                try:
                    repaired = text.replace('\n', '\\n')
                    return json.loads(repaired)
                except json.JSONDecodeError:
                    return None

        # 1. Tentative sur le texte nettoyé
        res = try_load(cleaned_text)
        if res:
            return res

        # 2. Tentative d'extraction précise du JSON via { ... }
        start_idx = cleaned_text.find('{')
        end_idx = cleaned_text.rfind('}')

        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            candidate = cleaned_text[start_idx: end_idx + 1]
            res = try_load(candidate)
            if res:
                return res

        # 3. Fallback Regex : Si le JSON est cassé, on essaie d'extraire les champs clés
        logger.warning(f"Échec du parsing JSON strict. Tentative d'extraction par Regex.")

        try:
            verdict_m = re.search(r'"verdict":\s*"([^"]+)"', cleaned_text)
            score_m = re.search(r'"score":\s*"([^"]+)"', cleaned_text)
            short_m = re.search(r'"explanation_short":\s*"(.*?)(?<!\\)"', cleaned_text, re.DOTALL)
            long_m = re.search(r'"explanation_long":\s*"(.*?)(?<!\\)"', cleaned_text, re.DOTALL)
            biais_m = re.search(r'"biais_detecte":\s*("([^"]+)"|null)', cleaned_text)

            if verdict_m:
                detected_biais = None
                if biais_m:
                    if biais_m.group(1) == 'null':
                        detected_biais = None
                    else:
                        detected_biais = biais_m.group(2)

                return {
                    "verdict": verdict_m.group(1),
                    "score": score_m.group(1) if score_m else "N/A",
                    "explanation_short": short_m.group(1) if short_m else "Analyse partiellement illisible (erreur de format).",
                    "explanation_long": long_m.group(1) if long_m else cleaned_text,
                    "biais_detecte": detected_biais
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
