# src/core/providers/__init__.py
from .base import AbstractAIProvider
from .mistral_provider import MistralProvider
from .groq_provider import GroqProvider
from .ollama_provider import OllamaProvider

_provider_instances = {} # Cache pour les instances (Singleton)

def get_provider(provider_name: str = "mistral") -> AbstractAIProvider:
    """
    Factory qui retourne une instance du fournisseur d'IA demandé.
    Utilise un cache pour garantir qu'une seule instance de chaque fournisseur est créée (Singleton pattern).
    """
    provider_name_lower = provider_name.lower()

    if provider_name_lower not in _provider_instances:
        if provider_name_lower == "mistral":
            _provider_instances[provider_name_lower] = MistralProvider()
        elif provider_name_lower == "groq":
            _provider_instances[provider_name_lower] = GroqProvider()
        elif provider_name_lower == "ollama":
            _provider_instances[provider_name_lower] = OllamaProvider()
        else:
            raise ValueError(f"Fournisseur d'IA inconnu: {provider_name}")

    return _provider_instances[provider_name_lower]
