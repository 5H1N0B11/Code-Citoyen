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
    get_sophisme_naming_prompt,
    get_verdict_calibration_prompt,
    get_verdict_head_prompt,
    has_statistical_signal,
    WINDOW_SELECTION_SYSTEM_PROMPT,
    TOPIC_UPDATE_SYSTEM_PROMPT,
    VALID_CATEGORIES,
    BIAS_KEYS_LIST,
    SOPHISMES_DEBAT,
)
from ..prompts.doctrine_decomposer import get_doctrine_decomposition_prompt

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
# NORMALISATION DES BIAIS (P5)
# =============================================
def _normalize_biais(raw: Optional[str]) -> Optional[str]:
    """
    Normalise `biais_detecte` contre les clés exactes de BIAS_LIST.
    Si le modèle a reformulé ou listé plusieurs options (ex: "Biais X ou Biais Y"),
    on cherche la première clé connue contenue dans la réponse.
    Retourne la valeur brute (pas None) si aucune clé n'est trouvée, pour ne pas perdre l'info.
    """
    if not raw or not BIAS_KEYS_LIST:
        return raw

    def _try_match(candidate: str) -> Optional[str]:
        c = candidate.lower().strip()
        if not c:
            return None
        # 1. Correspondance exacte
        for key in BIAS_KEYS_LIST:
            if key.lower() == c:
                return key
        # 2. La clé complète est contenue dans la réponse
        for key in BIAS_KEYS_LIST:
            if key.lower() in c:
                return key
        # 3. La base de la clé (sans parenthèses) est dans la réponse
        for key in BIAS_KEYS_LIST:
            base = key.split('(')[0].strip().lower()
            if len(base) > 6 and base in c:
                return key
        # 4. Le contenu des parenthèses (terme anglais) est dans la réponse
        #    (ex: "False Dichotomy" → "Fausse Dichotomie (Faux Dilemme)")
        for key in BIAS_KEYS_LIST:
            paren = re.search(r'\(([^)]+)\)', key)
            if paren and len(paren.group(1)) > 5 and paren.group(1).lower() in c:
                return key
        # 5. La réponse brute (courte) est contenue dans la clé
        for key in BIAS_KEYS_LIST:
            if len(c) > 6 and c in key.lower():
                return key
        return None

    # Premier essai sur le raw entier
    match = _try_match(raw)
    if match:
        return match

    # Fallback : le LLM a peut-être sorti plusieurs noms séparés par virgule / "ou" / " et "
    # Ex: "False Dichotomy, Projection Bias" → on prend le premier qui matche.
    for chunk in re.split(r'\s*(?:,|;|/|\bou\b|\bet\b|\bor\b)\s*', raw):
        m = _try_match(chunk)
        if m:
            logger.info(f"[P5] biais_detecte normalisé après split : '{raw[:50]}' → '{m}'")
            return m

    # Pas dans BIAS_LIST = pas forcément faux. Le LLM a sa propre connaissance
    # des biais (ex: "Biais d'attribution intergroupes", "Biais d'homogénéité
    # de l'exogroupe") qui ne sont pas dans notre liste prioritaire de 40.
    # On garde le nom tel quel — la définition et la source sont demandées au
    # LLM et permettent à l'utilisateur de juger.
    logger.info(f"[P5] biais_detecte hors-liste prioritaire (conservé) : '{raw[:80]}'")
    return raw


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
        Initialise les providers selon Config.LLM_MODE :
          - "local" : Ollama uniquement.
          - "cloud" (défaut) : Groq + Mistral.
        """
        providers = {}

        if Config.LLM_MODE == "local":
            ollama_p = get_provider("ollama")
            await ollama_p.initialize()
            providers["ollama"] = ollama_p
            logger.info("OllamaProvider initialisé (mode local).")
        else:
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
        logger.info(f"AnalysisOrchestrator prêt (mode={Config.LLM_MODE}).")
        return analyzer

    async def call_llm(self, task_name: str, messages: List[Dict[str, str]], temperature: float = 0.0, max_tokens: Optional[int] = None, response_format: Optional[Any] = None) -> str:
        """Méthode centralisée qui exécute l'IA pour une tâche, avec gestion de fallback (mode cloud).
        response_format : override du format — str 'json' OU schéma JSON (dict) pour une sortie
        contrainte (enum fermé). Si None, on prend le format défini par la route."""
        route = TourDeControle.get(task_name)
        primary_provider = route["provider"]
        primary_model = route["model"]
        primary_format = route.get("format")
        fmt = response_format if response_format is not None else primary_format

        # --- Mode local : appel direct, pas de fallback inter-provider ---
        if Config.LLM_MODE == "local":
            return await self.providers[primary_provider].complete_chat_async(
                messages=messages,
                model=primary_model,
                temperature=temperature,
                max_tokens=max_tokens,
                format=fmt,
            )

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
                max_tokens=max_tokens,
                format=fmt,
            )
        except Exception as e:
            logger.warning(f"Primary provider '{primary_provider}' failed for task '{task_name}': {e}. Messages: {messages}")
            self.health_manager.record_error(primary_provider)

            # --- Determine Fallback ---
            if primary_provider == "groq":
                fallback_provider = "mistral"
                # Utilisation directe du dictionnaire ROUTES pour ne pas déclencher le fallback récursif
                fallback_model = TourDeControle.ROUTES.get('fact_checking', {}).get('model', 'mistral-small-latest')
            elif primary_provider == "mistral":
                fallback_provider = "groq"
                # Utilisation directe du dictionnaire ROUTES pour ne pas déclencher le fallback récursif
                fallback_model = TourDeControle.ROUTES.get('selection_phrase', {}).get('model', 'llama-3.1-8b-instant')
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
                max_tokens=max_tokens,
                format=fmt,
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
    async def select_affirmation(
        self,
        buffer: List[Dict[str, Any]],
        history: List[Dict[str, str]],
        main_topic: Optional[str] = None,
        sub_topic: Optional[str] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Sélectionne l'affirmation la plus pertinente dans un buffer de phrases.
        Le contexte (main_topic/sub_topic du Radar) est injecté dans le prompt
        pour que la désambiguïsation des pronoms et la correction phonétique
        puissent s'appuyer sur le sujet courant — ex: passer 'il' à 'le voleur
        du Louvre' quand le sub_topic est 'Arrestation liée au Louvre'.
        """
        if not buffer:
            return None

        # Format the buffer and history for the prompt
        buffer_text = "\n".join([f"- (start={s.get('video_timestamp', s.get('start', 0.0)):.2f}s) {s.get('affirmation', s.get('text', ''))}" for s in buffer])
        history_text = "\n".join([f" - [{msg['role']}] {msg['content']}" for msg in history])

        # Bloc CONTEXTE explicite (sujet/sous-sujet du Radar) si dispo
        topic_block = ""
        if main_topic or sub_topic:
            topic_lines = []
            if main_topic:
                topic_lines.append(f"SUJET PRINCIPAL : {main_topic}")
            if sub_topic:
                topic_lines.append(f"SOUS-SUJET COURANT : {sub_topic}")
            topic_block = "\n".join(topic_lines) + "\n\n"

        user_content = (
            f"{topic_block}"
            f"HISTORIQUE COMPLET:\n{history_text}\n\n"
            f"BUFFER ACTUEL (phrases des dernières secondes):\n{buffer_text}\n\n"
            "Votre tâche est de sélectionner les affirmations pertinentes (maximum 3) à vérifier dans le BUFFER ACTUEL.\n"
            "DÉSAMBIGUÏSATION dans 'affirmation_corrigee' :\n"
            "1. Priorité absolue aux PHRASES VOISINES DU BUFFER (avant/après) pour identifier le sujet précis "
            "des pronoms ('il', 'ils', 'ce', 'celui-ci'). Si une phrase voisine nomme explicitement un acteur, "
            "remplace les pronoms par cet acteur.\n"
            "2. Le SOUS-SUJET COURANT peut être utilisé pour compléter si l'affirmation est manifestement la "
            "suite/conséquence du même événement (ex: sous-sujet='Cambriolage du Louvre' et affirmation='un "
            "des voleurs fuyait vers l'Algérie' → 'un des voleurs du Louvre fuyait vers l'Algérie').\n"
            "3. ATTENTION : si l'affirmation contient un autre nom propre ou un autre événement (ex: 'Lola', "
            "'Picasso'), NE LE MÉLANGE PAS avec le sous-sujet courant. C'est un autre sujet, traite-le tel quel.\n"
            "4. Mieux vaut une phrase corrigée légèrement ambiguë qu'un faux amalgame entre deux affaires.\n"
            "5. **PRÉSERVATION DES SUJETS/OBJETS PRÉCIS** : si l'affirmation parle d'une LOI, d'un PAYS, "
            "d'une POPULATION ou d'un GROUPE spécifique mentionné dans les phrases voisines (ex: 'la loi du "
            "Maghreb', 'les Algériens', 'les chrétiens'), tu DOIS préserver cette précision dans la phrase "
            "corrigée. Ne JAMAIS l'élider en formule générique. "
            "Ex: voisine='Dans les pays du Maghreb la loi interdit de perdre sa nationalité' + phrase='la loi "
            "interdit de perdre sa nationalité' → corrigée: '**Au Maghreb**, la loi interdit de perdre sa "
            "nationalité' (sinon le fact-checker va vérifier la loi française par défaut, ce qui est faux)."
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

            # Fallback robustesse : certains LLM (locaux notamment) renvoient un
            # objet unique au lieu d'une liste à un seul item. On normalise.
            if isinstance(parsed_selection, dict):
                if parsed_selection.get("affirmation_corrigee"):
                    parsed_selection = [parsed_selection]
                # Cas {"affirmations": [...]} ou {"selections": [...]}
                else:
                    for key in ("affirmations", "selections", "items", "résultats", "results"):
                        inner = parsed_selection.get(key)
                        if isinstance(inner, list):
                            parsed_selection = inner
                            break

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
    # PHASE 1.5D — Décomposition conceptuelle doctrinale
    # ------------------------------------------------------------------
    async def _decompose_doctrine(
        self,
        affirmation: str,
        main_topic: Optional[str] = None,
        sub_topic: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Décompose le qualificatif appliqué à une doctrine en conditions
        vérifiables + liste les textes sources majoritaires.
        Utilisé uniquement quand category == "DOCTRINE".
        Retourne None en cas d'échec (non bloquant).
        """
        prompt = get_doctrine_decomposition_prompt(affirmation, main_topic, sub_topic)
        messages = [{"role": "user", "content": prompt}]
        try:
            raw = await asyncio.wait_for(
                self.call_llm(
                    task_name="doctrine_decomposition",
                    messages=messages,
                    temperature=0.0,
                    max_tokens=600,
                ),
                timeout=Config.TIMEOUT,
            )
            parsed = parse_llm_json(raw)
            if isinstance(parsed, dict) and parsed.get("conditions"):
                logger.info(
                    f"[Phase 1.5D] Décomposition : qualificatif='{parsed.get('qualificatif')}' "
                    f"doctrine='{parsed.get('doctrine')}' "
                    f"({len(parsed['conditions'])} conditions)"
                )
                return parsed
            logger.warning(f"[Phase 1.5D] Réponse invalide — analyse DOCTRINE sans décomposition. Raw: {raw[:200]}")
        except Exception as e:
            logger.warning(f"[Phase 1.5D] Erreur décomposition doctrinale (non bloquant): {e}")
        return None

    # ------------------------------------------------------------------
    # ÉTAPE "VÉRIFIE" — CALIBRATION DU VERDICT PAR RUBRIQUE (levier bas coût)
    # ------------------------------------------------------------------
    async def _calibrate_verdict(self, affirmation: str, web_sources_block: str, proposed: str) -> Optional[str]:
        """2e passage contraint : confronte le verdict proposé aux extraits + rubrique stricte
        (VRAI<5% / IMPRECIS 5-25% / TROMPEUR cadré / FAUX / CONTESTE / NON_VERIFIABLE) et renvoie
        le verdict corrigé (enum fermé). Cadre l'interprétation des chiffres — le point faible."""
        schema = {
            "type": "object",
            "properties": {"verdict": {"type": "string",
                "enum": ["VRAI", "FAUX", "TROMPEUR", "IMPRECIS", "CONTESTE", "NON_VERIFIABLE"]}},
            "required": ["verdict"],
        }
        prompt = get_verdict_calibration_prompt(affirmation, web_sources_block or "", proposed or "?")
        try:
            raw = await asyncio.wait_for(
                self.call_llm(task_name="fact_checking", messages=[{"role": "user", "content": prompt}],
                              temperature=0.0, max_tokens=40, response_format=schema),
                timeout=Config.TIMEOUT,
            )
            parsed = parse_llm_json(raw)
            if isinstance(parsed, dict) and parsed.get("verdict"):
                return str(parsed["verdict"]).strip().upper()
        except Exception as e:
            logger.warning(f"[Calibration verdict] échec (non bloquant): {e}")
        return None

    async def _decide_verdict(self, affirmation: str, web_sources_block: str,
                              proposed: str, reasoning: str = "") -> Optional[str]:
        """Tête de verdict UNIFIÉE (levier architectural A1) : tranche sur l'enum COMPLET
        (factuels + BIAIS + OPINION) sans voir le label de catégorie. Casse le couplage
        catégorie→verdict : un FAIT mal classé LOGIQUE peut récupérer un verdict factuel."""
        schema = {
            "type": "object",
            "properties": {"verdict": {"type": "string",
                "enum": ["VRAI", "FAUX", "TROMPEUR", "IMPRECIS", "CONTESTE",
                         "NON_VERIFIABLE", "BIAIS", "OPINION"]}},
            "required": ["verdict"],
        }
        prompt = get_verdict_head_prompt(affirmation, web_sources_block or "", proposed or "?", reasoning or "")
        try:
            raw = await asyncio.wait_for(
                self.call_llm(task_name="fact_checking", messages=[{"role": "user", "content": prompt}],
                              temperature=0.0, max_tokens=40, response_format=schema),
                timeout=Config.TIMEOUT,
            )
            parsed = parse_llm_json(raw)
            if isinstance(parsed, dict) and parsed.get("verdict"):
                return str(parsed["verdict"]).strip().upper()
        except Exception as e:
            logger.warning(f"[Tête verdict] échec (non bloquant): {e}")
        return None

    # ------------------------------------------------------------------
    # NOMMAGE DE SOPHISME PAR CLASSIFICATION CONTRAINTE (LOGIQUE)
    # ------------------------------------------------------------------
    async def _name_sophisme(self, affirmation: str, main_topic: Optional[str] = None, sub_topic: Optional[str] = None) -> Optional[str]:
        """Nomme le sophisme par CLASSIFICATION CONTRAINTE (closed-set + option 'AUCUN').

        Recherche SOTA (research_sota.md) : choisir dans la liste fermée des biais bat la
        génération libre (le 12B 'sent' le sophisme mais le nomme mal — 3/10), et 'AUCUN'
        réduit le sur-étiquetage. Sortie JSON à enum fermé (Ollama format=schema).
        Retourne le nom EXACT d'un biais de la liste, ou None (AUCUN / échec).
        """
        if not SOPHISMES_DEBAT:
            return None
        schema = {
            "type": "object",
            "properties": {"sophisme": {"type": "string", "enum": SOPHISMES_DEBAT + ["AUCUN"]}},
            "required": ["sophisme"],
        }
        messages = [{"role": "user", "content": get_sophisme_naming_prompt(affirmation)}]
        try:
            raw = await asyncio.wait_for(
                self.call_llm(
                    task_name="classification", messages=messages,
                    temperature=0.0, max_tokens=80, response_format=schema,
                ),
                timeout=Config.TIMEOUT,
            )
            parsed = parse_llm_json(raw)
            if isinstance(parsed, dict):
                s = parsed.get("sophisme")
                if s and s.strip().upper() != "AUCUN" and s in SOPHISMES_DEBAT:
                    return s
        except Exception as e:
            logger.warning(f"[Sophisme naming] échec (non bloquant): {e}")
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
        sub_topic: Optional[str] = None,
        speaker: Optional[str] = None,
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

            category_upper = category_raw.strip().upper()
            if category_upper in VALID_CATEGORIES:
                category = category_upper
            else:
                found = next((c for c in VALID_CATEGORIES if c in category_upper), None)
                category = found if found else category_upper

            # --- LEVIER BAS-COÛT : reroute -> STATISTIQUE (guard déterministe) ---
            # Deux erreurs systématiques du benchmark : (1) FAIT_HISTORIQUE au lieu de
            # STATISTIQUE (73 cas), (2) sur-étiquetage LOGIQUE/OPINION sur des affirmations
            # dont la véracité repose en fait sur un chiffre porteur (%, montant, magnitude,
            # grand nombre). Seul le prompt STATISTIQUE applique la tolérance d'arrondi + la
            # détection de cherry-picking, donc ce reroutage améliore réellement l'analyse.
            # Précision mesurée sur golds : FAIT 5/189, LOGIQUE 2/68, OPINION 0/47. Les
            # hyperboles ("un million de fois") ne matchent pas (pas de chiffre adjacent).
            if (os.environ.get("ENABLE_STAT_REROUTE", "1") != "0"
                    and category in ("FAIT_HISTORIQUE", "LOGIQUE", "OPINION")
                    and has_statistical_signal(formatted_aff)):
                logger.info(f"[Phase 1 — reroute] {category} → STATISTIQUE (chiffre porteur) : '{formatted_aff[:50]}'")
                category = "STATISTIQUE"

            classif_health = self.health_manager.get_provider_health(classif_prov_name)
            final_classif_provider = (classif_health.get("fallback_active") and "groq") or classif_prov_name
            logger.info(f"[Phase 1 — {final_classif_provider.capitalize()}] Catégorie -> {category}")

            # --- PHASE 1.5D : DÉCOMPOSITION DOCTRINALE (DOCTRINE uniquement) ---
            # Exécutée AVANT le web search pour pouvoir le court-circuiter si besoin.
            doctrine_decomposition = None
            if category == "DOCTRINE":
                doctrine_decomposition = await self._decompose_doctrine(
                    formatted_aff, main_topic, sub_topic
                )

            # --- PHASE 1.5: RECHERCHE GOOGLE (catégories factuelles ciblées) ---
            # Court-circuitée pour DOCTRINE + décomposition active : les textes sacrés
            # (Coran, Hadith, Bible…) sont dans les données d'entraînement de Mistral ;
            # le web search ramène du commentaire contemporain qui noie les textes primaires.
            web_sources_block = ""
            if category in CATEGORIES_AVEC_RECHERCHE and not (category == "DOCTRINE" and doctrine_decomposition) and not os.environ.get("DISABLE_WEB_SEARCH"):
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
                            # --- LEVIER A2 : re-ranking des sources (le 12B se noie dans ~15 snippets) ---
                            # Re-classe par pertinence claim↔snippet (TF-IDF local CPU) et garde le top-k.
                            # Améliore les ENTRÉES du prompt spécialisé sans toucher à son jugement.
                            if os.environ.get("ENABLE_RERANK"):
                                from ..tools.rerank import rerank_snippets
                                before = len(filtered_urls)
                                filtered_urls = rerank_snippets(
                                    formatted_aff, filtered_urls, top_k=4,
                                    prefer_numeric=(category == "STATISTIQUE"))
                                logger.info(f"[Phase 1.5 — rerank] {before} → {len(filtered_urls)} source(s) (top pertinence).")
                            web_sources_block = format_urls_for_prompt(filtered_urls)
                            logger.info(f"[Phase 1.5] {len(filtered_urls)} source(s) web validée(s) et injectée(s).")
                        else:
                            logger.info("[Phase 1.5] Toutes les sources ont été filtrées (non fiables).")
                    else:
                        logger.info("[Phase 1.5] Aucune source web trouvée.")
                except Exception as e:
                    logger.warning(f"[Phase 1.5] Erreur lors de la recherche Google (non bloquant) : {e}")

            # --- GUARD ANTI-HALLUCINATION : STATISTIQUE sans source chiffrée ---
            # Si aucune source web n'a été trouvée pour une affirmation chiffrée, on refuse
            # de laisser Mistral inventer un chiffre de référence. Mieux vaut NON_VÉRIFIABLE.
            if category == "STATISTIQUE" and not web_sources_block and not os.environ.get("DISABLE_WEB_SEARCH"):
                logger.warning(f"[Phase 2 — Guard] STATISTIQUE sans source → NON_VÉRIFIABLE forcé pour : '{formatted_aff[:50]}'")
                return {
                    "affirmation": formatted_aff,
                    "analyse": {
                        "verdict": "NON_VÉRIFIABLE",
                        "score": "0%",
                        "explanation_long": (
                            "Aucune source officielle (INSEE, Eurostat, OCDE…) n'a pu être trouvée "
                            "pour vérifier ce chiffre. Pour éviter toute hallucination statistique, "
                            "l'analyse automatique est suspendue. "
                            "Vérifiez manuellement sur la source citée ou sur insee.fr / ec.europa.eu."
                        ),
                        "explanation_short": "Aucune source primaire disponible — vérification chiffrée impossible.",
                        "biais_detecte": None,
                    },
                    "raw_response": None,
                    "category": category,
                    "model": TourDeControle.get('fact_checking')['model'],
                    "status": "non_verifiable",
                    "main_topic": main_topic,
                    "sub_topic": sub_topic,
                    "web_sources": None,
                }

            # --- PHASE 2: ANALYSE SPÉCIALISÉE via Mistral ---
            fc_prov = TourDeControle.get('fact_checking')['provider'].capitalize()
            logger.info(f"[Phase 2 — {fc_prov}] Analyse spécialisée pour '{category}'")
            system_prompt = get_specialized_system_prompt(
                category,
                main_topic=main_topic,
                sub_topic=sub_topic,
                doctrine_decomposition=doctrine_decomposition,
            )

            web_sources_section = f"\n\n---\n\n{web_sources_block}\n\n---\n\n" if web_sources_block else ""

            # P7 — note explicite du locuteur : aide la détection de contradictions
            # quand l'historique est filtré par intervenant.
            speaker_note = f"\nAFFIRMATION PRONONCÉE PAR : {speaker}" if speaker else ""

            user_prompt = (
                f"{analysis_context_header}"
                f"L'objectif est de fact-checker la phrase suivante.\n"
                f"UTILISEZ LE CONTEXTE UNIQUEMENT POUR COMPRENDRE ET DÉSAMBIGUÏSER L'AFFIRMATION, PAS POUR LA VALIDER. "
                f"Votre analyse doit se concentrer UNIQUEMENT sur l'AFFIRMATION À ANALYSER."
                f"{web_sources_section}"
                f"{speaker_note}"
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

            doctrine_max_tokens = 2000 if (category == "DOCTRINE" and doctrine_decomposition) else Config.MAX_TOKENS
            analysis_response_raw = await asyncio.wait_for(
                self.call_llm(
                    task_name="fact_checking",
                    messages=messages,
                    temperature=0.0,
                    max_tokens=doctrine_max_tokens
                ),
                timeout=Config.TIMEOUT
            )

            # Parsing du JSON retourné par l'LLM
            parsed_analysis = self._parse_llm_json(analysis_response_raw)

            # Normalisation du verdict :
            # - tirets → underscores (NON-VÉRIFIABLE → NON_VÉRIFIABLE)
            # - É/é → E/e (NON_VÉRIFIABLE → NON_VERIFIABLE) pour éviter les doublons
            #   selon que le modèle accentue ou pas.
            if isinstance(parsed_analysis, dict) and "verdict" in parsed_analysis:
                v = str(parsed_analysis["verdict"]).replace("-", "_")
                v = v.replace("É", "E").replace("é", "e")
                v = v.replace("È", "E").replace("è", "e")
                parsed_analysis["verdict"] = v

            # P5 — Normalisation du nom de biais contre BIAS_LIST
            if isinstance(parsed_analysis, dict) and parsed_analysis.get("biais_detecte"):
                parsed_analysis["biais_detecte"] = _normalize_biais(parsed_analysis["biais_detecte"])

            # ----- GARDE-FOUS PROGRAMMATIQUES POST-LLM -----
            # Mistral Nemo 12B accepte les consignes en surface mais ne les
            # applique pas systématiquement (audit 2026-05-04). On ne peut
            # pas se reposer uniquement sur le prompt — on durcit ici.
            if isinstance(parsed_analysis, dict):
                self._apply_post_llm_guards(parsed_analysis, category)

            # --- LEVIER SOTA : nommage de sophisme par classification contrainte (LOGIQUE) ---
            # Remplace le nom librement généré (souvent faux, 3/10) par un choix dans la liste
            # fermée, ou None si 'AUCUN' (réduit les fausses alarmes de sur-étiquetage).
            # B2 : étendre la passe contrainte à OPINION/DOCTRINE (94 % des manques de biais
            # sont des sophismes mal routés hors LOGIQUE où _name_sophisme ne se déclenchait pas).
            # On ne touche QUE biais_detecte, jamais le verdict (guard BIAIS reste LOGIQUE-only).
            bias_pass_cats = (("LOGIQUE", "OPINION", "DOCTRINE")
                              if os.environ.get("ENABLE_BIAS_EXTEND") else ("LOGIQUE",))
            if category in bias_pass_cats and isinstance(parsed_analysis, dict):
                named = await self._name_sophisme(formatted_aff, main_topic, sub_topic)
                if named:
                    parsed_analysis["biais_detecte"] = named
                    logger.info(f"[Sophisme contraint — {category}] → {named}")
                elif category == "LOGIQUE":
                    logger.info("[Sophisme contraint] → AUCUN (nom d'origine conservé)")

            # --- LEVIER "VÉRIFIE" : calibration du verdict factuel par rubrique (flag) ---
            if (os.environ.get("ENABLE_VERDICT_CALIBRATION")
                    and category in ("STATISTIQUE", "FAIT_HISTORIQUE", "JURIDIQUE", "CONSENSUS_SCIENCE")
                    and isinstance(parsed_analysis, dict) and parsed_analysis.get("verdict")):
                cal = await self._calibrate_verdict(formatted_aff, web_sources_block,
                                                    parsed_analysis.get("verdict"))
                if cal and cal != str(parsed_analysis.get("verdict")).upper():
                    logger.info(f"[Calibration] verdict {parsed_analysis.get('verdict')} → {cal}")
                    parsed_analysis["verdict"] = cal

            # --- LEVIER ARCHITECTURAL A1 : tête de verdict unifiée (découple cat→verdict) ---
            # RÉSULTAT A/B (2026-06-27, défaut OFF) : RÉGRESSE le verdict (-3.5 pts moy held-out,
            # M2 48→39). La tête générique re-décide TOUT et jette les priors tunés des prompts
            # spécialisés (tolérance d'arrondi STATISTIQUE, cherry-pick) → pousse vers les extrêmes
            # (IMPRECIS→FAUX/NON_VERIFIABLE). Ne dé-hedge bien que CONTESTE/BIAIS→factuel (minoritaire).
            # CONSERVÉ OFF : ne réactiver qu'en version CHIRURGICALE (ne tirer que sur les verdicts
            # « hedge » CONTESTE/NON_VERIFIABLE, jamais sur un verdict factuel déjà posé).
            if (os.environ.get("ENABLE_VERDICT_HEAD")
                    and isinstance(parsed_analysis, dict) and parsed_analysis.get("verdict")):
                reasoning = str(parsed_analysis.get("explanation_long", ""))
                head = await self._decide_verdict(formatted_aff, web_sources_block,
                                                  parsed_analysis.get("verdict"), reasoning)
                if head and head != str(parsed_analysis.get("verdict")).upper():
                    logger.info(f"[Tête verdict] {parsed_analysis.get('verdict')} → {head}")
                    parsed_analysis["verdict"] = head

            return {
                "affirmation": formatted_aff,
                "analyse": parsed_analysis,
                "raw_response": analysis_response_raw,
                "category": category,
                "model": TourDeControle.get('fact_checking')['model'],
                "status": "success",
                "main_topic": main_topic,
                "sub_topic": sub_topic,
                "speaker": speaker,
                "web_sources": web_sources_block if web_sources_block else None,
            }

        except Exception as e:
            raise AnalysisError(f"Erreur d'analyse: {str(e)}")

    def _apply_post_llm_guards(self, analyse: Dict[str, Any], category: str) -> None:
        """Garde-fous programmatiques post-LLM. Modifie `analyse` en place.

        Trois patterns observés en audit 2026-05-04 où le LLM ne suit pas
        les consignes du prompt :

        1. **Liens biais inventés** : `biais_source` peut être une URL 404
           que Mistral fabrique (ex: `Biais_de_responsabilité_attribuée`
           sur Wikipédia FR n'existe pas). On vérifie via HEAD HTTP, on met
           `null` si 404 ou erreur.

        2. **LOGIQUE → autre chose que BIAIS** : le prompt LOGIQUE dit
           "OBLIGATOIREMENT BIAIS" mais Mistral sort parfois FAUX/OPINION.
           Override : si catégorie LOGIQUE, force verdict = BIAIS.

        3. **FAUX abusif** : le LLM met FAUX quand les sources ne mentionnent
           simplement pas le sujet. On détecte par mots-clés dans
           l'explication ("pas de preuve", "aucune source", "n'existe pas
           dans les sources"...) et on force NON_VÉRIFIABLE.
        """
        verdict = str(analyse.get("verdict", "")).upper()

        # --- Garde-fou 1 : LOGIQUE → BIAIS forcé ---
        if category == "LOGIQUE" and verdict not in ("BIAIS", "OPINION"):
            # OPINION reste toléré (cas limites), mais FAUX/VRAI/CONTESTÉ → forcer BIAIS
            if verdict in ("FAUX", "VRAI", "CONTESTE", "TROMPEUR", "IMPRECIS"):
                logger.info(f"[Guard] LOGIQUE force {verdict} → BIAIS")
                analyse["verdict"] = "BIAIS"
                verdict = "BIAIS"

        # --- Garde-fou 2 : FAUX abusif → NON_VÉRIFIABLE ---
        if verdict == "FAUX":
            expl = (str(analyse.get("explanation_long", "")) +
                    " " + str(analyse.get("explanation_short", ""))).lower()
            abusive_patterns = [
                "pas de preuve", "aucune preuve",
                "aucune source", "pas de source",
                "les sources ne mentionnent pas", "ne sont pas mentionn",
                "ne fait pas mention", "ne font pas mention",
                "n'est pas mentionn", "ne traite pas du sujet",
                "n'existe pas dans les sources", "absence de source",
            ]
            if any(p in expl for p in abusive_patterns):
                logger.info(f"[Guard] FAUX abusif (silence des sources) → NON_VERIFIABLE")
                analyse["verdict"] = "NON_VERIFIABLE"

        # --- Garde-fou 3 : Vérifier les liens biais_source ---
        # Mistral Nemo invente des URLs Wikipédia plausibles mais inexistantes
        # (ex: 'Biais_de_responsabilit%C3%A9_attribu%C3%A9e' = 404 réel).
        # Pour Wikipédia : on passe par l'API officielle (très fiable, JSON).
        # Pour les autres URLs : politique tolérante (seul un 404 invalide).
        biais_source = analyse.get("biais_source")
        if biais_source and isinstance(biais_source, str) and biais_source.lower().startswith(("http://", "https://")):
            invalid = self._check_url_exists(biais_source)
            if invalid:
                logger.info(f"[Guard] biais_source invalide (404 / page inexistante) → null : {biais_source}")
                analyse["biais_source"] = None

    @staticmethod
    def _check_url_exists(url: str) -> bool:
        """Retourne True SI l'URL est démontrée invalide (404 / page Wikipédia
        inexistante). Sinon (200, 403, erreur réseau, etc.), retourne False par
        prudence — on ne tue un lien que si on est SÛR qu'il est faux."""
        import re
        from urllib.parse import unquote
        import httpx

        # Cas 1 : URL Wikipédia → API officielle (la plus fiable).
        m = re.match(r"https?://(\w{2})\.wikipedia\.org/wiki/(.+?)(?:#|$)", url)
        if m:
            lang = m.group(1)
            # Décoder les %xx ; httpx ré-encodera proprement les caractères
            # Unicode pour la requête API.
            title = unquote(m.group(2))
            try:
                api = f"https://{lang}.wikipedia.org/w/api.php"
                params = {"action": "query", "format": "json", "titles": title, "redirects": 1}
                headers = {"User-Agent": "CodeCitoyen-FactCheck/1.0 (https://github.com/5H1N0B11/CodeCitoyen)"}
                with httpx.Client(timeout=5.0, headers=headers) as cli:
                    r = cli.get(api, params=params)
                    if r.status_code == 200:
                        data = r.json()
                        pages = data.get("query", {}).get("pages", {})
                        # Si la page n'existe pas, l'API renvoie pageid = -1
                        for _, page in pages.items():
                            if page.get("missing") is not None or str(page.get("pageid", "-1")) == "-1":
                                return True  # Page Wikipédia inexistante = lien invalide
                            return False
                    return False  # API indisponible : on garde par prudence
            except Exception:
                return False

        # Cas 2 : URL non-Wikipédia → GET avec User-Agent navigateur.
        try:
            headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101 Firefox/126.0"}
            with httpx.Client(timeout=5.0, follow_redirects=True, headers=headers) as cli:
                r = cli.get(url)
                # Tolérant : seul un 404 explicite invalide.
                return r.status_code == 404
        except Exception:
            return False  # Erreur réseau : on conserve par défaut

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
