# src/core/providers/__init__.py
from .base import AbstractAIProvider
from .mistral_provider import MistralProvider
from .groq_provider import GroqProvider


def get_provider(provider_name: str = "mistral") -> AbstractAIProvider:
    """
    Factory qui retourne une instance du fournisseur d'IA demandé.
    """
    if provider_name.lower() == "mistral":
        return MistralProvider()
    elif provider_name.lower() == "groq":
        return GroqProvider()
    else:
        raise ValueError(f"Fournisseur d'IA inconnu: {provider_name}")
