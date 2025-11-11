# error_handling.py - Gestion des erreurs

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

def handle_api_error(error: Exception) -> str:
    """
    Gère les erreurs API de manière standardisée

    Args:
        error: L'exception à traiter

    Returns:
        Message d'erreur formaté
    """
    error_type = type(error).__name__
    error_msg = str(error)

    logger.error(f"Erreur API: {error_type} - {error_msg}")

    # Messages d'erreur personnalisés selon le type
    if "Timeout" in error_type:
        return "Erreur: Timeout lors de la requête API"
    elif "Authentication" in error_type:
        return "Erreur: Problème d'authentification"
    elif "RateLimit" in error_type:
        return "Erreur: Limite de requêtes atteinte"
    else:
        return f"Erreur API: {error_msg}"

def log_and_continue(error: Exception, context: str = "") -> None:
    """
    Log une erreur et continue l'exécution

    Args:
        error: L'exception
        context: Contexte de l'erreur
    """
    logger.error(f"Erreur {context}: {str(error)}")

def validate_config(config: dict) -> bool:
    """
    Valide la configuration

    Args:
        config: Dictionnaire de configuration

    Returns:
        True si la configuration est valide
    """
    required_keys = ["default_model", "timeout", "max_retries"]
    if not all(key in config for key in required_keys):
        logger.error("Configuration incomplète")
        return False
    return True