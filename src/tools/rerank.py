#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module de RE-RANKING des snippets web (Objectif A2).

La Phase 1.5 (web_search.fetch_fact_check_urls) renvoie jusqu'à ~15 snippets
de qualité mixte. Déversés tels quels dans le prompt de Phase 2, ils noient le
modèle 12B. Ce module re-classe ces snippets par pertinence au claim avec un
modèle LOCAL CPU (TF-IDF + cosinus, scikit-learn), ne garde que le top-k, et
pour les claims STATISTIQUE remonte en priorité les phrases chiffrées.

CHOIX TECHNIQUE : TF-IDF (scikit-learn) plutôt que sentence-transformers/e5.
sentence-transformers n'est PAS installé et l'installer risquerait de toucher
au torch 2.11+cu130 (critique Blackwell). TF-IDF est déjà disponible, CPU-only,
sans téléchargement de modèle, et suffisant pour un re-ranking lexical court.

DÉGRADATION GRACIEUSE : si scikit-learn est absent ou en cas d'erreur, on
renvoie les snippets d'origine tronqués à top_k, sans jamais planter.

CONTRAT : respecte le schéma EXACT de web_search.py — chaque snippet est un
dict {"url": str, "source_type": str, "snippet": str}. La clé texte est
"snippet". Les dicts sont renvoyés tels quels (mêmes clés, même ordre).

