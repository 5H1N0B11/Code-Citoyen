#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module pour récupérer le contexte sur les interlocuteurs.

Ce module a pour but de faire des recherches web ciblées pour
identifier le rôle et le background public d'une personne.
"""

import asyncio
import logging
import re
import json
from typing import List, Dict, Any

from ..core.providers import get_provider
from ..utils import Config

logger = logging.getLogger(__name__)

def guess_speakers_from_filename(filename: str) -> List[str]:
    """
    Tente de deviner les noms des intervenants à partir du nom de fichier.
    Utilise une heuristique simple basée sur les noms propres (majuscules).

    Args:
        filename: Le nom du fichier (sans extension).

    Returns:
        Une liste de noms potentiels.
    """
    # Heuristique : recherche des séquences de deux mots ou plus commençant par une majuscule.
    # Ex: "Éric Zemmour", "Apolline de Malherbe"
    # C'est imparfait mais souvent efficace sur les titres de vidéos.
    potential_names = re.findall(r'([A-ZÉÀ-ÖØ-Þ][a-zà-öø-ÿ]+(?:\s[A-ZÉÀ-ÖØ-Þ][a-zà-öø-ÿ]+)+)', filename)
    # Heuristique v2 : Recherche des séquences de mots commençant par une majuscule,
    # en autorisant des particules non capitalisées (de, d', du) entre eux.
    # Ex: "Éric Zemmour", "Apolline de Malherbe", "Charles de Gaulle"
    # ([A-ZÉÀ-ÖØ-Þ][a-zà-öø-ÿ'-]+) : Capture un mot commençant par une majuscule (peut contenir ' ou -).
    # (?:\s(?:de|d'|du)\s[A-ZÉÀ-ÖØ-Þ][a-zà-öø-ÿ'-]+)* : Capture les particules suivies d'un mot capitalisé.
    # (?:\s[A-ZÉÀ-ÖØ-Þ][a-zà-öø-ÿ'-]+)+ : Capture les séquences de mots capitalisés.
    potential_names = re.findall(r"([A-ZÉÀ-ÖØ-Þ][a-zà-öø-ÿ'-]+(?:\s(?:de|d'|du)\s[A-ZÉÀ-ÖØ-Þ][a-zà-öø-ÿ'-]+|\s[A-ZÉÀ-ÖØ-Þ][a-zà-öø-ÿ'-]+)+)", filename)

    # Nettoyage et dédoublonnage simple
    return sorted(list(set([name.strip() for name in potential_names])))

async def extract_entities_from_text(full_text: str) -> List[str]:
    """
    Utilise une IA pour extraire les noms de personnes et d'organisations d'un texte.

    Args:
        full_text: L'intégralité de la transcription.

    Returns:
        Une liste de noms uniques.
    """
    logger.info("Extraction des entités nommées de la transcription complète...")
    try:
        provider = get_provider(Config.DEFAULT_PROVIDER)
        await provider.initialize()

        prompt = (
            "Analyse le texte suivant et extrais TOUS les noms propres de personnes et d'organisations (partis politiques, entreprises, etc.). "
            "Ne liste que les noms les plus pertinents pour comprendre le contexte de la discussion. Ignore les noms de lieux non pertinents. "
            "Formate ta réponse EXCLUSIVEMENT en JSON, sous la forme d'une liste de chaînes de caractères. "
            "Exemple de sortie : [\"Emmanuel Macron\", \"Marine Le Pen\", \"Rassemblement National\", \"TotalEnergies\"]\n\n"
            f"TEXTE À ANALYSER :\n\n{full_text[:8000]}" # On tronque pour être sûr de ne pas dépasser les limites
        )

        response = await provider.complete_chat_async(messages=[{"role": "user", "content": prompt}], model=Config.DEFAULT_MODEL, temperature=0.0)
        
        # Nettoyage pour extraire la liste JSON
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if json_match:
            entities = json.loads(json_match.group(0))
            return sorted(list(set(entities)))
        return []
    except Exception as e:
        logger.error(f"Erreur lors de l'extraction des entités: {e}")
        return []

async def fetch_speaker_background(name: str, semaphore: asyncio.Semaphore) -> str:
    """
    Utilise une IA pour générer une biographie concise d'une personne.

    Args:
        name: Le nom de la personne à rechercher.
        semaphore: Le sémaphore partagé pour contrôler les appels API.

    Returns:
        Une chaîne de caractères décrivant le background de la personne.
    """
    logger.info(f"Recherche du background pour : {name}")
    try:
        # On utilise le provider par défaut (Mistral) pour cette tâche
        provider = get_provider(Config.DEFAULT_PROVIDER)
        await provider.initialize() # On s'assure qu'il est initialisé pour cette tâche spécifique, au cas où.

        prompt = (
            "RÉPONSE EN FRANÇAIS. Ton rôle est de fournir une biographie ultra-concise (1-2 phrases MAXIMUM) "
            "d'une personnalité publique. Tu dois te concentrer sur son rôle principal actuel et passé le plus pertinent. "
            "Exemple pour 'Emmanuel Macron': 'Homme d'État français, actuel président de la République française depuis 2017.' "
            "Exemple pour 'Apolline de Malherbe': 'Journaliste et animatrice de radio et de télévision française, notamment sur RMC et BFM TV.'\n\n"
            f"Personnalité à décrire : {name}"
        )

        # Utilisation du sémaphore partagé pour garantir un seul appel à la fois
        async with semaphore:
            logger.info(f"-> Appel API (Background) pour '{name}'")
            background = await provider.complete_chat_async(messages=[{"role": "user", "content": prompt}], model=Config.DEFAULT_MODEL, temperature=0.1)
            return f"- {name}: {background.strip()}"

    except Exception as e:
        logger.error(f"Erreur lors de la recherche du background pour {name}: {e}")
        return f"- {name}: Impossible de récupérer le background."