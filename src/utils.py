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
    DEFAULT_PROVIDER = "mistral"
    DEFAULT_MODEL = "mistral-small-latest"
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
		
		# Utiliser un set pour garantir l'unicité puis joindre
		return "\n".join(sorted(list(set(text_content)), key=lines.index))
	except Exception as e:
		logger.error(f"Erreur lors de l'extraction du texte VTT depuis {file_path}: {e}")
		return ""