Module autonome : NON wiré dans l'orchestrateur (intégration faite ensuite).
"""
import re
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# La clé du texte exploitable dans les dicts de web_search.fetch_fact_check_urls
TEXT_KEY = "snippet"

# Poids du bonus "présence de chiffres" ajouté au cosinus (∈ [0,1]) quand
# prefer_numeric=True. Volontairement modéré pour ne pas écraser la pertinence.
NUMERIC_BONUS = 0.25

# Détection de contenu chiffré : nombres, pourcentages, montants, grandeurs.
_NUMERIC_RE = re.compile(
    r"\d|%|€|\$|£|‰|"
    r"\b(?:milliard|million|millier|pour\s*cent|pourcent|euros?|dollars?)\b",
    re.IGNORECASE,
)

# --- Détection paresseuse de scikit-learn (singleton module-level) ---------
# Pas de modèle lourd à charger pour TF-IDF : on mémorise seulement la
# disponibilité de la lib pour éviter de ré-importer à chaque appel.
_SKLEARN_OK: bool | None = None
_TfidfVectorizer = None
_cosine_similarity = None


def _ensure_sklearn() -> bool:
    """Importe scikit-learn une seule fois. Retourne True si disponible."""
    global _SKLEARN_OK, _TfidfVectorizer, _cosine_similarity
    if _SKLEARN_OK is not None:
        return _SKLEARN_OK
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        _TfidfVectorizer = TfidfVectorizer
        _cosine_similarity = cosine_similarity
        _SKLEARN_OK = True
    except Exception as e:  # pragma: no cover - dépend de l'environnement
        logger.warning("[Rerank] scikit-learn indisponible (%s) — fallback brut.", e)
        _SKLEARN_OK = False
    return _SKLEARN_OK


def _has_numbers(text: str) -> bool:
    """True si le texte contient un signal chiffré/quantitatif."""
    return bool(_NUMERIC_RE.search(text or ""))


def _numeric_bonus(text: str, prefer_numeric: bool) -> float:
    """Bonus de score si prefer_numeric et que le snippet contient un chiffre."""
    if prefer_numeric and _has_numbers(text):
        return NUMERIC_BONUS
    return 0.0


def _relevance_scores(claim: str, texts: List[str]) -> List[float]:
    """
    Cosinus TF-IDF entre le claim et chaque texte de snippet.

    Vectoriseur ajusté à la volée sur (claim + snippets) — pas de modèle
    persistant nécessaire. n-grams de mots (1,2) + accents repliés pour le FR.
    Retourne une liste de scores ∈ [0,1] alignée sur `texts`.
    """
    vectorizer = _TfidfVectorizer(
        lowercase=True,
        strip_accents="unicode",
        ngram_range=(1, 2),
        sublinear_tf=True,
    )
    matrix = vectorizer.fit_transform([claim] + texts)
    sims = _cosine_similarity(matrix[0:1], matrix[1:])[0]
    return [float(s) for s in sims]


def rerank_snippets(
    claim: str,
    snippets: List[Dict[str, Any]],
    top_k: int = 3,
    prefer_numeric: bool = False,
) -> List[Dict[str, Any]]:
    """
    Re-classe les snippets web par pertinence au claim et renvoie le top-k.

    Args:
        claim: L'affirmation à vérifier (texte du claim).
        snippets: Liste de dicts {"url", "source_type", "snippet"} issus de
                  web_search.fetch_fact_check_urls. Les dicts sont renvoyés
                  intacts (mêmes clés, même ordre interne).
        top_k: Nombre maximum de snippets à conserver après re-tri.
        prefer_numeric: Si True (claims STATISTIQUE), bonus aux snippets qui
                        contiennent des chiffres / % / €.

    Returns:
        Au plus `top_k` snippets re-triés par score décroissant. Si l'entrée
        contient moins de `top_k` éléments, tous sont renvoyés (triés). En cas
        d'indisponibilité de scikit-learn ou d'erreur, renvoie les snippets
        d'origine tronqués à top_k (dégradation gracieuse, jamais d'exception).
    """
    if not snippets:
        return []
    if top_k <= 0:
        return []

    # Dégradation gracieuse : pas de lib → on renvoie l'ordre d'origine tronqué.
    if not _ensure_sklearn():
        return snippets[:top_k]

    # Si claim vide, on ne peut pas calculer de pertinence : ordre d'origine.
    if not (claim or "").strip():
        return snippets[:top_k]

    try:
        texts = [str(s.get(TEXT_KEY, "") or "") for s in snippets]

        # Si tous les textes sont vides, TF-IDF échoue (vocab vide) → fallback.
        if not any(t.strip() for t in texts):
            return snippets[:top_k]

        base = _relevance_scores(claim, texts)
        scored = []
        for idx, (snip, text, sim) in enumerate(zip(snippets, texts, base)):
            score = sim + _numeric_bonus(text, prefer_numeric)
            # idx en clé secondaire = tri stable (préserve l'ordre d'origine
            # entre ex æquo, donc CIBLÉE > LARGE > CONTEXTUELLE est conservé).
            scored.append((score, idx, snip))

        scored.sort(key=lambda x: (-x[0], x[1]))
        return [snip for _, _, snip in scored[:top_k]]
    except Exception as e:  # pragma: no cover - robustesse runtime
        logger.warning("[Rerank] Échec re-ranking (%s) — fallback brut.", e)
        return snippets[:top_k]


# =============================================
# TEST STANDALONE
# =============================================
if __name__ == "__main__":
    claim = "La France est la 6e puissance économique mondiale."

    # 5 snippets factices respectant le schéma de web_search.py.
    fake_snippets = [
        {
            "url": "https://www.insee.fr/pib-mondial",
            "source_type": "CIBLÉE",
            "snippet": (
                "Selon le FMI, la France est la 7e puissance économique "
                "mondiale en 2024 avec un PIB de 3 130 milliards de dollars, "
                "derrière l'Inde."
            ),
        },
        {
            "url": "https://www.example.com/recette-tarte",
            "source_type": "LARGE",
            "snippet": (
                "Recette de la tarte aux pommes : préchauffez le four et "
                "étalez la pâte feuilletée."
            ),
        },
        {
            "url": "https://www.worldbank.org/gdp-ranking",
            "source_type": "LARGE",
            "snippet": (
                "Classement des puissances économiques mondiales par PIB : "
                "États-Unis, Chine, Allemagne, Japon, Inde, Royaume-Uni, France."
            ),
        },
        {
            "url": "https://fr.wikipedia.org/wiki/Economie_de_la_France",
            "source_type": "CONTEXTUELLE",
            "snippet": (
                "L'économie de la France est diversifiée et repose sur les "
                "services, l'industrie et l'agriculture."
            ),
        },
        {
            "url": "https://www.oecd.org/france-economy",
            "source_type": "CONTEXTUELLE",
            "snippet": (
                "La France représente environ 2,8 % du PIB mondial et figure "
                "parmi les 10 premières économies de la planète."
            ),
        },
    ]

    print("=== CLAIM ===")
    print(claim)
    print("\n=== ORDRE D'ORIGINE ===")
    for i, s in enumerate(fake_snippets, 1):
        print(f"  {i}. [{s['source_type']}] {s['url']}")

    print("\n=== RE-RANK (top_k=3, prefer_numeric=True) ===")
    ranked = rerank_snippets(claim, fake_snippets, top_k=3, prefer_numeric=True)
    for i, s in enumerate(ranked, 1):
        print(f"  {i}. [{s['source_type']}] {s['url']}")
        print(f"     {s['snippet'][:80]}...")

    print("\n=== RE-RANK (top_k=3, prefer_numeric=False) ===")
    ranked2 = rerank_snippets(claim, fake_snippets, top_k=3, prefer_numeric=False)
    for i, s in enumerate(ranked2, 1):
        print(f"  {i}. [{s['source_type']}] {s['url']}")

    assert len(ranked) == 3, "top_k non respecté"
    assert all(k in ranked[0] for k in ("url", "source_type", "snippet")), "schéma cassé"
    print("\n[OK] Schéma préservé, top_k respecté, dégradation gracieuse en place.")
