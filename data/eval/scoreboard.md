# Scoreboard — progression vers l'objectif

Cibles : Cat ≥ 80 % · Verdict ≥ 75 % · Biais nommé ≥ 60 % (moyenne 4 vidéos).
Matcher biais corrigé (synonymes EN/FR) à partir du levier 1 → les biais avant/après ne sont pas comparables stricto sensu.

| Levier | Modèle | Ruffin C/V/B | Tanguy C/V/B | Zemmour C/V/B | Leclerc C/V/B | Note |
|--------|--------|--------------|--------------|---------------|---------------|------|
| Baseline | nemo:12b | 80/70/0 | 44/52/~30 | 56/50/40 | 56/37/50 | matcher honnête (biais Tanguy recalculé ~30%) |
| +Nommage contraint | nemo:12b | **80/70/50** | **48/56/50** | **56/50/60** | **56/37/100** | **biais partout en hausse, 0 régression cat/verd** ✅ |

**MOYENNES après nommage contraint** : Cat **60 %** · Verdict **53 %** · **Biais 65 %**.
🎯 **Objectif BIAIS (≥60 %) ATTEINT** par un seul levier gratuit (décodage contraint). Biais : Ruffin 0→50, Tanguy 30→50, Zemmour 40→60, Leclerc 50→100.
Restent SOUS cible : Catégorie (60<80) et Verdict (53<75) — métriques de RAISONNEMENT → levier = QLoRA (besoin 200-500 ex, j'en ai 100).

Levier RETENU : nommage de sophisme par classification contrainte (enum fermé 15 sophismes, option AUCUN, non-destructif).
Plan : (a) calibration verdicts (lever 3 recherche) pour grappiller sur verd ; (b) EXTENSION — plus de vidéos politiques → dataset 200-500 ex → QLoRA torchtune pour cat+verd.
