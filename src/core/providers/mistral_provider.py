# src/core/providers/mistral_provider.py
import os
import logging
import asyncio
from typing import List, Dict, Optional

from .base import AbstractAIProvider
from ...utils import AnalysisError

# Configuration du logging
logger = logging.getLogger(__name__)

class MistralProvider(AbstractAIProvider):
    """Implémentation du fournisseur d'IA pour MistralAI."""

    def __init__(self):
        self.client = None

    async def initialize(self, api_key: Optional[str] = None) -> None:
        """Initialise le client Mistral."""
        try:
            from mistralai import Mistral
        except ImportError as e:
            raise AnalysisError(f"Erreur critique: Impossible de charger mistralai: {str(e)}. Assurez-vous que la bibliothèque 'mistralai' est correctement installée.")

        api_key = api_key or os.getenv("MISTRAL_API_KEY")
        if not api_key:
            raise AnalysisError("Clé API MistralAI non configurée. Veuillez définir la variable d'environnement MISTRAL_API_KEY.")

        try:
            self.client = Mistral(api_key=api_key)
            logger.info("Client Mistral initialisé avec succès via le Provider.")
        except Exception as e:
            raise AnalysisError(f"Erreur d'initialisation du client Mistral: {str(e)}")

    async def complete_chat_async(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.0
    ) -> str:
        """Effectue un appel chat asynchrone à l'API Mistral."""
        if not self.client:
            raise AnalysisError("Le client Mistral n'est pas initialisé. Appelez 'initialize' d'abord.")
        
        try:
            logger.info(f"Envoi de la requête à Mistral (Model: {model})...")
            response = await self.client.chat.complete_async(
                model=model,
                messages=messages,
                temperature=temperature
            )
            logger.info("Réponse reçue de Mistral.")
            return response.choices[0].message.content.strip()
        except Exception as e:
            raise AnalysisError(f"Erreur de l'API Mistral: {str(e)}")