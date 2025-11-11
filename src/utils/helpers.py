# helpers.py
import re
from typing import Any

def clean_text(text: str) -> str:
    """
    Nettoie un texte en supprimant les espaces superflus et les caractères spéciaux

    Args:
        text: Le texte à nettoyer

    Returns:
        Le texte nettoyé
    """
    if not text:
        return ""

    # Suppression des espaces superflus
    text = ' '.join(text.split())

    # Suppression des caractères spéciaux (sauf ponctuation de base)
    text = re.sub(r'[^\w\s.,;:!?\'"-]', '', text)

    return text.strip()

def validate_text(text: str) -> bool:
    """
    Valide qu'un texte n'est pas vide et contient des caractères valides

    Args:
        text: Le texte à valider

    Returns:
        True si le texte est valide, False sinon
    """
    if not text or not isinstance(text, str):
        return False

    # Vérification qu'il reste du contenu après nettoyage
    cleaned = clean_text(text)
    return len(cleaned) > 0

def format_response(response: Any) -> str:
    """
    Formate une réponse de l'API pour un affichage propre

    Args:
        response: La réponse brute de l'API

    Returns:
        La réponse formatée
    """
    if not response:
        return "Aucune réponse valide reçue"

    if isinstance(response, str):
        return clean_text(response)

    if isinstance(response, dict):
        return clean_text(response.get('content', ''))

    return clean_text(str(response))