# Changelog

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