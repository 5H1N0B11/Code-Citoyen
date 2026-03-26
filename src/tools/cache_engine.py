#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module de mise en cache SQLite pour les recherches web.
Permet d'économiser des requêtes réseau pour des requêtes identiques.
"""

import sqlite3
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

class CacheEngine:
    def __init__(self, db_path=None):
        if db_path is None:
            # Résolution dynamique pour pointer vers data/cache.db à la racine du projet
            current_dir = Path(__file__).parent.absolute()
            project_root = current_dir.parent.parent
            self.db_path = project_root / "data" / "cache.db"
        else:
            self.db_path = Path(db_path)
            
        # Création du dossier cible s'il n'existe pas
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialise la table SQLite si elle n'existe pas."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS search_cache (
                    query TEXT PRIMARY KEY,
                    results TEXT,
                    timestamp DATETIME
                )
            ''')
            conn.commit()

    def get_cached_result(self, query: str):
        """Récupère un résultat en cache s'il a moins de 24h."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT results, timestamp FROM search_cache WHERE query = ?", (query,))
                row = cursor.fetchone()

                if row:
                    results_json, timestamp_str = row
                    timestamp = datetime.fromisoformat(timestamp_str)
                    
                    # Vérifie si le cache est valide (< 24h)
                    if datetime.now() - timestamp < timedelta(hours=24):
                        logger.debug(f"Cache HIT pour la requête : '{query}'")
                        return json.loads(results_json)
                    else:
                        # Cache expiré, on nettoie
                        logger.debug(f"Cache EXPIRED pour la requête : '{query}'")
                        cursor.execute("DELETE FROM search_cache WHERE query = ?", (query,))
                        conn.commit()
                        
        except Exception as e:
            logger.error(f"Erreur lors de la lecture du cache SQLite : {e}")
        
        return None

    def cache_result(self, query: str, results):
        """Stocke un résultat de recherche dans le cache."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # Désactive l'ASCII pour garder les caractères accentués lisibles dans la base
                results_json = json.dumps(results, ensure_ascii=False)
                timestamp_str = datetime.now().isoformat()
                
                # INSERT OR REPLACE permet d'écraser un vieux cache s'il existe déjà
                cursor.execute('''
                    INSERT OR REPLACE INTO search_cache (query, results, timestamp)
                    VALUES (?, ?, ?)
                ''', (query, results_json, timestamp_str))
                conn.commit()
                logger.debug(f"Résultat mis en cache pour : '{query}'")
        except Exception as e:
            logger.error(f"Erreur lors de l'écriture dans le cache SQLite : {e}")