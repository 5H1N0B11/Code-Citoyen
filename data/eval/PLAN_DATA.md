# PLAN DONNÉES — franchir le plafond du 12B (option 2)

Statut : leviers gratuits + architecturaux épuisés. Mesure FIABLE (golds audités). Gap RÉEL :
cat 73.7 / verd 67.8 / biais 59.2 (cible 80/75/60). Seule voie restante = **plus de données PROPRES**.

## Pourquoi « plus de données » ≠ le risque de régression vu
La régression du v6 = **sur-apprentissage** (trop d'epochs / rank trop élevé sur le MÊME petit dataset
→ mémorisation). Ce n'est PAS « trop de données ». Plus de données propres = le REMÈDE
(diversité → généralisation). Le danger réel : (a) sur-entraîner, (b) ajouter des étiquettes BRUITÉES.
→ Garde-fous : cap epochs (2), rank modéré (16-32), et étalonnage audité comme on vient de le faire.

## Cible des nouvelles données (où sont les gaps)
1. **Catégorie OPINION↔LOGIQUE** (la plus grosse confusion résiduelle) : viser des claims argumentatifs
   (jugements de valeur vs sophismes) pour apprendre la frontière.
2. **Verdict sur DÉBATS** (point faible, 62.5) : format multi-locuteurs, claims qui s'enchaînent.
   → privilégier des DÉBATS politiques (pas que des interviews).
3. Diversité de locuteurs / partis (éviter le sur-ajustement à quelques figures).

## Pipeline (par vidéo, en mode manager)
1. **Sélection** : vidéo politique FR avec transcript fiable. Cf. candidats infra.
2. **Transcript** : `WHISPER_DEVICE=cpu .venv/bin/python data/eval/whisper_transcribe.py <video_id>`
   (= le vrai pipeline de prod ; meilleur que les VTT auto).
3. **Étalonnage** : agent(s) qui découpent en claims + posent category/expected_verdict/expected_bias
   selon `RUBRIQUE_VERDICTS.md`, PUIS un 2e agent qui AUDITE les étiquettes (recherche web) — le double
   passage a prouvé sa valeur (golds à ~4 % de bruit). Sortie : `data/eval/gold/<id>.json`.
4. **Held-out** : décider AVANT entraînement si la vidéo va en TRAIN ou en HELD-OUT (ne jamais mélanger).
5. **Build** : `HELDOUT="id1,id2,..." .venv/bin/python data/eval/build_dataset.py` → sft.jsonl.
6. **Train v7** : `R=32 EPOCHS=2 .venv/bin/python data/eval/qlora_train.py` (libérer la VRAM d'Ollama
   d'abord : `ollama stop mistral-nemo-citoyen-v4`). Convertir GGUF → `Modelfile.v7` → `ollama create`.
7. **Éval** : moyenne held-out parallèle (web ON). GARDER v7 si la moyenne monte, sinon rester v4.

## Stratégie recommandée : ship + accumulation au fil de l'eau
Ne PAS faire un grand chantier data en amont (rendements décroissants, plafond 12B). À la place :
- **Expédier v4 maintenant** (utilisable).
- Chaque vidéo fact-checkée en campagne → étalonnée (pipeline ci-dessus) → versée au dataset.
- Re-LoRA tous les ~5-8 nouvelles vidéos, garder si la moyenne held-out progresse.
→ Valeur immédiate + amélioration continue + évite le sur-apprentissage (réentraînement sur du réel diversifié).

## Candidats vidéos
Voir section ajoutée par l'agent de scouting ci-dessous (à compléter).

### Candidats identifiés (scout 2026-06-27 — IDs à reconfirmer à l'ingestion)
| # | Titre / chaîne | ID YouTube | Format | Gap comblé |
|---|---|---|---|---|
| 1 | Débat chefs de partis devant le Medef — BFMTV | `AGw-hcvwTSQ` | Débat 5 locuteurs (Attal/Bardella/Bompard/Retailleau/Roussel) | DÉBAT + STAT, 4 locuteurs neufs |
| 2 | Bompard (LFI) vs Wauquiez (LR) — BFMTV | `XuTN2ObRdUg` | Face-à-face | DÉBAT + STAT gauche/droite |
| 3 | Immigration/régularisations métiers en tension — Public Sénat | `I_Rzif_L13A` | Débat sénateurs | Diversité institutionnelle, locuteurs neufs |
| 4 | Immigration : la gauche à la hauteur ? — France 5 C Ce Soir | `AE-y5MiKXfY` | Débat plateau | OPINION↔LOGIQUE, sophismes |
| 5 | Grand débat Léon Deffontaines (PCF) — BFMTV | `YRa1G0xq_pY` | Entretien-débat | Diversité locuteur (PCF) |

Pistes sans ID isolé : France 24 « Le Débat », LCP « Ça vous regarde » (budget 2026), Public Sénat « Sens Public ».
Énergie non couverte (à retrouver). Priorité = #1 et #2 (les plus alignés débat+STAT).

### Première itération suggérée (si Fabien dit GO)
Étalonner #1 (débat 5 partis, le plus riche) → held-out OU train selon besoin → si train, re-LoRA v7 (R32/2ep)
→ éval held-out. Sinon, l'ajouter comme 3e débat held-out pour muscler la mesure du point faible (verdict débat).

### Avancement accumulation (fil-de-l'eau)
- ✅ AGw-hcvwTSQ (Medef, 22 claims) → HELD-OUT (généralisation v4 : cat 90.9/verd 45.5/biais 100)
- ✅ XuTN2ObRdUg (Bompard/Wauquiez, 19 claims) → TRAIN (audit : 0 correction H, gold propre)
- ✅ AE-y5MiKXfY (France5 immigration, 17 claims) → TRAIN (audit 0 corr ; bon OPINION/LOGIQUE)
- ⏳ Cible : ~5-6 vidéos TRAIN avant re-LoRA v7. Avancement TRAIN : 2/~6.
