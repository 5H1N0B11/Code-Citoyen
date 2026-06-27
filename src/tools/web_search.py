#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module de Fact-Checking par recherche web.

Ce module effectue des recherches via DuckDuckGo pour trouver des sources
pertinentes à injecter dans les prompts d'analyse. Il intègre un cache
et un rate-limiter pour être à la fois performant et respectueux.

Utilisé par orchestrator.py pour les catégories nécessitant des preuves tangibles.
"""
import re
import asyncio
import logging
from typing import List, Dict, Any, Optional
from ddgs import DDGS
import httpx
from bs4 import BeautifulSoup

from .cache_engine import CacheEngine

logger = logging.getLogger(__name__)

# =============================================
# CONFIGURATION
# =============================================
MAX_RESULTS_PER_QUERY = 5
MAX_PARALLEL_QUERIES = 3
MAX_CONTENT_CHARS = 1200  # Limite de caractères extraits par page scrapée

# Domaines tier 0-2 : sources primaires fiables dont on extrait le contenu réel
TIER_0_2_DOMAINS = {
    # Tier 0 — Droit & Institutions
    "legifrance.gouv.fr", "conseil-constitutionnel.fr", "assemblee-nationale.fr",
    "senat.fr", "service-public.fr", "vie-publique.fr", "eur-lex.europa.eu",
    # Tier 1 — Statistiques & Économie
    "insee.fr", "ined.fr", "courdescomptes.fr", "banque-france.fr",
    "oecd.org", "imf.org", "worldbank.org", "inegalites.fr",
    # Tier 2 — Science & Santé
    "ipcc.ch", "inserm.fr", "cnrs.fr", "has-sante.fr", "who.int",
    "thelancet.com", "nejm.org",
}

# Rate limiter pour nos propres recherches web pour éviter les bannissements
SEARCH_MIN_CALL_INTERVAL: float = 2.0  # secondes
_search_rate_lock: asyncio.Lock = asyncio.Lock()
_search_last_call_time: float = 0.0

# Liste de domaines spécialisés par catégorie. Avec ~10 domaines max,
# DDG reste fiable. Avec 40+ OR site:, il dégrade et renvoie du hors-sujet.
DOMAINES_PAR_CATEGORIE = {
    "STATISTIQUE": [
        "insee.fr", "ined.fr", "courdescomptes.fr", "banque-france.fr",
        "oecd.org", "imf.org", "worldbank.org", "inegalites.fr",
        "ec.europa.eu",  # Eurostat
    ],
    "JURIDIQUE": [
        "legifrance.gouv.fr", "conseil-constitutionnel.fr",
        "assemblee-nationale.fr", "senat.fr", "service-public.fr",
        "vie-publique.fr", "eur-lex.europa.eu",
        # Presse pour les affaires en cours
        "lemonde.fr", "lefigaro.fr", "liberation.fr",
    ],
    "FAIT_HISTORIQUE": [
        # Presse pour actualité récente (priorité — c'est là que sortent les
        # arrestations, faits divers, actualités politiques chaudes).
        "lemonde.fr", "lefigaro.fr", "liberation.fr", "lepoint.fr",
        "francetvinfo.fr", "lexpress.fr", "leparisien.fr",
        "afp.com", "factuel.afp.com", "reuters.com",
        # Encyclopédies pour faits historiques anciens
        "fr.wikipedia.org", "universalis.fr",
    ],
    "DOCTRINE": [
        # Textes fondateurs
        "vatican.va", "quran.com", "sunnah.com", "sefaria.org",
        "marxists.org", "encyclopedia.ushmm.org",
        # Encyclopédies (le filet de sécurité)
        "fr.wikipedia.org", "universalis.fr",
    ],
    "CONSENSUS_SCIENCE": [
        "ipcc.ch", "inserm.fr", "cnrs.fr", "has-sante.fr", "who.int",
        "scholar.google.com", "cairn.info", "jstor.org",
        "nature.com", "science.org", "thelancet.com", "nejm.org",
    ],
}

DOMAINES_FACT_CHECK = [
    # --- TIER 0: Sources Primaires (Droit & Institutions) ---
    "legifrance.gouv.fr",       # Le droit français
    "conseil-constitutionnel.fr", # Décisions constitutionnelles
    "assemblee-nationale.fr",   # Travaux parlementaires
    "senat.fr",                 # Travaux parlementaires
    "service-public.fr",        # Informations administratives
    "vie-publique.fr",          # Documentation gouvernementale
    "eur-lex.europa.eu",        # Droit de l'Union Européenne

    # --- TIER 1: Économie, Démographie & Statistiques Publiques ---
    "insee.fr",                 # Statistiques officielles françaises
    "ined.fr",                  # Institut national d'études démographiques (Immigration, natalité)
    "courdescomptes.fr",        # Rapports sur les finances publiques
    "banque-france.fr",         # Données macro-économiques françaises
    "oecd.org",                 # OCDE (Comparaisons fiscales internationales)
    "imf.org",                  # Fonds Monétaire International
    "worldbank.org",            # Banque Mondiale
    "inegalites.fr",            # Observatoire des inégalités

    # --- TIER 2: Science, Santé & Environnement ---
    "ipcc.ch",                  # GIEC (Climat)
    "inserm.fr",                # Recherche médicale et santé publique
    "cnrs.fr",                  # Recherche scientifique globale
    "has-sante.fr",             # Haute Autorité de Santé
    "who.int",                  # Organisation Mondiale de la Santé (OMS)
    "scholar.google.com",       # Moteur de recherche académique
    "cairn.info",               # Portail de publications en sciences humaines
    "jstor.org",                # Archive de journaux académiques
    "nature.com",               # Revue scientifique généraliste de référence
    "science.org",              # Revue scientifique de référence
    "thelancet.com",            # Revue médicale de référence
    "nejm.org",                 # New England Journal of Medicine

    # --- TIER 3: Textes Fondateurs & Histoire (Doctrines) ---
    "vatican.va",               # Catholicisme (Textes et dogmes officiels)
    "quran.com",                # Islam (Coran)
    "sunnah.com",               # Islam (Recueils de Hadiths authentifiés)
    "sefaria.org",              # Judaïsme (Torah, Talmud, textes hébraïques)
    "marxists.org",             # Marxisme / Communisme (Archives historiques mondiales)
    "encyclopedia.ushmm.org",   # Nazisme / Histoire (Musée de l'Holocauste, référence historique)
    
    # --- TIER 3.5: Encyclopédies Universelles (Le filet de sécurité absolu pour TOUTES les autres doctrines) ---
    "fr.wikipedia.org",         # Encyclopédie collaborative (Excellent pour les résumés doctrinaux et historiques)
    "universalis.fr",           # Encyclopédie académique francophone

    # --- TIER 4: Agences de Presse (Faits bruts & International) ---
    "factuel.afp.com",          # AFP Factuel
    "afp.com/fr/factuel",
    "reuters.com",              # Agence Reuters
    
    # --- TIER 5: Cellules de Fact-Checking (à utiliser avec esprit critique) ---
    "lemonde.fr/les-decodeurs", # Le Monde Décodeurs
    "liberation.fr/checknews",  # Libération CheckNews
    "francetvinfo.fr",          # France Info (pour le contexte)
    "rts.ch/info/verification", # RTS (Suisse)

    # --- TIER 6: Presse généraliste (contexte, mais avec ligne éditoriale) ---
    "lefigaro.fr",
    "lepoint.fr",
    "lemonde.fr",
    "liberation.fr",
]

# Catégories pour lesquelles la recherche Google est activée
CATEGORIES_AVEC_RECHERCHE = {"FAIT_HISTORIQUE", "STATISTIQUE", "JURIDIQUE", "DOCTRINE", "CONSENSUS_SCIENCE"}

# Initialisation du moteur de cache local SQLite
search_cache = CacheEngine()

# =============================================
# FONCTIONS PRINCIPALES
# =============================================

async def _search_ddgs_async(query: str, num_results: int) -> List[Dict[str, str]]:
    """Recherche synchrone retournant l'URL et l'extrait (snippet) natif fourni par DuckDuckGo."""
    try:
        # ddgs.text est synchrone, on l'exécute dans un thread pour ne pas bloquer l'event loop
        def sync_search():
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=num_results))
        
        results = await asyncio.to_thread(sync_search)
        return [{"url": r['href'], "snippet": r.get('body', '')} for r in results if r]
    except Exception as e:
        logger.warning(f"[DDGS] Erreur de recherche : {e}")
        return []


async def _fetch_page_content(url: str, timeout: int = 5) -> str:
    """
    Extrait le texte principal d'une page web (tier 0-2 uniquement).
    Retourne une chaîne vide en cas d'erreur ou si le contenu est inutilisable.
    """
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.5,en;q=0.3",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                return ""
            content_type = response.headers.get("content-type", "")
            if "html" not in content_type:
                return ""

            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
                tag.decompose()

            # Priorité : balises sémantiques de contenu principal
            main = (
                soup.find("article")
                or soup.find("main")
                or soup.find(id=re.compile(r"content|article|main", re.I))
                or soup.find(class_=re.compile(r"content|article|main", re.I))
                or soup.body
            )
            if not main:
                return ""

            text = " ".join(main.get_text(separator=" ").split())
            return text[:MAX_CONTENT_CHARS]
    except Exception as e:
        logger.debug(f"[Scraper] Impossible de lire '{url[:60]}': {e}")
        return ""


async def _enrich_with_page_content(results: List[Dict[str, str]]) -> None:
    """
    Pour les sources tier 0-2, remplace le snippet DuckDuckGo par le contenu
    réel de la page (extraction HTML). Modifie la liste en place.
    Timeout global de 12s pour ne pas bloquer le pipeline.
    """
    candidates = [
        r for r in results
        if any(domain in r.get("url", "") for domain in TIER_0_2_DOMAINS)
    ]
    if not candidates:
        return

    async def _enrich_one(result: Dict[str, str]) -> None:
        content = await _fetch_page_content(result["url"])
        if content:
            result["snippet"] = content
            logger.info(f"[Scraper] Contenu réel extrait : {result['url'][:70]} ({len(content)} chars)")
        else:
            logger.debug(f"[Scraper] Contenu non récupéré : {result['url'][:70]}")

    try:
        await asyncio.wait_for(
            asyncio.gather(*[_enrich_one(r) for r in candidates], return_exceptions=True),
            timeout=12.0,
        )
    except asyncio.TimeoutError:
        logger.warning("[Scraper] Timeout global atteint — scraping partiel.")


def _build_search_queries(base_query: str, category: Optional[str]) -> List[str]:
    """
    Génère jusqu'à 3 variantes de requêtes complémentaires pour maximiser le recall.
    - Q1 : ciblée sur les sources fiables de la catégorie (opérateurs site:)
    - Q2 : large, sans restriction de domaine
    - Q3 : contextuelle (académique pour science/stats/doctrine, sinon mots-clés métier)
    """
    queries = []

    # Q1 — Ciblée
    domaines = DOMAINES_PAR_CATEGORIE.get(category, [])
    if domaines:
        site_filter = " OR ".join(f"site:{d}" for d in domaines[:8])
        queries.append(f"{base_query} ({site_filter})")
    else:
        queries.append(base_query)

    # Q2 — Large
    queries.append(base_query)

    # Q3 — Contextuelle / Académique
    if category in {"CONSENSUS_SCIENCE", "STATISTIQUE", "DOCTRINE"}:
        queries.append(
            f"{base_query} site:scholar.google.com OR site:cairn.info OR site:jstor.org"
        )
    else:
        kw = {
            "FAIT_HISTORIQUE": "histoire archive encyclopédie",
            "JURIDIQUE":       "loi droit France légal",
        }.get(category, "actualité vérification source")
        queries.append(f"{base_query} {kw}")

    # Dédupliquer en préservant l'ordre
    seen: set = set()
    unique: List[str] = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique.append(q)
    return unique


async def fetch_fact_check_urls(affirmation: str, search_query: Optional[str] = None, category: Optional[str] = None, langue: str = "fr") -> List[Dict[str, str]]:
    """
    Recherche asynchrone et parallèle de sources fact-checking pour une affirmation.

    Stratégie :
    1. Génère 3 requêtes complémentaires via _build_search_queries().
    2. Lance les 3 recherches DDGS en parallèle (asyncio.gather).
    3. Fusionne et déduplique les résultats.
    4. Enrichit les sources tier 0-2 avec le contenu réel des pages.
    5. Met en cache pour 24h.

    Args:
        affirmation: L'affirmation à vérifier.
        search_query: La requête de base (mots-clés). Si absent, dérivée de l'affirmation.
        category: La catégorie pour orienter les domaines de recherche.
        langue: La langue de recherche (défaut: 'fr').

    Returns:
        Liste de dicts {"url": str, "source_type": str, "snippet": str}
    """
    global _search_last_call_time

    # 1. Cache (évite l'appel réseau)
    cached_results = search_cache.get_cached_result(affirmation)
    if cached_results is not None:
        logger.info("[FactChecker] Cache HIT : résultats depuis le cache local.")
        return cached_results

    # 2. Requête de base
    if not search_query:
        affirmation_nettoyee = re.sub(r'[«»"""]', '', affirmation).strip()
        search_query = re.sub(r'[^\w\s]', ' ', affirmation_nettoyee[:80]).strip()

    # 3. Génération des variantes de requêtes
    queries = _build_search_queries(search_query, category)
    logger.info(f"[FactChecker] {len(queries)} requêtes parallèles pour : '{search_query[:60]}'")

    resultats_web: List[Dict[str, str]] = []

    # 4. Rate limiting (une fois par affirmation, pas par requête)
    async with _search_rate_lock:
        now = asyncio.get_running_loop().time()
        elapsed = now - _search_last_call_time
        if elapsed < SEARCH_MIN_CALL_INTERVAL:
            logger.debug(f"[WebSearch RateLimiter] Attente {SEARCH_MIN_CALL_INTERVAL - elapsed:.2f}s.")
            await asyncio.sleep(SEARCH_MIN_CALL_INTERVAL - elapsed)
        _search_last_call_time = asyncio.get_running_loop().time()

        # 5. Recherches parallèles
        labels = ["CIBLÉE", "LARGE", "CONTEXTUELLE"]
        raw_results = await asyncio.gather(
            *[_search_ddgs_async(q, MAX_RESULTS_PER_QUERY) for q in queries],
            return_exceptions=True
        )

    # 6. Fusion + déduplication (ordre : CIBLÉE > LARGE > CONTEXTUELLE)
    seen_urls: set = set()
    for i, results in enumerate(raw_results):
        if isinstance(results, Exception):
            logger.warning(f"[FactChecker] Erreur requête {i + 1} : {results}")
            continue
        label = labels[i] if i < len(labels) else "LARGE"
        for r in results:
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                resultats_web.append({
                    "url": url,
                    "source_type": label,
                    "snippet": r.get("snippet", "")
                })

    logger.info(
        f"[FactChecker] {len(resultats_web)} résultats uniques "
        f"({len(queries)} requêtes × {MAX_RESULTS_PER_QUERY} max)."
    )

    # 7. Enrichissement : contenu réel pour les sources tier 0-2
    if resultats_web:
        await _enrich_with_page_content(resultats_web)
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
        "\nINSTRUCTION : Lisez attentivement les EXTRAITS DU CONTENU sous chaque URL et basez votre "
        "verdict sur les FAITS qu'ils contiennent. Citez la source. N'inventez aucun chiffre ni fait "
        "absent des extraits.\n\n"
        "HIÉRARCHIE DES SOURCES (préférez la plus fiable disponible, mais TOUTES sont exploitables) :\n"
        "  • NIVEAU 1 — Sources primaires (.gouv.fr, insee.fr, legifrance.fr, rapports officiels) et "
        "publications académiques : leurs données sont des faits.\n"
        "  • NIVEAU 2 — Agences de presse (AFP, Reuters) : fiables pour les faits et événements récents.\n"
        "  • NIVEAU 3 — Presse générale et cellules de fact-checking : utiles, surtout pour l'actualité "
        "récente ; si possible remontez à la source primaire qu'elles citent, mais elles restent une preuve valable.\n\n"
        "RÈGLE DE VERDICT (applique-la strictement, dans cet ordre) :\n"
        "  1. Les extraits CONFIRMENT l'affirmation (mêmes faits, chiffres concordants même approximatifs) "
        "→ verdict VRAI.\n"
        "  2. Les extraits CONTREDISENT l'affirmation → verdict FAUX.\n"
        "  3. Le fait/chiffre est globalement exact mais imprécis, arrondi, exagéré ou sorti de son contexte "
        "→ IMPRECIS ou TROMPEUR (PAS faux).\n"
        "  4. NON_VERIFIABLE est réservé au SEUL cas où AUCUN extrait ne traite du sujet. "
        "Ne l'utilise PAS quand des extraits confirment ou contredisent : tu DOIS trancher.\n"
        "  5. Un fait historique ou un chiffre BIEN ÉTABLI et confirmé par les extraits est VRAI, même si "
        "les sources sont journalistiques. Ne sois pas sceptique par réflexe : sois EXACT. "
        "Confirmer un fait vrai est aussi important que démentir un fait faux."
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
