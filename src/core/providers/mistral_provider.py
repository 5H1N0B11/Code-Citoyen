# src/core/providers/mistral_provider.py
import os
import logging
import asyncio
from typing import List, Dict, Optional, Any

from .base import AbstractAIProvider
from ...utils import AnalysisError

# Configuration du logging
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# RATE LIMITER GLOBAL — protège TOUS les appels Mistral de façon centralisée
# Les plans payants sont généreux, mais un fallback massif depuis Groq
# pourrait créer un burst. On met un petit délai pour lisser la charge.
# 2.0s entre chaque appel = 30 req/min (très conservateur, plan de base ~60 RPM)
# -----------------------------------------------------------------------
MISTRAL_MIN_CALL_INTERVAL: float = 2.0   # secondes entre deux appels Mistral

# Verrou asyncio global (partagé entre toutes les instances de MistralProvider)
_mistral_rate_lock: asyncio.Lock = asyncio.Lock()
_mistral_last_call_time: float = 0.0     # timestamp du dernier appel réussi

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
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        format: Optional[str] = None,
    ) -> str:
        """Effectue un appel chat asynchrone à l'API Mistral."""
        global _mistral_last_call_time

        if not self.client:
            raise AnalysisError("Le client Mistral n'est pas initialisé. Appelez 'initialize' d'abord.")
        
        # --- Attente du délai minimum ET exécution séquentielle ---
        async with _mistral_rate_lock:
            # Le verrou garantit qu'un seul appel Mistral est exécuté à la fois.
            # On attend d'abord que l'intervalle minimum se soit écoulé depuis la fin de l'appel précédent.
            try:
                now = asyncio.get_running_loop().time()
                elapsed = now - _mistral_last_call_time
                if elapsed < MISTRAL_MIN_CALL_INTERVAL:
                    wait_time = MISTRAL_MIN_CALL_INTERVAL - elapsed
                    logger.debug(f"[Mistral RateLimiter] Attente {wait_time:.2f}s avant prochain appel.")
                    await asyncio.sleep(wait_time)

                # Maintenant, on effectue l'appel API à l'intérieur du verrou.
                logger.info(f"Envoi de la requête à Mistral (Model: {model})...")
                response = await self.client.chat.complete_async(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                logger.info("Réponse reçue de Mistral.")
                return response.choices[0].message.content.strip()
            except Exception as e:
                raise AnalysisError(f"Erreur de l'API Mistral: {str(e)}")
            finally:
                # On met à jour le timestamp de fin d'appel, que ce soit un succès ou un échec.
                _mistral_last_call_time = asyncio.get_running_loop().time()