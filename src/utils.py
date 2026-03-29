#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module utilitaire pour le projet Code Citoyen.

Ce module contient des fonctions, classes et constantes générales
utilisées par plusieurs autres modules du projet. Le but est de
centraliser le code commun et d'éviter les dépendances circulaires.
"""

import logging
import re
import time
import threading
import json
import ast
from typing import Union, Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# =============================================
# CLASSES DE CONFIGURATION ET D'ERREURS
# =============================================
class Config:
    """
    Classe de configuration centrale pour l'application.
    """
    
    TIMEOUT = 30
    MAX_RETRIES = 3
    RETRY_DELAY = 2
    MAX_TOKENS = 1000
    TEMPERATURE = 0.7
    MIN_WORDS_FOR_ANALYSIS = 3  # Seuil de mots minimum pour une analyse pertinente
    MIN_CLAIM_LENGTH = 10
    MAX_CLAIM_LENGTH = 500
    MAX_CONCURRENT_REQUESTS = 1 # Crucial pour éviter le rate-limit de l'API Mistral.
    WINDOW_SIZE_SECONDS = 40 # Taille de la fenêtre d'analyse pour le Fact-Checker (augmentée pour mieux capter les arguments longs)
    RADAR_INTERVAL_SECONDS = 45 # Intervalle de mise à jour du sujet par le Radar
    VIDEO_DELAY_SECONDS = 5     # Délai de fallback (en secondes) si la phrase n'a pas de timestamp vidéo.
    FALLBACK_COOLDOWN_DURATION = 60 # Durée du cooldown en secondes pour les API en fallback
    BANNED_DOMAINS = ["twitter.com", "x.com", "facebook.com", "tiktok.com", "instagram.com"]

class AnalysisError(Exception):
    """
    Exception personnalisée générique pour les erreurs d'analyse.
    """
    pass

class ApiHealthManager:
    """
    Gère l'état de santé des fournisseurs d'API et active/désactive le mode fallback.
    C'est un singleton pour s'assurer qu'il n'y a qu'une seule instance gérant l'état global.
    """
    _instance = None
    _lock = threading.Lock() # Protège l'accès à l'instance et à l'état interne

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init_state()
                cls._instance.fallback_cooldown_duration = Config.FALLBACK_COOLDOWN_DURATION
            return cls._instance

    def _init_state(self):
        self.provider_status = {
            "groq": {"fallback_active": False, "cooldown_until": 0.0, "error_count": 0},
            "mistral": {"fallback_active": False, "cooldown_until": 0.0, "error_count": 0},
        }

    def record_error(self, provider_name: str):
        with self._lock:
            if provider_name in self.provider_status:
                self.provider_status[provider_name]["error_count"] += 1
                self.provider_status[provider_name]["fallback_active"] = True
                self.provider_status[provider_name]["cooldown_until"] = time.time() + self.fallback_cooldown_duration
                logger.warning(f"{provider_name.capitalize()} API a rencontré une erreur. Mise en cooldown pour {self.fallback_cooldown_duration} secondes.")

    def get_provider_health(self, provider_name: str) -> Dict[str, Any]:
        with self._lock:
            return self.provider_status.get(provider_name, {}).copy() # Retourne une copie pour éviter les modifications externes

    def check_and_update_fallback(self, provider_name: str):
        with self._lock:
            if provider_name in self.provider_status:
                status = self.provider_status[provider_name]
                if  status["fallback_active"] and time.time() > status["cooldown_until"]:
                    status["fallback_active"] = False
                    status["cooldown_until"] = 0.0
                    logger.info(f"Cooldown terminé pour {provider_name}. Désactivation du fallback.")

    def get_cooldown_remaining(self, provider_name: str) -> float:
         with self._lock:
            if provider_name in self.provider_status:
                remaining = self.provider_status[provider_name]["cooldown_until"] - time.time()
                return max(0, remaining)  # Ensure it doesn't return negative values
            return 0.0

    def reset_error_count(self, provider_name: str):
        with self._lock:
            if provider_name in self.provider_status:
                self.provider_status[provider_name]["error_count"] = 0
                logger.info(f"Compteur d'erreurs réinitialisé pour {provider_name}.")

class TourDeControle:
    """
    Le Routeur de tâches central du projet.
    Associe chaque tâche spécifique à un fournisseur et à un modèle précis.
    Architecture Hybride : Groq pour les tâches très rapides et légères (sélection de phrase)
    et Mistral pour les tâches complexes ou plus gourmandes en tokens (classification, analyse, résumé).
    """
    ROUTES = {
        # --- Préparation (Setup au démarrage) ---
        "extraction_sujet":   {"provider": "groq",    "model": "llama-3.1-8b-instant"}, # Tâche rapide, idéale pour Groq
        "extraction_entites": {"provider": "mistral", "model": "mistral-small-latest"},
        "resume_actus":       {"provider": "mistral", "model": "mistral-small-latest"},
        "biographies":        {"provider": "mistral", "model": "mistral-small-latest"},
        
        # --- Direct (Boucle Live de Streaming) ---
        "radar_contexte":     {"provider": "mistral", "model": "mistral-small-latest"}, # Déplacé vers Mistral car peut être gourmand en tokens
        "selection_phrase":   {"provider": "groq",    "model": "llama-3.1-8b-instant"}, # Tâche critique pour le live, doit être très rapide
        "classification":     {"provider": "mistral", "model": "mistral-small-latest"}, # Tâche critique, déplacée sur Mistral pour la qualité
        "extraction_mots_cles": {"provider": "mistral", "model": "mistral-small-latest"}, # Tâche créative, nécessite un bon modèle
        
        # --- Juge Final (Fact-Checking) ---
        "fact_checking":      {"provider": "mistral", "model": "mistral-small-latest"},
    }
    
    @classmethod
    def get(cls, task_name: str) -> Dict[str, str]:
        health_manager = ApiHealthManager()
        health_manager.check_and_update_fallback("groq")
        health_manager.check_and_update_fallback("mistral")

        route = cls.ROUTES.get(task_name)

        if route is None:
            logger.warning(f"Tâche '{task_name}' non définie dans TourDeControle. Fallback par défaut sur 'mistral'.")
            return {"provider": "mistral", "model": "mistral-small-latest"}

        original_primary_provider = route["provider"]

        # Determine the alternative provider
        alternative_provider = "mistral" if original_primary_provider == "groq" else "groq"

        # Check health of the original primary provider
        if health_manager.get_provider_health(original_primary_provider)["fallback_active"]:
            # Original primary is in cooldown. Try to use the alternative.
            if not health_manager.get_provider_health(alternative_provider)["fallback_active"]:
                logger.warning(f"Le fournisseur primaire '{original_primary_provider}' est en cooldown. Bascule sur '{alternative_provider}' pour la tâche '{task_name}'.")
                return {"provider": alternative_provider, "model":  cls.ROUTES.get('fact_checking', {}).get('model', 'mistral-small-latest') if alternative_provider == "mistral" else  cls.ROUTES.get('classification', {}).get('model', 'llama-3.1-8b-instant')}
            else:
                # Both are in cooldown. Log and return the original primary.
                logger.warning(f"Les deux fournisseurs ('{original_primary_provider}' et '{alternative_provider}') sont en cooldown. La tâche '{task_name}' utilisera le fournisseur primaire en cooldown, ce qui va probablement échouer.")

        return route

# =============================================
# FONCTIONS UTILITAIRES
# =============================================

def parse_llm_json(response_text: str) -> Union[Dict[str, Any], List[Any], None]:
    """
    Tente de parser une réponse JSON/Python-literal d'un LLM, en nettoyant les balises Markdown.
    Retourne un dictionnaire ou une liste si succès, sinon None.
    """
    cleaned_text = response_text.strip()

    # 1. Enlever les blocs de code markdown ```json ... ``` ou ``` ... ```
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned_text, re.DOTALL)
    if match:
        cleaned_text = match.group(1).strip()

    # 2. Trouver le début et la fin du JSON (soit {..} soit [..])
    start_brace = cleaned_text.find('{')
    start_bracket = cleaned_text.find('[')
    
    start_idx = -1
    
    if start_brace == -1 and start_bracket == -1:
        return None # No JSON object/list found

    if start_brace != -1 and (start_bracket == -1 or start_brace < start_bracket):
        start_idx = start_brace
        end_char = '}'
    else:
        start_idx = start_bracket
        end_char = ']'

    end_idx = cleaned_text.rfind(end_char)

    if start_idx != -1 and end_idx > start_idx:
        json_candidate = cleaned_text[start_idx : end_idx + 1]
        
        # 3. Tenter de parser avec json.loads
        try:
            # strict=False permet de tolérer les vrais sauts de ligne (control characters) 
            # insérés par Mistral à l'intérieur des chaînes de caractères.
            return json.loads(json_candidate, strict=False)
        except json.JSONDecodeError:
            # 4. Fallback avec ast.literal_eval pour les dicts/listes Python (guillemets simples)
            try:
                return ast.literal_eval(json_candidate)
            except (ValueError, SyntaxError, MemoryError):
                pass # Fall through to return None
    
    return None

def validate_text(text: Union[str, Dict]) -> bool:
    """
    Valide qu'un texte ou dictionnaire d'affirmation est valide.
    Lève une AnalysisError si la validation échoue.
    """
    if isinstance(text, dict):
        affirmation_text = text.get('text') or text.get('affirmation', '')
    elif isinstance(text, str):
        affirmation_text = text
    else:
        raise AnalysisError("Le texte doit être une chaîne de caractères ou un dictionnaire avec 'text'/'affirmation'.")

    if not isinstance(affirmation_text, str):
        raise AnalysisError("Le texte doit être une chaîne de caractères.")

    if not affirmation_text.strip():
        raise AnalysisError("Le texte ne peut pas être vide.")

    if len(affirmation_text.strip()) < Config.MIN_CLAIM_LENGTH:
        raise AnalysisError(f"Le texte est trop court, il doit contenir au moins {Config.MIN_CLAIM_LENGTH} caractères.")

    # Optional: Check if it has enough words as per MIN_WORDS_FOR_ANALYSIS
    if len(affirmation_text.strip().split()) < Config.MIN_WORDS_FOR_ANALYSIS:
        logger.warning(f"Le texte a moins de {Config.MIN_WORDS_FOR_ANALYSIS} mots, l'analyse pourrait être moins pertinente.")

    return True


def format_affirmation(affirmation: Union[str, Dict]) -> str:
    """
    Formate une affirmation pour l'analyse.
    """
    if isinstance(affirmation, dict):
        return str(affirmation.get('text') or affirmation.get('affirmation', '')).strip()
    return str(affirmation).strip()

def extract_text_from_vtt(file_path: str) -> str:
    """
    Extrait le contenu textuel d'un fichier VTT en ignorant les métadonnées.
    Retourne une chaîne de caractères unique avec les dialogues séparés par des sauts de ligne.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        text_content = []
        # Regex pour identifier les lignes de temps
        timestamp_regex = re.compile(r'\d{2}:\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3}')

        for line in lines:
            line = line.strip()
            # Ignorer les lignes vides, les en-têtes VTT et les lignes de temps
            if line and not line.startswith('WEBVTT') and not timestamp_regex.match(line) and not line.isdigit():
                # Nettoyer les balises de formatage VTT comme <v ...>
                cleaned_line = re.sub(r'<[^>]+>', '', line).strip()
                if cleaned_line:
                    text_content.append(cleaned_line)
        
        # Dédoublonnage instantané O(N) préservant l'ordre (depuis Python 3.7)
        return "\n".join(dict.fromkeys(text_content))
    except Exception as e:
        logger.error(f"Erreur lors de l'extraction du texte VTT depuis {file_path}: {e}")
        return ""
