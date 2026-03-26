import json
import logging
from collections import deque
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class HistoryManager:
    """Gestionnaire d'historique des affirmations."""
    def __init__(self, max_size: int = 10000, result_dir: Path = None):
        if result_dir is None:
            # Par défaut, pointe vers src/results/
            result_dir = Path(__file__).parent.parent / "results"
            result_dir.mkdir(parents=True, exist_ok=True)
            
        self.max_size = max_size
        self.history = deque(maxlen=max_size)
        self.history_file = result_dir / "history.json"
        # self.load_history() # Désactivé pour éviter de recharger la mémoire de la session précédente au démarrage

    def add_to_history(self, item: Dict[str, Any]) -> None:
        self.history.append(item)
        self.save_history()

    def get_history(self) -> List[Dict[str, Any]]:
        return list(self.history)

    def save_history(self) -> None:
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(list(self.history), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde de l'historique: {str(e)}")

    def load_history(self) -> None:
        try:
            if self.history_file.exists():
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.history = deque(json.load(f), maxlen=self.max_size)
        except Exception as e:
            logger.error(f"Erreur lors du chargement de l'historique: {str(e)}")
            self.history = deque(maxlen=self.max_size)

    def clear_history(self) -> None:
        """Vide l'historique en mémoire et potentiellement le fichier."""
        self.history.clear()
        if self.history_file.exists():
            try:
                self.history_file.unlink()
                logger.info("Fichier d'historique supprimé.")
            except Exception as e:
                logger.error(f"Erreur lors de la suppression du fichier d'historique: {str(e)}")
        logger.info("Historique vidé.")

    def get_formatted_history(self, limit: int = 5) -> List[Dict[str, str]]:
        """Retourne l'historique récent formaté pour le modèle de chat."""
        formatted_history = []
        recent_history = list(self.history)[-limit:]
        for item in recent_history:
            if item.get("status") == "error" or not item.get("result"):
                continue
            formatted_history.append({"role": "user", "content": item.get("affirmation", "N/A")})
            formatted_history.append({"role": "assistant", "content": str(item.get("result", {}).get("analyse", "N/A"))})
        return formatted_history