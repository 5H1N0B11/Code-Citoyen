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

## QLoRA v3 (568 ex, liger, 2 epochs, dropout 0.1) — RÉSULTAT HELD-OUT NUANCÉ
Entraîné sur 11 vidéos (Bardella exclu), token-acc 0.84 (vs 0.95 v1 = MOINS de mémorisation).
**HELD-OUT Bardella** (jamais vu) :
| modèle | cat | verd | biais |
|--------|-----|------|-------|
| nemo+contraint | 64 | 48 | 20 |
| LoRA v1 | 56 | 50 | 0 |
| **LoRA v3** | 64 | **60** | 0 |
✅ **LE VERDICT GÉNÉRALISE** : +12 pts held-out (48→60), PAS de mémorisation → la thèse "plus de données" est VALIDÉE.
⚠️ Biais 0 : le LoRA détecte les sophismes (verdict BIAIS ok) mais en oublie le NOMMAGE contraint (catastrophic forgetting) → noms tous faux.
→ v3 échange biais contre verdict. Pas strictement > nemo+contraint.

## Piste v4 (best of both, à tester) : ajouter les exemples de NOMMAGE CONTRAINT au dataset
(claim LOGIQUE → sophisme exact) pour qu'UN seul modèle fasse verdict ET biais. Nécessite 1 entraînement GPU-exclusif de plus (pause cashFlow ~15 min).

## ÉTAT DÉPLOYÉ
Choix à faire : nemo+contraint (biais 20, verd 48) OU LoRA v3 (biais 0, verd 60). Hybride (2 modèles) impossible en coexistence avec cashFlow (VRAM). Défaut sûr = nemo+contraint (a la détection de biais).


## QLoRA v4 (636 ex, +nommage sophisme) — MEILLEUR MODÈLE, held-out Bardella
| modèle | cat | verd | biais |
|--------|-----|------|-------|
| nemo+contraint | 64 | 48 | 20 |
| v3 | 64 | 60 | 0 |
| **v4** | **72** | **66** | **20** |
v4 bat nemo+contraint sur LES 3 (held-out). Nommage récupéré. DÉPLOYÉ.
Cibles restantes : cat 80(à72), verd 75(à66), biais 60(à20). Continuer : PLUS DE DONNÉES + sophismes rares. GPU libre week-end.


## COMPARAISON ROBUSTE v4 vs v5 (2 held-out : Bardella + Chenu)
| modèle | Bardella | Chenu | MOYENNE |
|--------|----------|-------|---------|
| v4 | 64/62/40 | 80/70/67 | **72 / 66 / 53** |
| v5 | 68/50/20 | 76/74/100 | **72 / 62 / 60** |
LEÇON : v4≈v5 (la "régression v5" était du BRUIT mono-vidéo). VARIANCE ÉNORME entre runs (v4 Bardella : 72/66/20 puis 64/62/40) et entre vidéos (Chenu >> Bardella). → conclure SEULEMENT sur moyennes multi-vidéos/runs.
Moyenne ~72/64/57 vs cible 80/75/60. Biais ~atteint. Cat/verd à +8-10 pts.
Prochain : +4 held-out Whisper, v6 (epochs 3 / full data), mesure moyenne robuste.

---

## MISE À JOUR 2026-06-27 — held-out 8 vidéos (6 interviews + 2 débats), web ON

### État DÉPLOYÉ : v4 + reroute STAT étendu, tête de verdict OFF
| Métrique | Moy 8 vidéos | Cible | Écart |
|----------|--------------|-------|-------|
| Catégorie | **72.6** | 80 | −7.4 |
| Verdict | **68.6** | 75 | −6.4 |
| Biais | **59.2** | 60 | −0.8 (quasi atteint) |
| Verdict DÉBATS seuls | 61.6 | 75 | **point faible réel** |

### Journal leviers (depuis le plateau v4≈v5)
| Levier | Type | Effet mesuré | Décision |
|--------|------|--------------|----------|
| Reroute FAIT→STAT (chiffre porteur) | guard déterministe | **+6.5 cat** A/B, 0 coût LLM | ✅ déployé |
| Reroute étendu LOGIQUE/OPINION→STAT | guard déterministe | M2 cat 78.6→82.1, 0 régression | ✅ déployé |
| Harmonisation golds (14 corrections) | données | bruit label ↓, 2 golds held-out corrigés | ✅ appliqué |
| Guard JURIDIQUE→FAIT (mots de loi) | guard déterministe | 19% recall, 4% FP → sémantique | ❌ rejeté |
| **A1 tête de verdict unifiée** | architectural | **−3.5 verd** (M2 48→39) | ❌ revert (OFF) |

### Leçon archi
Couplage catégorie→verdict PAS purement nuisible : prompts spécialisés = priors tunés
(tolérance arrondi, cherry-pick) qu'une tête générique détruit. → améliorer les ENTRÉES
(A2 re-ranking preuves) plutôt que remplacer le JUGEMENT. Point faible = verdict débats (61.6).

### Prochains (ordre impact/coût)
A2 re-ranking embeddings CPU des snippets · A3 self-consistency k=3 (volatilité débats) · B2 biais contraint généralisé.

### MAJ 2026-06-27 (suite) — leviers archi A2/B2 testés
| Levier | Type | Effet mesuré (5 held-out) | Décision |
|--------|------|---------------------------|----------|
| A2 re-ranking TF-IDF sources | archi | **−3.5 verd** (TF-IDF promeut le lexical, pas le correctif ; couper prive de preuves) | ❌ revert (OFF) |
| B2 passe biais étendue OPINION/DOCTRINE | archi | neutre (golds sans biais hors LOGIQUE → rien à matcher) | ❌ OFF (safe, gain ailleurs) |

**BILAN ARCHI : 3 leviers « intelligents » testés (A1 tête verdict, A2 rerank, B2 biais) → tous neutres/négatifs.**
Les SEULS gains viennent des guards DÉTERMINISTES (reroute STAT +6.5 cat) et des DONNÉES (golds harmonisés).
→ Le pipeline spécialisé est bien tuné ; le remplacer/élaguer le dégrade. Le gap restant (verd 68.6, cat 72.6)
est désormais surtout un plafond MODÈLE/DONNÉES, pas architectural. Prochain vrai levier = données/retrain v7.
