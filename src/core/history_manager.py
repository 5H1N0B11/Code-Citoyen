import json
import logging
import threading
from collections import deque, defaultdict
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class HistoryManager:
    """Gestionnaire d'historique des affirmations."""
    def __init__(self, max_size: int = 10000, result_dir: Path = None):
        if result_dir is None:
            result_dir = Path(__file__).parent.parent / "results"
            result_dir.mkdir(parents=True, exist_ok=True)

        self.max_size = max_size
        self.history = deque(maxlen=max_size)
        self._next_id = 1
        self.history_file = result_dir / "history.json"

        # Index par intervenant : { "nom_intervenant": [id1, id2, ...] }
        self._speaker_index: Dict[str, List[int]] = defaultdict(list)

        # Sauvegarde debounced : évite les IO bloquantes dans le lock appelant
        self._save_timer: threading.Timer = None
        self._save_lock = threading.Lock()

    def add_to_history(self, item: Dict[str, Any], speaker: Optional[str] = None) -> None:
        if "id" not in item:
            item["id"] = self._next_id
            self._next_id += 1
        # P7 — speaker peut venir soit du paramètre explicite, soit de l'item
        # (cas où le buffer du stream a déjà mis 'speaker' dans la transcription).
        effective_speaker = speaker or item.get("speaker")
        if effective_speaker:
            item["speaker"] = effective_speaker
            self._speaker_index[effective_speaker.strip().lower()].append(item["id"])
        self.history.append(item.copy())
        self._schedule_save()

    def update_item(self, item_id: int, updates: Dict[str, Any]) -> bool:
        for i, item in enumerate(self.history):
            if item.get("id") == item_id:
                self.history[i].update(updates)
                self._schedule_save()
                return True
        logger.warning(f"Item with ID {item_id} not found in history for update.")
        return False

    def get_history(self) -> List[Dict[str, Any]]:
        return list(self.history)

    def _schedule_save(self) -> None:
        """Demande une sauvegarde dans 500ms (debounced). Non-bloquant."""
        with self._save_lock:
            if self._save_timer is not None:
                self._save_timer.cancel()
            self._save_timer = threading.Timer(0.5, self._do_save)
            self._save_timer.daemon = True
            self._save_timer.start()

    def _do_save(self) -> None:
        try:
            data = list(self.history)
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde de l'historique: {str(e)}")

    def save_history(self) -> None:
        """Sauvegarde immédiate (utilisée lors du clear ou de la fermeture)."""
        if self._save_timer is not None:
            self._save_timer.cancel()
        self._do_save()

    def load_history(self) -> None:
        try:
            if self.history_file.exists():
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.history = deque(json.load(f), maxlen=self.max_size)
        except Exception as e:
            logger.error(f"Erreur lors du chargement de l'historique: {str(e)}")
            self.history = deque(maxlen=self.max_size)

    def clear_history(self) -> None:
        self.history.clear()
        if self._save_timer is not None:
            self._save_timer.cancel()
        if self.history_file.exists():
            try:
                self.history_file.unlink()
                logger.info("Fichier d'historique supprimé.")
            except Exception as e:
                logger.error(f"Erreur lors de la suppression du fichier d'historique: {str(e)}")
        logger.info("Historique vidé.")

    def get_formatted_history(self, limit: int = 20) -> List[Dict[str, str]]:
        """Retourne l'historique récent formaté pour le modèle de chat (fenêtre élargie à 20)."""
        return self._format_items(list(self.history)[-limit:])

    def get_formatted_history_by_speaker(self, speaker: str, limit: int = 10) -> List[Dict[str, str]]:
        """
        Retourne l'historique des affirmations d'un intervenant spécifique.
        Utile pour la détection de contradictions intra-débat par personne.
        """
        key = speaker.strip().lower()
        item_ids = self._speaker_index.get(key, [])
        if not item_ids:
            return []
        # Récupère les items correspondants depuis l'historique complet
        id_set = set(item_ids[-limit:])
        matching = [item for item in self.history if item.get("id") in id_set]
        return self._format_items(matching)

    def _format_items(self, items: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """Formate une liste d'items d'historique en messages de chat."""
        formatted_history = []
        for item in items:
            if item.get("type") != "analyse" or item.get("status") == "error" or not item.get("result"):
                continue
            analysis_data = item.get("result", {}).get("analyse")
            if isinstance(analysis_data, dict):
                affirmation_text = item.get("affirmation", "N/A")
                speaker_prefix = f"[{item['speaker']}] " if item.get("speaker") else ""
                verdict = analysis_data.get("verdict", "INCONNU")
                explanation_short = analysis_data.get("explanation_short", "Analyse non disponible.")
                biais = analysis_data.get("biais_detecte")
                biais_mention = f" Biais détecté: {biais}." if biais else ""

                formatted_history.append({"role": "user", "content": f"{speaker_prefix}{affirmation_text}"})
                concise_analysis = f"Verdict: {verdict}. Synthèse: {explanation_short}{biais_mention}"
                formatted_history.append({"role": "assistant", "content": concise_analysis})
        return formatted_history
