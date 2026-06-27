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

## QLoRA v1 — ÉCHEC (test held-out)
Entraîné sur 8 vidéos (203 ex, 4 epochs, token-acc 0.95 = surappris). 
- Sur vidéos VUES (contaminé) : Leclerc 74/83/50, Zemmour 74/70/40, MAIS Tanguy s'effondre 36/46/10.
- **HELD-OUT Bardella (jamais vu)** : LoRA **56/50/0** vs nemo+contraint **64/48/20**. → LoRA PIRE en cat et biais (détruit), verd +2 (bruit). NE GÉNÉRALISE PAS.
- Causes : surapprentissage (4 epochs/200 ex) + format JSON-combiné qui n'apprend pas la classification + dérive "tout est nuance statistique" qui casse la détection de sophismes.
- DÉCISION : revenir à nemo+nommage contraint (config de prod). Modèle citoyen v1 ABANDONNÉ.

## QLoRA v2 — BLOQUÉ (VRAM)
Dataset v2 prêt (406 ex 2-formats, Bardella held-out), script corrigé (paged_adamw_8bit, ctx 768, 2 epochs, dropout 0.1).
MAIS : un runner Ollama est resté coincé en VRAM (~7,6 Go, état non-libérable), `ollama stop` ne le décharge plus,
et pas de sudo pour `systemctl restart ollama` ni de droit de kill (process user `ollama`). Le 12B 4-bit ne tient
plus en VRAM (16 Go partagés avec le bureau) → entraînement v2 impossible ce tour.
➡️ ACTION REQUISE (Fabien) : `sudo systemctl restart ollama` pour libérer le GPU. Ensuite v2 relançable :
   `EPOCHS=2 DROPOUT=0.1 TORCHDYNAMO_DISABLE=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True python data/eval/qlora_train.py`
   puis convert→ollama create→eval held-out Bardella (baseline à battre : 64/48/20).

## ÉTAT DÉPLOYÉ (config prouvée, bot fonctionnel)
mistral-nemo:12b + filtre sélection + nommage contraint. Biais 65% (objectif atteint). Cat ~60, Verd ~53 (non atteints).
Le LoRA n'est PAS déployé (v1 échec held-out, v2 bloqué VRAM).
