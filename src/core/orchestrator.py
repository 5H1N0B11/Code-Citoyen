#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module de l'Orchestrateur d'Analyse Critique.

Ce module contient la classe principale `AnalysisOrchestrator` qui gère
l'ensemble du processus d'analyse d'affirmations en utilisant une architecture
hybride Groq + Mistral :

  - Phase 0 (Extraction de sujet)  → Groq  (llama3-8b-8192) — rapide, anti-429
  - Phase 1 (Classification)       → Mistral (mistral-small-latest) — qualité
  - Phase 1.5 (Recherche Google)   → fact_checker.py (inchangé)
  - Phase 2 (Analyse spécialisée)  → Mistral (mistral-small-latest) — qualité/prix optimisé
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
import ast
from functools import wraps

# Imports depuis notre nouveau module utilitaire
from ..utils import (
    Config, AnalysisError, validate_text, TourDeControle,
    format_affirmation, ApiHealthManager, parse_llm_json
)
# Import du système de provider
from .providers import get_provider, AbstractAIProvider

# Import des prompts pour la logique en deux phases
from ..prompts.templates import (
    get_classification_prompt, get_classification_prompt_light, 
    get_specialized_system_prompt, get_system_prompt_topic_extraction, 
    get_search_keyword_prompt,
    WINDOW_SELECTION_SYSTEM_PROMPT,
    TOPIC_UPDATE_SYSTEM_PROMPT
)

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
      - self.classification_provider (Groq/Mistral)
      - self.analysis_provider      (Mistral)
    """

    def __init__(
        self,
        providers: Dict[str, AbstractAIProvider],
    ):
        """
        Initialise l'orchestrateur avec le dictionnaire de fournisseurs.
        """
        self.providers = providers
        self.health_manager = ApiHealthManager()

    @classmethod
    async def create(
        cls,
        provider_name: str = None, # Conservé pour compatibilité mais piloté par Config
        api_key: Optional[str] = None
    ) -> "AnalysisOrchestrator":
        """
        Méthode de fabrique asynchrone pour créer une instance de AnalysisOrchestrator.
        Initialise toute la flotte de modèles disponibles.
        """
        providers = {}
        
        try:
            groq_p = get_provider("groq")
            await groq_p.initialize()
            providers["groq"] = groq_p
            logger.info("GroqProvider initialisé.")
        except Exception as e:
            logger.warning(f"Erreur init Groq: {e}")

        try:
            mistral_p = get_provider("mistral")
            await mistral_p.initialize(api_key)
            providers["mistral"] = mistral_p 
            logger.info("MistralProvider initialisé (via TourDeControle).")
        except Exception as e:
            logger.warning(f"Erreur init Mistral: {e}")

        analyzer = cls(providers)
        logger.info("AnalysisOrchestrator hybride prêt au service.")
        return analyzer

    async def call_llm(self, task_name: str, messages: List[Dict[str, str]], temperature: float = 0.0, max_tokens: Optional[int] = None) -> str:
        """Méthode centralisée qui exécute l'IA pour une tâche, avec gestion de fallback."""
        route = TourDeControle.get(task_name)
        primary_provider = route["provider"]
        primary_model = route["model"]

        # --- Attempt 1: Primary Provider ---
        try:
            # Check cooldown status before making a call
            self.health_manager.check_and_update_fallback(primary_provider)
            if self.health_manager.get_provider_health(primary_provider)["fallback_active"]:
                raise AnalysisError(f"Provider '{primary_provider}' is in cooldown, forcing fallback.")

            return await self.providers[primary_provider].complete_chat_async(
                messages=messages,
                model=primary_model,
                temperature=temperature,
                max_tokens=max_tokens
            )
        except Exception as e:
            logger.warning(f"Primary provider '{primary_provider}' failed for task '{task_name}': {e}. Messages: {messages}")
            self.health_manager.record_error(primary_provider)

            # --- Determine Fallback ---
            if primary_provider == "groq":
                fallback_provider = "mistral"
                fallback_route = TourDeControle.get('fact_checking') # Use the route of a known mistral task
                fallback_model = fallback_route['model']
            elif primary_provider == "mistral":
                fallback_provider = "groq"
                fallback_route = TourDeControle.get('selection_phrase') # Use the route of a known groq task
                fallback_model = fallback_route['model']
            else:
                fallback_provider = None

            if not fallback_provider or fallback_provider not in self.providers:
                logger.error(f"No fallback configured for provider '{primary_provider}'. Raising original error.")
                raise AnalysisError(f"Primary provider '{primary_provider}' failed or is misconfigured, and no fallback is available.") from e

        # --- Attempt 2: Fallback Provider ---
        logger.info(f"Attempting to use fallback provider '{fallback_provider}' for task '{task_name}'.")
        try:
            self.health_manager.check_and_update_fallback(fallback_provider)
            if self.health_manager.get_provider_health(fallback_provider)["fallback_active"]:
                raise AnalysisError(f"Fallback provider '{fallback_provider}' is also in cooldown.")
            
            return await self.providers[fallback_provider].complete_chat_async(
                messages=messages,
                model=fallback_model,
                temperature=temperature,
                max_tokens=max_tokens
            )
        except Exception as fallback_e:
            logger.error(f"Fallback provider '{fallback_provider}' also failed: {fallback_e}. Messages: {messages}")
            self.health_manager.record_error(fallback_provider)
            raise AnalysisError(f"Both primary '{primary_provider}' and fallback '{fallback_provider}' providers failed.") from fallback_e

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
            topic_raw = await asyncio.wait_for(
                self.call_llm(
                    task_name="extraction_sujet",
                    messages=topic_messages,
                    temperature=0.0
                ),
                timeout=Config.TIMEOUT
            )

            parsed_topic = parse_llm_json(topic_raw)

            if isinstance(parsed_topic, dict):
                return {
                    "sujet_principal": parsed_topic.get("sujet_principal"),
                    "sous_sujet": parsed_topic.get("sous_sujet")
                }
            else:
                logger.warning(f"Erreur de format JSON lors de l'extraction du sujet. Réponse brute: {topic_raw[:200]}")
                return {"sujet_principal": None, "sous_sujet": None}
        except Exception as e:
            logger.exception(f"Erreur lors de l'extraction du sujet (Groq): {e}")
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

    async def _extract_search_keywords(self, affirmation: str, main_topic: Optional[str], sub_topic: Optional[str]) -> str:
        """
        Utilise un LLM pour extraire les mots-clés de recherche optimaux d'une affirmation.
        """
        prompt = get_search_keyword_prompt(affirmation, main_topic, sub_topic)
        messages = [{"role": "user", "content": prompt}]

        try:
            keywords = await self.call_llm(
                task_name="extraction_mots_cles",
                messages=messages,
                temperature=0.0,
                max_tokens=50 # Les mots-clés sont courts
            )
            # Nettoyage final pour enlever les guillemets et les préfixes indésirables de l'IA
            cleaned = keywords.strip().replace('"', '')
            cleaned = re.sub(r'(?i)^(sortie attendue|mots[- ]?clés?|requête)\s*:\s*', '', cleaned)
            return cleaned
        except Exception as e:
            logger.warning(f"Échec de l'extraction des mots-clés, fallback sur l'affirmation brute. Erreur: {e}")
            # Fallback: si l'extraction échoue, on utilise l'affirmation originale nettoyée.
            return re.sub(r'[^\w\s]', ' ', affirmation).strip()


    # ------------------------------------------------------------------
    # MÉTHODE PUBLIQUE : Sélection d'affirmation (Phase 1 du Stream)
    # ------------------------------------------------------------------
    async def select_affirmation(self, buffer: List[Dict[str, Any]], history: List[Dict[str, str]]) -> Optional[List[Dict[str, Any]]]:
        """
        Sélectionne l'affirmation la plus pertinente dans un buffer de phrases.
        Utilise le modèle rapide (Groq) pour la vitesse.
        """
        if not buffer:
            return None

        # Format the buffer and history for the prompt
        buffer_text = "\n".join([f"- (start={s.get('video_timestamp', s.get('start', 0.0)):.2f}s) {s.get('affirmation', s.get('text', ''))}" for s in buffer])
        history_text = "\n".join([f" - [{msg['role']}] {msg['content']}" for msg in history])

        user_content = (
            f"HISTORIQUE COMPLET:\n{history_text}\n\n"
            f"BUFFER ACTUEL (phrases des dernières secondes):\n{buffer_text}\n\n"
            "Votre tâche est de sélectionner les affirmations pertinentes (maximum 3) à vérifier dans le BUFFER ACTUEL."
        )

        messages = [
            {"role": "system", "content": WINDOW_SELECTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_content}
        ]

        try:
            selection_raw = await self.call_llm(
                task_name="selection_phrase",
                messages=messages,
                temperature=0.0,
                max_tokens=1000 
            )
            
            parsed_selection = parse_llm_json(selection_raw)

            if isinstance(parsed_selection, list):
                valid_selections = [
                    item for item in parsed_selection
                    if isinstance(item, dict) and item.get("affirmation_corrigee")
                ]
                if valid_selections:
                    logger.info(f"[Sélection] {len(valid_selections)} affirmation(s) sélectionnée(s).")
                    return valid_selections
                else:
                    logger.info("[Sélection] Aucune affirmation pertinente sélectionnée par l'IA.")
                    return None
            else:
                logger.warning(f"[Sélection] L'IA n'a pas retourné une liste. Réponse brute: {selection_raw[:200]}")
                return None
        except Exception as e:
            logger.error(f"Erreur lors de la sélection de l'affirmation : {e}", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # MÉTHODE PUBLIQUE : Mise à jour du contexte (Radar)
    # ------------------------------------------------------------------
    async def update_topic_context(self, user_content: str) -> Optional[Dict[str, Any]]:
        """
        Met à jour le sujet et le résumé de la discussion.
        """
        messages = [
            {"role": "system", "content": TOPIC_UPDATE_SYSTEM_PROMPT},
            {"role": "user", "content": user_content}
        ]

        try:
            response_raw = await self.call_llm(
                task_name="radar_contexte", messages=messages, temperature=0.1, max_tokens=500
            )
            parsed_response = parse_llm_json(response_raw)
            if isinstance(parsed_response, dict):
                return parsed_response
            return None
        except Exception as e:
            logger.error(f"[Radar] Erreur dans update_topic_context: {e}", exc_info=True)
            return None

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
          Phase 1  — Classification               → Mistral
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
            prov_name = TourDeControle.get('extraction_sujet')['provider'].capitalize()
            logger.info(f"[Phase 0 — {prov_name}] Sujet principal: {main_topic}")
        else:
            logger.debug(f"[Phase 0] Ignorée — main_topic/sub_topic déjà fournis : {main_topic!r} / {sub_topic!r}")

        # Contexte ULTRA-LÉGER pour la Classification (évite les 429 TPM)
        classif_context_parts = []
        if main_topic:
            classif_context_parts.append(f"SUJET PRINCIPAL :\n{main_topic}")
        if sub_topic:
            classif_context_parts.append(f"SOUS-SUJET :\n{sub_topic}")
        
        classif_context_header = "\n\n---\n\n".join(classif_context_parts) + "\n\n--=\n\n" if classif_context_parts else ""

        # Contexte LOURD pour Mistral (Fact-Checking)
        analysis_context_parts = []
        if global_context:
            analysis_context_parts.append(f"CONTEXTE GÉNÉRAL DE LA DISCUSSION :\n{global_context}")
        if main_topic:
            analysis_context_parts.append(f"SUJET PRINCIPAL DE LA DISCUSSION :\n{main_topic}")
        if sub_topic:
            analysis_context_parts.append(f"SOUS-SUJET ACTUEL DE LA DISCUSSION :\n{sub_topic}")
        if previous_context:
            analysis_context_parts.append(f"DERNIÈRE PHRASE PRONONCÉE AVANT L'AFFIRMATION (CONTEXTE IMMÉDIAT) :\n{previous_context}")
        if future_context:
            analysis_context_parts.append(f"TROIS PROCHAINES PHRASES PRONONCÉES APRÈS L'AFFIRMATION (CONTEXTE DE DÉSAMBIGUÏSATION) :\n{future_context}")

        analysis_context_header = "\n\n---\n\n".join(analysis_context_parts) + "\n\n--=\n\n" if analysis_context_parts else ""

        # L'historique est maintenant une liste de messages structurés
        history_messages = history or []

        try:
            # --- PHASE 1: CLASSIFICATION ---
            classification_route = TourDeControle.get('classification')
            classif_prov_name = classification_route['provider']
            
            logger.info(f"STARTING ANALYSIS for: '{formatted_aff[:30]}...'")
            logger.info(f"[Phase 1 — {classif_prov_name.capitalize()}] Classification de '{formatted_aff[:30]}...'")

            classification_user_content = (
                f"{classif_context_header}"
                f"L'objectif est de classer la phrase suivante.\n"
                f"UTILISEZ LE CONTEXTE UNIQUEMENT POUR COMPRENDRE ET DÉSAMBIGUÏSER L'AFFIRMATION, "
                f"PAS POUR LA VALIDER.\n\n"
                f"AFFIRMATION À CLASSER : \"{formatted_aff}\""
            )
            
            # Utilise le prompt "light" si groq, sinon complet pour mistral
            if classif_prov_name == 'groq':
                classif_system_prompt = get_classification_prompt_light()
            else:
                classif_system_prompt = get_classification_prompt(main_topic=main_topic, sub_topic=sub_topic)
                
            classification_messages = [
                {"role": "system", "content": classif_system_prompt},
                {"role": "user", "content": classification_user_content}
            ]

            category_raw = await asyncio.wait_for(
                self.call_llm(
                    task_name="classification",
                    messages=classification_messages,
                    temperature=0.0
                ),
                timeout=Config.TIMEOUT
            )

            match = re.search(r'(\w+)', category_raw)
            category = match.group(1) if match else category_raw.strip()

            final_classif_provider = self.health_manager.get_provider_health(classif_prov_name)["fallback_active"] and "groq" or classif_prov_name
            logger.info(f"[Phase 1 — {final_classif_provider.capitalize()}] Catégorie -> {category}")

            # --- PHASE 1.5: RECHERCHE GOOGLE (catégories factuelles ciblées) ---
            web_sources_block = ""
            if category in CATEGORIES_AVEC_RECHERCHE:
                # NOUVELLE ÉTAPE : Extraire les mots-clés pour une recherche plus efficace
                search_query = await self._extract_search_keywords(formatted_aff, main_topic, sub_topic)
                logger.info(f"[Phase 1.5] Recherche Google pour la catégorie '{category}' avec la requête : '{search_query}'")
                try:
                    # On passe l'affirmation originale pour le cache, et la requête optimisée pour la recherche
                    urls_found = await asyncio.wait_for(fetch_fact_check_urls(formatted_aff, search_query, category=category), timeout=15)
                    if urls_found:
                        # --- FILTRE ANTI-RÉSEAUX SOCIAUX ---
                        filtered_urls = [u for u in urls_found if not any(b in u['url'].lower() for b in Config.BANNED_DOMAINS)]
                        
                        logger.info(f"[Metrics FactCheck] Sources brutes récupérées : {urls_found}")
                        if len(filtered_urls) < len(urls_found):
                            logger.warning(f"[Metrics FactCheck] Rejet de {len(urls_found) - len(filtered_urls)} source(s) non fiable(s) (Réseaux Sociaux).")
                            
                        if filtered_urls:
                            web_sources_block = format_urls_for_prompt(filtered_urls)
                            logger.info(f"[Phase 1.5] {len(filtered_urls)} source(s) web validée(s) et injectée(s).")
                        else:
                            logger.info("[Phase 1.5] Toutes les sources ont été filtrées (non fiables).")
                    else:
                        logger.info("[Phase 1.5] Aucune source web trouvée.")
                except Exception as e:
                    logger.warning(f"[Phase 1.5] Erreur lors de la recherche Google (non bloquant) : {e}")

            # --- PHASE 2: ANALYSE SPÉCIALISÉE via Mistral ---
            fc_prov = TourDeControle.get('fact_checking')['provider'].capitalize()
            logger.info(f"[Phase 2 — {fc_prov}] Analyse spécialisée pour '{category}'")
            system_prompt = get_specialized_system_prompt(category, main_topic=main_topic, sub_topic=sub_topic)

            web_sources_section = f"\n\n---\n\n{web_sources_block}\n\n---\n\n" if web_sources_block else ""

            user_prompt = (
                f"{analysis_context_header}"
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

            analysis_response_raw = await asyncio.wait_for(
                self.call_llm(
                    task_name="fact_checking",
                    messages=messages,
                    temperature=0.0,
                    max_tokens=Config.MAX_TOKENS # On s'assure que Mistral a de la place
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
                "model": TourDeControle.get('fact_checking')['model'],
                "status": "success",
                "main_topic": main_topic,
                "sub_topic": sub_topic,
                "web_sources": web_sources_block if web_sources_block else None,
            }

        except Exception as e:
            raise AnalysisError(f"Erreur d'analyse: {str(e)}")

    def _parse_llm_json(self, response_text: str) -> Dict[str, Any]:
        """
        Tente de parser une réponse JSON de l'LLM.
        En cas d'échec, retourne un dictionnaire d'erreur structuré au lieu de planter.
        """
        parsed_json = parse_llm_json(response_text) 
        if parsed_json and isinstance(parsed_json, dict):
            return parsed_json 

        logger.warning(f"Échec total du parsing JSON. Retour d'un objet d'erreur. Réponse brute: {response_text[:200]}")
        return {
            "verdict": "ERREUR_PARSING",
            "score": "N/A",
            "explanation_short": "La réponse de l'IA était mal formatée.",
            "explanation_long": (
                "L'analyse n'a pas pu être extraite car la réponse de l'IA n'était pas un JSON valide. "
                f"Cela peut être dû à une erreur de l'API ou à une réponse tronquée.\n\n"
                f"Réponse brute reçue :\n---\n{response_text}"
            ),
            "biais_detecte": None
        }

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
                error_msg = f"Erreur d'analyse: {e}"
                aff_text = format_affirmation(aff)
                results.append({
                    "id": i,
                    "affirmation": aff_text,
                    "analyse": error_msg,
                    "status": "error",
                    "error": error_msg
                })
                logger.exception(f"Échec de l'analyse pour l'affirmation #{i}: {aff_text}")
        return results


async def ask_ma(
    analyzer: "AnalysisOrchestrator",
    question: str,
    model: str = None
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
        raise AnalysisError(f"Erreur lors de la question: {e}")
