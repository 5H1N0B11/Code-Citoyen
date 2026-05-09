"""
Phase 1.5D — Décomposition conceptuelle doctrinale.

Objectif : avant de vérifier si un qualificatif s'applique à une doctrine,
décomposer ce qualificatif en conditions nécessaires et suffisantes,
dérivées du sens ordinaire du mot (sans référence à des auteurs),
et identifier les textes sources fondateurs majoritaires à consulter.

Fonctionne pour toute doctrine (religieuse, politique, philosophique)
et pour tout qualificatif (totalitaire, pacifique, liberticide, raciste…).
"""

from typing import Dict, Optional

DOCTRINE_DECOMPOSITION_PROMPT = """
RÉPONSE EN FRANÇAIS. Tu es un analyste conceptuel rigoureux.

On te donne une affirmation qui applique un QUALIFICATIF à une DOCTRINE.
Ta mission : préparer la vérification factuelle en deux étapes.

ÉTAPE 1 — EXTRACTION
- Identifie le QUALIFICATIF (l'adjectif ou la qualification appliquée à la doctrine).
- Identifie la DOCTRINE ciblée (religion, idéologie, philosophie, mouvement).

ÉTAPE 2 — DÉCOMPOSITION DU QUALIFICATIF
Décompose le qualificatif en 4 à 5 conditions nécessaires et suffisantes.
RÈGLES ABSOLUES :
- Déduis les conditions du sens ORDINAIRE du mot. Aucune référence à des auteurs.
- Formule chaque condition comme une question binaire (réponse OUI ou NON) vérifiable dans un texte.
- Les conditions doivent être indépendantes les unes des autres.
- Vise les critères structurels de la doctrine (ses règles, ses peines, ses textes) — pas les comportements individuels des pratiquants.

Exemples de formulation correcte :
  "La doctrine interdit-elle de la quitter sans sanction physique ou sociale ?"
  "La doctrine revendique-t-elle une autorité supérieure à la loi civile ?"
  "La doctrine prescrit-elle des peines corporelles pour certains comportements ?"
  "La doctrine reconnaît-elle la liberté de conscience individuelle ?"
  "La doctrine traite-t-elle différemment ses membres selon leur sexe ou leur origine ?"

ÉTAPE 3 — TEXTES SOURCES MAJORITAIRES
Liste les 3 à 5 textes FONDATEURS les plus utilisés par la majorité des pratiquants
de la doctrine (courant majoritaire, pas les versions réformées ou marginales).
Format : "Titre (type)" — ex: "Coran (texte révélé)", "Hadith Bukhari (traditions prophétiques canoniques)"

RETOURNE UNIQUEMENT ce JSON valide (aucun texte avant ou après) :
{
  "qualificatif": "le mot ou la qualification extraite",
  "doctrine": "la doctrine ou religion ciblée",
  "conditions": [
    "Condition 1 formulée comme question ?",
    "Condition 2 formulée comme question ?",
    "Condition 3 formulée comme question ?",
    "Condition 4 formulée comme question ?"
  ],
  "sources_primaires": [
    "Texte 1 (type)",
    "Texte 2 (type)",
    "Texte 3 (type)"
  ]
}
"""


def get_doctrine_decomposition_prompt(
    affirmation: str,
    main_topic: Optional[str] = None,
    sub_topic: Optional[str] = None,
) -> str:
    context = ""
    if main_topic:
        context += f"\nContexte : sujet principal = '{main_topic}'."
    if sub_topic:
        context += f" Sous-sujet = '{sub_topic}'."
    return f"{DOCTRINE_DECOMPOSITION_PROMPT}{context}\n\nAFFIRMATION À ANALYSER : \"{affirmation}\""


def build_doctrine_analysis_prompt(decomposition: Dict) -> str:
    qualificatif = decomposition.get("qualificatif", "le terme employé")
    doctrine = decomposition.get("doctrine", "la doctrine citée")
    conditions = decomposition.get("conditions", [])
    sources = decomposition.get("sources_primaires", [])

    sources_str = ", ".join(sources) if sources else "textes fondateurs de la doctrine"
    conditions_block = "\n".join(
        f"{i+1}. {c}" for i, c in enumerate(conditions)
    ) if conditions else "(aucune condition extraite — analyse libre)"

    return (
        f"Une décomposition analytique a été préparée pour cette affirmation.\n\n"
        f"QUALIFICATIF APPLIQUÉ : \"{qualificatif}\"\n"
        f"DOCTRINE CIBLÉE : \"{doctrine}\"\n\n"
        f"TEXTES SOURCES À CONSULTER (courant majoritaire) :\n{sources_str}\n\n"
        f"CONDITIONS À VÉRIFIER (dérivées du sens ordinaire de \"{qualificatif}\") :\n"
        f"{conditions_block}\n\n"
        f"INSTRUCTIONS D'ANALYSE :\n"
        f"Pour chaque condition, répondez OUI ou NON.\n"
        f"SOURCES AUTORISÉES (par ordre de priorité) :\n"
        f"1. Les extraits fournis dans ce contexte (sources web récupérées).\n"
        f"2. VOTRE CONNAISSANCE DES TEXTES CANONIQUES : Les textes fondateurs des grandes doctrines "
        f"(Coran, Hadith Bukhari/Muslim/Tirmidhi, Bible, Torah, Talmud, textes marxistes-léninistes, "
        f"Mein Kampf, etc.) sont dans vos données d'entraînement. Si les sources web ne couvrent pas "
        f"un aspect, UTILISEZ votre connaissance directe de ces textes et citez le verset, "
        f"le hadith ou le paragraphe précis (ex: 'Hadith Bukhari 6922 : من بدّل دينه فاقتلوه').\n"
        f"INTERDIT : Répondre NON_VÉRIFIABLE si vous connaissez la réponse dans les textes canoniques.\n\n"
        f"RÈGLE ANTI-RELATIVISME : Si une règle est dans les textes canoniques majoritaires, "
        f"elle est PRÉSENTE — même si une minorité de pratiquants la rejette. "
        f"Ne diluez pas une règle structurelle par des contre-exemples minoritaires.\n\n"
        f"RÈGLES DE VERDICT FINAL :\n"
        f"- ADMIS : majorité des conditions (≥3) confirmées par les textes fondateurs\n"
        f"- CONTESTÉ : résultat mixte, ou présent dans certains courants majeurs mais pas tous\n"
        f"- INFONDÉ : majorité des conditions (≥3) absentes ou contredites par les textes\n\n"
        f"FORMAT DE RÉPONSE :\n"
        f"{{ \"verdict\": \"[ADMIS/CONTESTÉ/INFONDÉ]\", \"score\": \"X%\",\n"
        f"  \"verification_conditions\": [\n"
        f"    {{\"condition\": \"...\", \"reponse\": \"OUI/NON\", \"citation\": \"...\", \"source\": \"...\"}}\n"
        f"  ],\n"
        f"  \"explanation_long\": \"[synthèse condition par condition + verdict motivé]\",\n"
        f"  \"explanation_short\": \"[1-2 phrases résumant le verdict]\",\n"
        f"  \"biais_detecte\": null, \"biais_definition\": null, \"biais_source\": null }}"
    )
