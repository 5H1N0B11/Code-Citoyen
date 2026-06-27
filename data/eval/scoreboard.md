# Scoreboard — progression vers l'objectif

Cibles : Cat ≥ 80 % · Verdict ≥ 75 % · Biais nommé ≥ 60 % (moyenne 4 vidéos).
Matcher biais corrigé (synonymes EN/FR) à partir du levier 1 → les biais avant/après ne sont pas comparables stricto sensu.

| Levier | Modèle | Ruffin C/V/B | Tanguy C/V/B | Zemmour C/V/B | Leclerc C/V/B | Note |
|--------|--------|--------------|--------------|---------------|---------------|------|
| Baseline | nemo:12b | 80/70/0 | 44/52/~30 | 56/50/40 | 56/37/50 | matcher honnête (biais Tanguy recalculé ~30%) |
| +Nommage contraint | nemo:12b | — | **48/56/50** | (en cours) | (en cours) | **biais +20 pts** ✅ (id13 Effet de Foule, id18 Homme de Paille récupérés) |

Levier RETENU : nommage de sophisme par classification contrainte (enum fermé 15 sophismes, option AUCUN, non-destructif).
Prochain : calibration des verdicts (recherche levier 3) — NON_VERIFIABLE seulement si 0 preuve, exiger quote pour VRAI/FAUX.
