#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module de Fact-Checking par recherche Google ciblée.

Ce module effectue des recherches Google ciblées sur les sites de fact-checking
reconnus (AFP Factuel, Les Décodeurs, CheckNews...) pour trouver des sources
réelles à injecter dans les prompts Mistral.

Utilisé par orchestrator.py pour les catégories : FAIT_HISTORIQUE, STATISTIQUE, JURIDIQUE.
"""
import trafilatura
import re
import asyncio
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# =============================================
# CONFIGURATION
# =============================================
MAX_RESULTS_PAR_RECHERCHE = 3

DOMAINES_FACT_CHECK = [
    "lemonde.fr/les-decodeurs",
    "afp.com/fr/factuel",
    "liberation.fr/checknews",
    "rts.ch/info/verification",
    "factuel.afp.com",
    "lepoint.fr",
    "lefigaro.fr",
    "insee.fr",
    "vie-publique.fr",
    "legifrance.gouv.fr",
]

# Catégories pour lesquelles la recherche Google est activée
CATEGORIES_AVEC_RECHERCHE = {"FAIT_HISTORIQUE", "STATISTIQUE", "JURIDIQUE"}


# =============================================
# FONCTIONS PRINCIPALES
# =============================================

# def _search_sync(query: str, num_results: int, lang: str, sleep_interval: int) -> List[str]:
#     """
#     Wrapper synchrone pour googlesearch.search().
#     Isolé pour être exécuté dans un thread via asyncio.to_thread().
#     """
#     from googlesearch import search
#     return list(search(query, num_results=num_results, lang=lang, sleep_interval=sleep_interval))
def _search_sync(query: str, num_results: int) -> List[str]:
    from ddgs import DDGS
    with DDGS() as ddgs:
        results = ddgs.text(query, max_results=num_results)
        return [r['href'] for r in results] if results else []

async def fetch_article_summary(url: str) -> str:
    """Télécharge et extrait un résumé du vrai texte d'une page (sans les menus)."""
    try:
        def _extract():
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                text = trafilatura.extract(downloaded)
                if text:
                    # On garde 1000 caractères max pour ne pas exploser le contexte Mistral
                    return text[:1000] + "..."
            return "Contenu illisible ou bloqué."
        
        return await asyncio.to_thread(_extract)
    except Exception as e:
        logger.warning(f"[Scraper] Erreur sur {url} : {e}")
        return "Erreur de lecture."


async def fetch_fact_check_urls(affirmation: str, langue: str = "fr") -> List[Dict[str, str]]:
    """
    Recherche asynchrone de sources fact-checking pour une affirmation.

    Stratégie :
    1. Recherche ciblée sur les sites de fact-checking (opérateur site:)
    2. Fallback : recherche large avec le mot-clé "vérification"

    Args:
        affirmation: L'affirmation à vérifier.
        langue: La langue de recherche (défaut: 'fr').

    Returns:
        Liste de dicts {"url": str, "source_type": "CIBLÉE" | "LARGE"}
    """
    affirmation_nettoyee = re.sub(r'[«»"""]', '', affirmation).strip()
    resultats_web: List[Dict[str, str]] = []

    requete_domaines = " OR ".join([f"site:{dom}" for dom in DOMAINES_FACT_CHECK])
    requete_ciblee = f'"{affirmation_nettoyee}" {requete_domaines}'

    logger.info(f"[FactChecker] Recherche ciblée pour : '{affirmation_nettoyee[:60]}...'")

    try:
        urls = await asyncio.to_thread(
            _search_sync,
            requete_ciblee,
            MAX_RESULTS_PAR_RECHERCHE
            #, langue,
            # 2  # sleep_interval
        )
        for url in urls:
            extrait = await fetch_article_summary(url)
            resultats_web.append({"url": url, "source_type": "CIBLÉE", "snippet": extrait})
        logger.info(f"[FactChecker] {len(urls)} URL(s) trouvée(s) (recherche ciblée).")
    except Exception as e:
        logger.warning(f"[FactChecker] Erreur recherche ciblée : {e}")

    # Fallback si aucun résultat ciblé
    if not resultats_web:
        logger.info("[FactChecker] Aucun résultat ciblé. Tentative de recherche large (fallback).")
        requete_fallback = f'{affirmation_nettoyee} vérification fact-check'
        try:
            urls_larges = await asyncio.to_thread(
                _search_sync,
                requete_fallback,
                MAX_RESULTS_PAR_RECHERCHE
                #, langue,
                # 2
            )
            for url in urls_larges:
                if not any(r["url"] == url for r in resultats_web):
                    extrait = await fetch_article_summary(url)
                    resultats_web.append({"url": url, "source_type": "LARGE", "snippet": extrait})
            logger.info(f"[FactChecker] {len(urls_larges)} URL(s) trouvée(s) (fallback large).")
        except Exception as e:
            logger.warning(f"[FactChecker] Erreur recherche fallback : {e}")

    return resultats_web


def format_urls_for_prompt(urls: List[Dict[str, str]]) -> str:
    """Formate la liste d'URLs et leurs extraits de texte pour Mistral."""
    if not urls:
        return ""

    lines = ["SOURCES TROUVÉES PAR RECHERCHE WEB (à utiliser comme contexte prioritaire) :"]
    for i, item in enumerate(urls, 1):
        tag = f"[{item['source_type']}]" if item.get("source_type") else ""
        lines.append(f"  {i}. {tag} {item['url']}")
        
        # On ajoute l'extrait de texte si on a réussi à l'aspirer
        if item.get("snippet") and item["snippet"] != "Erreur de lecture.":
            extrait_propre = item["snippet"].replace('\n', ' ')
            lines.append(f"     -> EXTRAIT DU CONTENU : \"{extrait_propre}\"")

    lines.append(
        "\nINSTRUCTION : Lisez attentivement les EXTRAITS DU CONTENU sous chaque URL. "
        "Appuyez-vous sur ces textes pour confirmer ou infirmer l'affirmation. "
        "Citez la source explicitement. Ne devinez pas, utilisez uniquement les faits présents dans ces extraits."
    )
    return "\n".join(lines)


# =============================================
# TEST STANDALONE
# =============================================
if __name__ == "__main__":
    import asyncio

    async def _test():
        affirmations_test = [
            "Le chômage a baissé de 10% depuis 2022.",
            "L'entreprise Total a investi 5 milliards d'euros en France l'année dernière."
        ]
        for aff in affirmations_test:
            print(f"\n🔍 Affirmation : {aff}")
            urls = await fetch_fact_check_urls(aff)
            print(format_urls_for_prompt(urls))

    asyncio.run(_test())
