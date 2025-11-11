# config.py - Configuration centrale du projet

import os
from typing import Dict, Any

class APIConfig:
    """Configuration pour l'API MistralAI"""

    # Modèle par défaut
    DEFAULT_MODEL = os.getenv("MISTRAL_DEFAULT_MODEL", "mistral-small-latest")

    # Paramètres de timeout
    TIMEOUT = int(os.getenv("API_TIMEOUT", "30"))
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
    RETRY_DELAY = int(os.getenv("RETRY_DELAY", "2"))

    # Configuration des chemins
    @staticmethod
    def get_config() -> Dict[str, Any]:
        """Retourne la configuration complète"""
        return {
            "default_model": APIConfig.DEFAULT_MODEL,
            "timeout": APIConfig.TIMEOUT,
            "max_retries": APIConfig.MAX_RETRIES,
            "retry_delay": APIConfig.RETRY_DELAY
        }

# Configuration des chemins
class PathConfig:
    """Configuration des chemins du projet"""

    @staticmethod
    def get_project_root() -> str:
        """Retourne le chemin racine du projet"""
        from pathlib import Path
        return str(Path(__file__).parent.parent.parent)

# Configuration des logs
class LogConfig:
    """Configuration des logs"""

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Export des configurations
API_CONFIG = APIConfig.get_config()
PROJECT_ROOT = PathConfig.get_project_root()
LOG_CONFIG = {
    "level": LogConfig.LOG_LEVEL,
    "format": LogConfig.LOG_FORMAT
}