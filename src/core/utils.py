#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module utilitaire pour le projet Code Citoyen.

Ce module contient des fonctions, classes et constantes générales
utilisées par plusieurs autres modules du projet. Le but est de
centraliser le code commun et d'éviter les dépendances circulaires.
"""

import logging
from typing import Union, Dict, Any

logger = logging.getLogger(__name__)

# =============================================
# CLASSES DE CONFIGURATION ET D'ERREURS
# =============================================
class Config:
    """
    Classe de configuration centrale pour l'application.
    """
    DEFAULT_MODEL = "mistral-small-latest"
    TIMEOUT = 30
    MAX_RETRIES = 3
    RETRY_DELAY = 2
    MAX_TOKENS = 1000
    TEMPERATURE = 0.7
    MIN_CLAIM_LENGTH = 10
    MAX_CLAIM_LENGTH = 500

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

    Args:
        text: Le texte ou dictionnaire à valider.

    Returns:
        bool: True si le texte est valide, False sinon.
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

    Args:
        affirmation: L'affirmation à formater.

    Returns:
        str: L'affirmation formatée.
    """
    if isinstance(affirmation, dict):
        return str(affirmation.get('affirmation', '')).strip()
    return str(affirmation).strip()

def format_response(response: Any) -> str:
    """
    Formate une réponse de l'API pour un affichage propre.

    Args:
        response: La réponse brute de l'API.

    Returns:
        str: La réponse formatée.
    """
    if not response:
        return "Aucune réponse valide reçue"

    if isinstance(response, str):
        return response.strip()

    if hasattr(response, 'choices') and len(response.choices) > 0:
        if hasattr(response.choices[0], 'message') and hasattr(response.choices[0].message, 'content'):
            return response.choices[0].message.content.strip()

    return str(response).strip()