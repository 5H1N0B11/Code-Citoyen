# src/core/providers/base.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class AbstractAIProvider(ABC):
    """
    Classe de base abstraite définissant l'interface pour un fournisseur d'IA.
    Chaque fournisseur (Mistral, Gemini, etc.) devra hériter de cette classe
    et implémenter ses méthodes.
    """

    @abstractmethod
    async def initialize(self, api_key: Optional[str] = None) -> None:
        """
        Initialise le client spécifique au fournisseur.
        Doit lever une exception si l'initialisation échoue.
        """
        pass

    @abstractmethod
    async def complete_chat_async(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float
    ) -> str:
        """
        Méthode générique pour effectuer un appel chat asynchrone.
        """
        pass