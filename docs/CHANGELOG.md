# Changelog

## [2026-03-15] - Optimisations Anti-429 & Statut Opinion

### Ajouté
- **Statut Opinion Pédagogique** : Les jugements de valeur ou injonctions ("Il faut faire X") reçoivent désormais obligatoirement le verdict `OPINION` avec une explication pédagogique.
- **Pipeline MLOps (Préparation)** : Définition de la Phase 4 pour le traitement de chaînes YouTube en masse et l'évaluation "LLM-as-a-Judge".

### Modifié
- **Anti-Rate Limit (Groq)** : Séparation des contextes dans `AnalysisOrchestrator`. Le prompt de classification reçoit un contexte allégé (sans l'historique DDGS) pour préserver les quotas TPM.
- **Filtre Anti-Doublon** : Réduction de la mémoire glissante de 20 à 5 phrases dans `stream_engine.py` pour économiser les tokens.
- **Interface Web Temps Réel** : Les analyses "futures" (en avance sur le lecteur) sont affichées en grisé au lieu d'être masquées (meilleur feedback UX).

### Corrigé
- **Crash Parser JSON** : Ajout d'un fallback `ast.literal_eval` dans `_parse_llm_json` pour récupérer silencieusement les fausses réponses JSON (dictionnaires Python) hallucinées par Mistral.
- **Recherche Web DDGS** : Mise à jour vers la librairie `ddgs` et suppression des guillemets stricts dans la requête pour débloquer les recherches aveugles.

## [2026-03-14] - Architecture V2 & Radar Contextuel

### Ajouté
- **Moteur Radar** : Implémentation d'une boucle asynchrone (`stream_engine.py`) qui maintient un Résumé Roulant pour mettre à jour le sujet du débat en direct sans exploser les limites d'API Groq.
- **Correction ASR Intelligente** : Groq corrige les bégaiements, les erreurs phonétiques ("loup" -> "Louvre") et résout les pronoms avant l'envoi aux moteurs de recherche.
- **Interface Web V2** : Ajout de la pastille de contexte dynamique (Sujet/Sous-Sujet) et des séparateurs visuels de changement de sujet dans le fil d'analyse.
- **Refonte Modulaire** : Réorganisation propre du code source (`src/web`, `src/cli`, `src/core`, `src/tools`, `src/prompts`, `src/ingestion`).
- **Unification** : L'interface CLI (`console_app.py`) utilise désormais le même moteur hybride (Groq/Mistral) que le serveur Web.

## [2026-01-04] - Documentation & Architecture Update

### Documentation
- **Révision complète** : Mise à jour majeure de `README.md`, `PLAN_MILESTONES.md` et `COMMANDS.md`.
- **Alignement Architecture** : La documentation reflète désormais l'architecture active "Single-Phase Analysis" (Correction + Analyse via un prompt unique).
- **Guidelines** : Création de `docs/CONTRIBUTING.md` pour définir les standards de contribution et d'architecture.
- **Legacy** : Identification claire des modules obsolètes (`orchestrator.py`) dans la documentation.

## [Unreleased] - 2025-12-13

### Ajouté
- **Ingestion VTT v3.1** :
    - Amélioration de la logique de fusion des sous-titres : priorité à la continuité du texte sur l'écart temporel pour éviter les doublons lors des mises à jour de segments.
    - Ajout d'un fallback pour la détection des locuteurs : si les balises `<v>` sont absentes, le parser cherche le format `NOM: Paroles`.
- **Live Fact Checker** :
    - Ajout d'un `.strip()` lors de l'ajout au buffer de transcription pour éviter l'accumulation d'espaces.

### Modifié
- **Documentation** : Mise à jour du README et de la Roadmap pour refléter les améliorations du parser VTT et la gestion des horodatages.