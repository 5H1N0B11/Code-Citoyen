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
    MIN_CLAIM_LENGTH = 10
    MAX_CLAIM_LENGTH = 500
    MAX_CONCURRENT_REQUESTS = 1 # Crucial pour éviter le rate-limit de l'API Mistral.
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
    """
    if isinstance(text, dict):
        affirmation_text = text.get('affirmation')
        return isinstance(affirmation_text, str) and \
               Config.MIN_CLAIM_LENGTH <= len(affirmation_text.strip()) <= Config.MAX_CLAIM_LENGTH
    elif isinstance(text, str):
        return Config.MIN_CLAIM_LENGTH <= len(text.strip()) <= Config.MAX_CLAIM_LENGTH
    return False

def format_affirmation(affirmation: Union[str, Dict]) -> str:
    """
    Formate une affirmation pour l'analyse.
    """
    if isinstance(affirmation, dict):
        return str(affirmation.get('affirmation', '')).strip()
    return str(affirmation).strip()

def extract_text_from_vtt(file_path: str) -> str:
    """
    Extrait le contenu textuel d'un fichier VTT en ignorant les métadonnées.
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    text_content = []
    # Regex pour identifier les lignes de texte qui ne sont pas des métadonnées VTT
    text_line_regex = re.compile(r'^[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3} --> [0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}')

    for i, line in enumerate(lines):
        line = line.strip()
        if not line or line.startswith('WEBVTT') or line.startswith('Kind:') or line.startswith('Language:') or '-->' in line:
            # Si la ligne est une métadonnée ou une ligne de temps, on la saute
            # Mais on vérifie si la ligne suivante est le texte à extraire
            if '-->' in line and i + 1 < len(lines):
                next_line = lines[i+1].strip()
                # Si la ligne suivante n'est pas vide et n'est pas une autre métadonnée, on la prend
                if next_line and not ('-->' in next_line or next_line.startswith('WEBVTT') or next_line.startswith('Kind:') or next_line.startswith('Language:')):
                    # Supprimer les balises de temps et autres balises VTT
                    cleaned_line = re.sub(r'<[^>]+>', '', next_line)
                    if cleaned_line:
                        text_content.append(cleaned_line)

    # Éviter les doublons si le texte est présent à la fois avec et sans balises
    unique_content = []
    for item in text_content:
        if not unique_content or unique_content[-1] not in item:
            unique_content.append(item)
            
    return "\n".join(unique_content)