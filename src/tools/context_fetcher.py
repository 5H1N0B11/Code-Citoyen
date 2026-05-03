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
from typing import List, Dict, Any, TYPE_CHECKING

from ..core.providers import get_provider
from ..utils import TourDeControle, parse_llm_json
from ..prompts.templates import get_entity_extraction_prompt, get_biography_prompt

if TYPE_CHECKING:
    from ..core.orchestrator import AnalysisOrchestrator

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
    # Heuristique : Recherche des séquences de mots commençant par une majuscule,
    # en autorisant des particules non capitalisées (de, d', du) entre eux.
    # Ex: "Éric Zemmour", "Apolline de Malherbe", "Charles de Gaulle"
    potential_names = re.findall(r"([A-ZÉÀ-ÖØ-Þ][a-zà-öø-ÿ'-]+(?:\s(?:de|d'|du)\s[A-ZÉÀ-ÖØ-Þ][a-zà-öø-ÿ'-]+|\s[A-ZÉÀ-ÖØ-Þ][a-zà-öø-ÿ'-]+)+)", filename)

    # Nettoyage et dédoublonnage simple
    return sorted(list(set([name.strip() for name in potential_names])))

async def extract_entities_from_text(orchestrator: "AnalysisOrchestrator", full_text: str) -> List[str]:
    """
    Utilise une IA pour extraire les noms de personnes et d'organisations d'un texte.

    Args:
        orchestrator: L'instance de l'orchestrateur pour faire l'appel LLM.
        full_text: L'intégralité de la transcription.

    Returns:
        Une liste de noms uniques.
    """
    logger.info("Extraction des entités nommées de la transcription complète...")
    try:
        prompt = get_entity_extraction_prompt(full_text)
        response = await orchestrator.call_llm(
            task_name="extraction_entites",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0
        )
        
        # Utilisation du parseur JSON centralisé
        entities = parse_llm_json(response)
        if isinstance(entities, list):
            # Assure l'unicité et le tri, et garantit que ce sont des chaînes
            return sorted(list(set(str(e) for e in entities)))
        
        logger.warning(f"Impossible d'extraire une liste JSON valide des entités. Réponse brute: {response[:200]}")
        return []
    except Exception as e:
        logger.error(f"Erreur lors de l'extraction des entités: {e}")
        return []

async def fetch_speaker_background(orchestrator: "AnalysisOrchestrator", name: str) -> str:
    """
    Utilise une IA pour générer une biographie concise d'une personne.

    Args:
        orchestrator: L'instance de l'orchestrateur pour faire l'appel LLM.
        name: Le nom de la personne à rechercher.

    Returns:
        Une chaîne de caractères décrivant le background de la personne.
    """
    logger.info(f"Recherche du background pour : {name}")
    try:
        prompt = get_biography_prompt(name)
        
        # On utilise l'orchestrateur pour bénéficier du routing et du fallback.
        route = TourDeControle.get("biographies")
        
        logger.info(f"-> Appel API (Background) pour '{name}' via {route['provider']} (tâche 'biographies')")
        background = await orchestrator.call_llm(
                task_name="biographies",
                messages=[{"role": "user", "content": prompt}], 
                temperature=0.1
        )
        return f"- {name}: {background.strip()}"

    except Exception as e:
        logger.error(f"Erreur lors de la recherche du background pour {name}: {e}")
        return f"- {name}: Impossible de récupérer le background."
