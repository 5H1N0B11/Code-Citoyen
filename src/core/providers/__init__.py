# src/core/providers/__init__.py
from .base import AbstractAIProvider
from .mistral_provider import MistralProvider
# Importer d'autres providers ici à l'avenir (ex: Gemini)

def get_provider(provider_name: str = "mistral") -> AbstractAIProvider:
    """
    Factory qui retourne une instance du fournisseur d'IA demandé.
    """
    if provider_name.lower() == "mistral":
        return MistralProvider()
    # elif provider_name.lower() == "gemini":
    #     return GeminiProvider()
    else:
        raise ValueError(f"Fournisseur d'IA inconnu: {provider_name}")