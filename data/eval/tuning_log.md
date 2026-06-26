# Journal de tuning nocturne

Format : `## Cycle N — HH:MM — vidéo` puis action / score avant→après / décision.

---

## Cycle 0 — kickoff — F-hsYpOya0M (Ruffin)
- Branche `bot-tuning-nuit` créée, scaffolding `data/eval/` en place.
- Serveur local UP (mode local, mistral-nemo:12b), vidéo Ruffin déjà analysée (24 analyses / 479 segments).
- Constat de départ (10 premiers verdicts) : sur-étiquetage sophismes (6/10 BIAIS), factuel vérifiable → NON_VERIFIABLE, sélection de fragments/questions.
- Action : extraction transcript+sortie bot ; dispatch agent étalonneur pour construire `gold/F-hsYpOya0M.json`.
- Prochain : évaluer le bot vs étalon avec `run_judgment_eval.py`, puis appliquer levier #1 (filtre sélection) ou #2 (garde-fou) selon le rapport.
