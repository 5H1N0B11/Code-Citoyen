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
from typing import Union, Dict, Any

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
    VIDEO_DELAY_SECONDS = 5     # Délai de fallback (en secondes) si la phrase n'a pas de timestamp vidéo.
class AnalysisError(Exception):
    """
    Exception personnalisée générique pour les erreurs d'analyse.
    """
    pass

class TourDeControle:
    """
    Le Routeur de tâches central du projet.
    Associe chaque tâche spécifique à un fournisseur et à un modèle précis.
    Note: Utilisation fixée à 'mistral-small-3-latest' (au lieu de latest/v4) pour économiser des tokens tout en conservant une excellente logique d'analyse.
    """
    ROUTES = {
        # --- Préparation (Setup au démarrage) ---
        "extraction_sujet":   {"provider": "mistral", "model": "mistral-small-3-latest"},
        "extraction_entites": {"provider": "mistral", "model": "mistral-small-3-latest"},
        "resume_actus":       {"provider": "mistral", "model": "mistral-small-3-latest"},
        "biographies":        {"provider": "mistral", "model": "mistral-small-3-latest"},
        
        # --- Direct (Boucle Live de Streaming) ---
        "radar_contexte":     {"provider": "groq",    "model": "llama-3.1-8b-instant"},
        "selection_phrase":   {"provider": "groq",    "model": "llama-3.1-8b-instant"},
        "classification":     {"provider": "mistral", "model": "mistral-small-3-latest"},
        
        # --- Juge Final (Fact-Checking) ---
        "fact_checking":      {"provider": "mistral", "model": "mistral-small-3-latest"},
    }
    
    @classmethod
    def get(cls, task_name: str) -> Dict[str, str]:
        if task_name not in cls.ROUTES:
            logger.warning(f"Tâche '{task_name}' non définie dans TourDeControle. Fallback sur mistral.")
            return {"provider": "mistral", "model": "mistral-small-3-latest"}
        return cls.ROUTES[task_name]

# =============================================
# FONCTIONS UTILITAIRES
# =============================================

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