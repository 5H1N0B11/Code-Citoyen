# src/core/providers/groq_provider.py
"""
Fournisseur d'IA pour l'API Groq.
Utilisé EXCLUSIVEMENT pour les phases légères (Phase 0 et Phase 1) :
- Extraction de sujet/sous-sujet
- Classification de l'affirmation

Modèle : llama-3.1-8b-instant (rapide, faible latence, idéal pour la classification)

RATE LIMITING CENTRALISÉ :
  Le plan gratuit Groq autorise ~30 req/min sur llama-3.1-8b-instant.
  Pour éviter les 429, on impose un délai minimum de GROQ_MIN_CALL_INTERVAL
  secondes entre TOUS les appels Groq, quel que soit l'appelant.
  Ce délai est géré par un verrou asyncio global (_groq_rate_lock) et un
  timestamp du dernier appel (_groq_last_call_time).
"""
import os
import logging
import asyncio
import time
from typing import List, Dict, Optional
from ...utils import ApiHealthManager # Import ApiHealthManager
from .base import AbstractAIProvider
from ...utils import AnalysisError

logger = logging.getLogger(__name__)

# Le modèle llama3-8b-8192 a été décommissionné par Groq.
# On passe sur le modèle actuellement supporté : llama-3.1-8b-instant.
GROQ_DEFAULT_MODEL = "llama-3.1-8b-instant"

# -----------------------------------------------------------------------
# RATE LIMITER GLOBAL — protège TOUS les appels Groq de façon centralisée
# Le plan gratuit autorise ~30 req/min. On met un délai pour lisser les bursts.
# -----------------------------------------------------------------------
GROQ_MIN_CALL_INTERVAL: float = 2.0   # secondes entre deux appels Groq

# Verrou asyncio global (partagé entre toutes les instances de GroqProvider)
_groq_rate_lock: asyncio.Lock = asyncio.Lock()
_groq_last_call_time: float = 0.0     # timestamp du dernier appel réussi


class GroqProvider(AbstractAIProvider):
    """Implémentation du fournisseur d'IA pour l'API Groq (via llama-3.1-8b-instant)."""

    def __init__(self):
        self.client = None

    async def initialize(self, api_key: Optional[str] = None) -> None:
        """Initialise le client Groq."""
        try:
            from groq import AsyncGroq
        except ImportError as e:
            raise AnalysisError(
                f"Erreur critique: Impossible de charger groq: {str(e)}. "
                "Assurez-vous que la bibliothèque 'groq' est correctement installée (pip install groq)."
            )

        api_key = api_key or os.getenv("GROQ_API_KEY")
        if not api_key:
            raise AnalysisError(
                "Clé API Groq non configurée. "
                "Veuillez définir la variable d'environnement GROQ_API_KEY."
            )

        try:
            # max_retries=0 est CRITIQUE pour empêcher le client de faire des sleep(20s) cachés lors des 429
            self.client = AsyncGroq(api_key=api_key, max_retries=0)
            logger.info("Client Groq initialisé avec succès.")
        except Exception as e:
            raise AnalysisError(f"Erreur d'initialisation du client Groq: {str(e)}")

    async def complete_chat_async(
        self,
        messages: List[Dict[str, str]],
        model: str = GROQ_DEFAULT_MODEL,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        format: Optional[str] = None,
    ) -> str:
        """
        Effectue un appel chat asynchrone à l'API Groq.

        RATE LIMITING CENTRALISÉ :
        Avant chaque appel, on acquiert le verrou global _groq_rate_lock et on
        attend que GROQ_MIN_CALL_INTERVAL secondes se soient écoulées depuis le
        dernier appel. Cela garantit qu'aucun appelant (orchestrator, flush_buffer,
        etc.) ne peut déclencher deux appels Groq en moins de GROQ_MIN_CALL_INTERVAL
        secondes, même en concurrence.
        """
        global _groq_last_call_time

        if not self.client:
            raise AnalysisError(
                "Le client Groq n'est pas initialisé. Appelez 'initialize' d'abord."
            )

        # --- Attente du délai minimum ET exécution séquentielle ---
        async with _groq_rate_lock:
            # Le verrou garantit qu'un seul appel Groq est exécuté à la fois.
            # On attend d'abord que l'intervalle minimum se soit écoulé depuis la fin de l'appel précédent.
            try:
                now = asyncio.get_running_loop().time()
                elapsed = now - _groq_last_call_time
                if elapsed < GROQ_MIN_CALL_INTERVAL:
                    wait_time = GROQ_MIN_CALL_INTERVAL - elapsed
                    logger.debug(f"[Groq RateLimiter] Attente {wait_time:.2f}s avant prochain appel.")
                    await asyncio.sleep(wait_time)

                # Maintenant, on effectue l'appel API à l'intérieur du verrou.
                logger.info(f"Envoi de la requête à Groq (Model: {model})...")
                response = await self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                logger.info("Réponse reçue de Groq.")
                return response.choices[0].message.content.strip()
            except Exception as e:
                raise AnalysisError(f"Erreur de l'API Groq: {str(e)}")
            finally:
                # On met à jour le timestamp de fin d'appel, que ce soit un succès ou un échec.
                _groq_last_call_time = asyncio.get_running_loop().time()
