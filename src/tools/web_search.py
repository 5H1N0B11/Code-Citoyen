#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module de Fact-Checking par recherche Google ciblée.

Ce module effectue des recherches Google ciblées sur les sites de fact-checking
reconnus (AFP Factuel, Les Décodeurs, CheckNews...) pour trouver des sources
réelles à injecter dans les prompts Mistral.

Utilisé par orchestrator.py pour les catégories : FAIT_HISTORIQUE, STATISTIQUE, JURIDIQUE.
"""
import re
import asyncio
import logging
from typing import List, Dict, Any

from .cache_engine import CacheEngine

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

# Initialisation du moteur de cache local SQLite
search_cache = CacheEngine()

# =============================================
# FONCTIONS PRINCIPALES
# =============================================

def _search_sync(query: str, num_results: int) -> List[Dict[str, str]]:
    """Recherche synchrone retournant l'URL et l'extrait (snippet) natif fourni par DuckDuckGo."""
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=num_results))
            if not results:
                return []
            # On retourne directement l'URL et le snippet (body) fourni par le moteur
            return [{"url": r['href'], "snippet": r.get('body', '')} for r in results]
    except Exception as e:
        logger.warning(f"[DDGS] Erreur de recherche : {e}")
        return []


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
    # 1. Vérification du cache en premier lieu (évite l'appel réseau)
    cached_results = search_cache.get_cached_result(affirmation)
    if cached_results is not None:
        logger.info(f"[FactChecker] Cache HIT : Résultats récupérés depuis le cache local.")
        return cached_results

    affirmation_nettoyee = re.sub(r'[«»"""]', '', affirmation).strip()
    
    # On limite à ~80 caractères et on nettoie la ponctuation pour permettre au moteur 
    # de corriger les fautes d'orthographe (ex: "Quentin de Ran" -> "Quentin Deranque")
    query_courte = re.sub(r'[^\w\s]', ' ', affirmation_nettoyee[:80]).strip()
    resultats_web: List[Dict[str, str]] = []

    requete_domaines = " OR ".join([f"site:{dom}" for dom in DOMAINES_FACT_CHECK])
    requete_ciblee = f'{query_courte} {requete_domaines}'

    logger.info(f"[FactChecker] Recherche ciblée pour : '{query_courte}'")

    try:
        results = await asyncio.to_thread(_search_sync, requete_ciblee, MAX_RESULTS_PAR_RECHERCHE)
        for r in results:
            resultats_web.append({"url": r["url"], "source_type": "CIBLÉE", "snippet": r["snippet"]})
        logger.info(f"[FactChecker] {len(results)} URL(s) trouvée(s) (recherche ciblée).")
    except Exception as e:
        logger.warning(f"[FactChecker] Erreur recherche ciblée : {e}")

    # Fallback si aucun résultat ciblé
    if not resultats_web:
        logger.info("[FactChecker] Aucun résultat ciblé. Tentative de recherche large (fallback).")
        # Recherche large avec le mot 'actualité' pour éviter le SEO parasite
        requete_fallback = f'{query_courte} actualité'
        try:
            results_larges = await asyncio.to_thread(_search_sync, requete_fallback, MAX_RESULTS_PAR_RECHERCHE)
            for r in results_larges:
                # Éviter les doublons
                if not any(res["url"] == r["url"] for res in resultats_web):
                    resultats_web.append({"url": r["url"], "source_type": "LARGE", "snippet": r["snippet"]})
            logger.info(f"[FactChecker] {len(results_larges)} URL(s) trouvée(s) (fallback large).")
        except Exception as e:
            logger.warning(f"[FactChecker] Erreur recherche fallback : {e}")

    # 3. Sauvegarde dans le cache (pour 24h) si on a trouvé des résultats
    if resultats_web:
        search_cache.cache_result(affirmation, resultats_web)

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
