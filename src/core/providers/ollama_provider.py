"""
Fournisseur d'IA pour Ollama (LLM local).

Ce provider parle au daemon Ollama via son API REST (par défaut sur
http://localhost:11434). Il s'intègre dans la même architecture
AbstractAIProvider que MistralProvider et GroqProvider, ce qui rend la
bascule cloud → local transparente côté orchestrator.

Spécificités :
  - Pas de rate-limiter : on parle à un service local, le débit est borné
    par le GPU. Inutile d'imposer un délai.
  - Support natif de `format="json"` : Ollama force le modèle à produire
    un JSON valide. Très utile pour fiabiliser les petits modèles.
  - `num_ctx` configurable (env OLLAMA_NUM_CTX) — par défaut 16384.
    Indispensable car Ollama tronque à 4096 par défaut, ce qui est
    insuffisant pour nos prompts RULE_GOLD + contexte long.
"""

import os
import logging
from typing import List, Dict, Optional

import httpx

from .base import AbstractAIProvider
from ...utils import AnalysisError

logger = logging.getLogger(__name__)

OLLAMA_DEFAULT_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "mistral-nemo:12b")
OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "16384"))
OLLAMA_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "180"))


class OllamaProvider(AbstractAIProvider):
    """Provider local via Ollama (HTTP REST)."""

    def __init__(self):
        self.base_url = OLLAMA_DEFAULT_URL
        self.client: Optional[httpx.AsyncClient] = None

    async def initialize(self, api_key: Optional[str] = None) -> None:
        """Vérifie que le daemon Ollama répond et que le modèle par défaut est dispo."""
        try:
            self.client = httpx.AsyncClient(base_url=self.base_url, timeout=OLLAMA_TIMEOUT)
            r = await self.client.get("/api/version")
            r.raise_for_status()
            version = r.json().get("version", "?")
            logger.info(f"OllamaProvider initialisé (Ollama {version} sur {self.base_url})")

            tags = await self.client.get("/api/tags")
            tags.raise_for_status()
            installed = {m.get("name") for m in tags.json().get("models", [])}
            if OLLAMA_DEFAULT_MODEL not in installed:
                logger.warning(
                    f"Modèle '{OLLAMA_DEFAULT_MODEL}' absent. Installés: {sorted(installed)}. "
                    f"Lance `ollama pull {OLLAMA_DEFAULT_MODEL}` si besoin."
                )
            else:
                logger.info(f"Modèle par défaut disponible : {OLLAMA_DEFAULT_MODEL}")
        except Exception as e:
            raise AnalysisError(
                f"Impossible de joindre Ollama à {self.base_url}. "
                f"Vérifiez que le daemon tourne (`ollama serve`). Erreur : {e}"
            ) from e

    async def complete_chat_async(
        self,
        messages: List[Dict[str, str]],
        model: str = OLLAMA_DEFAULT_MODEL,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        format: Optional[str] = None,
    ) -> str:
        if not self.client:
            raise AnalysisError("OllamaProvider non initialisé. Appelez initialize() d'abord.")

        options: Dict[str, object] = {
            "temperature": temperature,
            "num_ctx": OLLAMA_NUM_CTX,
        }
        if max_tokens is not None:
            options["num_predict"] = max_tokens

        payload: Dict[str, object] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": options,
        }
        if format:
            payload["format"] = format

        logger.info(f"Ollama → {model} (msgs={len(messages)}, format={format or 'libre'})")
        try:
            r = await self.client.post("/api/chat", json=payload)
            r.raise_for_status()
            data = r.json()
            content = data.get("message", {}).get("content", "")
            if not content:
                raise AnalysisError(f"Ollama a retourné une réponse vide. Payload: {data}")
            return content.strip()
        except httpx.HTTPStatusError as e:
            raise AnalysisError(
                f"Erreur HTTP Ollama: {e.response.status_code} {e.response.text[:200]}"
            ) from e
        except Exception as e:
            raise AnalysisError(f"Erreur appel Ollama: {e}") from e
