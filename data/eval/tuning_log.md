# Journal de tuning nocturne

Format : `## Cycle N — HH:MM — vidéo` puis action / score avant→après / décision.

---

## Cycle 0 — kickoff — F-hsYpOya0M (Ruffin)
- Branche `bot-tuning-nuit` créée, scaffolding `data/eval/` en place.
- Serveur local UP (mode local, mistral-nemo:12b), vidéo Ruffin déjà analysée (24 analyses / 479 segments).
- Constat de départ (10 premiers verdicts) : sur-étiquetage sophismes (6/10 BIAIS), factuel vérifiable → NON_VERIFIABLE, sélection de fragments/questions.
- Action : extraction transcript+sortie bot ; dispatch agent étalonneur pour construire `gold/F-hsYpOya0M.json`.
- Prochain : évaluer le bot vs étalon avec `run_judgment_eval.py`, puis appliquer levier #1 (filtre sélection) ou #2 (garde-fou) selon le rapport.

## Cycle 1 — 02:15 — Ruffin — BASELINE mistral-nemo:12b
Score : **Catégorie 80% (20/25) · Verdict 70% · Biais 0% (0/2)**.
Bonne surprise : le jugement sur claim PROPRE est correct. Le ressenti "il est con" venait surtout de la SÉLECTION (fragments/questions), court-circuitée par ce test.
Erreurs verdict (diagnostic via server.log) — les 4 ratés ont TOUS trouvé des sources web :
- id 6 (RN infléchi climat, 13 src) → modèle dit FAUX. Gold VRAI.
- id 9 (Fonds vert ÷4/2ans, 15 src) → FAUX → guard "FAUX abusif" → NON_VERIF. Gold VRAI.
- id 10 (Roosevelt 2→42% PIB, 7 src) → FAUX → guard → NON_VERIF. Gold VRAI.
- id 18 (député short AN, 6 src) → FAUX → guard → NON_VERIF. Gold VRAI.
- id 8 (Fonds vert ÷3/3ans) → recherche DDG en ERREUR (vide) → guard STATISTIQUE force NON_VERIF. Gold IMPRECIS.
Cause racine : modèle FAUX/NON_VERIF malgré des extraits qui CONFIRMENT. Prompt `format_urls_for_prompt` ordonnait littéralement "par défaut CONTESTÉ/NON-VÉRIFIABLE" → scepticisme réflexe absorbé par le 12B.
Erreurs catégorie (5) : FAIT_HISTORIQUE mange JURIDIQUE (id 12,17), DOCTRINE (id 14), STATISTIQUE (id 11), et OPINION pris pour LOGIQUE (id 24).
Biais 0/2 : id 23 détecte un biais mais mauvais nom (Généralisation Hâtive vs Ad Hominem) ; id 24 raté (OPINION au lieu de Appel à l'Émotion).

## Cycle 2 — 02:40 — Ruffin — LEVIER #1 (verdict qui tranche)
Commit `tuning(verdict)`: réécriture de la règle de verdict dans web_search.py — confirme→VRAI, contredit→FAUX, hors-sujet→NON_VERIFIABLE, "ne sois pas sceptique par réflexe". Serveur redémarré (PID 3571912). Ré-éval lancée → résultat au prochain réveil. Si verdict monte sans casser la catégorie, on garde ; sinon revert.

### Résultat cycle 2 : **66% verdict (< 70%)** → ÉCHEC, REVERTÉ.
Le modèle dit TOUJOURS FAUX sur id 6 (RN-climat) et id 10 (Roosevelt) malgré sources confirmantes. Conclusion forte : **ce n'est pas la consigne, c'est le RAISONNEMENT du 12B**. mistral-nemo lit des extraits qui confirment et conclut "faux". → escalade modèle.

## Cycle 3 — 02:25 — Ruffin — TEST MODÈLE qwen2.5:14b
- Bascule `OLLAMA_MODEL=qwen2.5:14b-instruct-q8_0`. Tient en VRAM (14.7/16 GB, 100% GPU).
- Smoke test (Roosevelt) : qwen classe correctement STATISTIQUE, MAIS **~70s/analyse** (q8 compute-bound) → dépasse le timeout `/analyze` de 60s → résultat None.
- Corrections : (a) pull `qwen2.5:14b-instruct-q4_K_M` (~2× plus rapide, quant de prod) ; (b) commit fix timeout /analyze 60→120s.
- DDGS flaky cette nuit ("No results found" sur 2/3 requêtes Roosevelt) — fiabilité recherche à surveiller, affecte tous les modèles.
- Prochain (au pull terminé) : redémarrer serveur sur q4, smoke test latence, éval complète qwen vs baseline mistral-nemo (cat 80 / verd 70).

### Résultat cycle 3 : qwen2.5:14b-q4 = **cat 56% / verd 62%** (15s/analyse). N'AMÉLIORE PAS l'agrégat.
Finding nuancé & important : les deux modèles sont COMPLÉMENTAIRES.
- qwen GAGNE sur le raisonnement factuel : id 10 Roosevelt→VRAI (nemo disait FAUX), id 8 Fonds vert→IMPRECIS.
- qwen PERD sur : routage catégorie (invente NON_FAIT/CONSENSUS_SCIENCE hors-contexte), refuse les événements récents juin 2026 (id 1,18,22→NON_VERIFIABLE), et classe les sophismes en OPINION (id 23,24) → rate les biais que nemo attrapait.
DÉCISION : **mistral-nemo reste le modèle de référence.** qwen non adopté. Piste future : hybride (nemo classe + qwen juge le factuel) ou few-shot pour qwen sur la taxonomie. NB : la métrique catégorie pénalise des désaccords taxonomiques légitimes (livre-thèse → DOCTRINE ou FAIT_HISTORIQUE, etc.) — envisager `acceptable_categories[]` dans l'étalon (à valider avec Fabien, ne pas relâcher la métrique en douce).

## Cycle 4 — 02:55 — Ruffin — LEVIER #3 (classif JURIDIQUE)
Retour serveur sur mistral-nemo (PID 3590509). Fix prompt classif : "contenu normatif d'une loi/code/règlement → JURIDIQUE" (couvre id 12 code du travail, id 17 règlement AN, sans overfit). Commit `tuning(classif)`. Éval relancée → résultat au prochain réveil. Attendu : cat 80→~88% (id 12,17 corrigés), verdict inchangé (~70, plafond raisonnement nemo).
Décision à venir : Ruffin ≈ plafond nemo (verd borné par le modèle, biais sous-échantillonné à 2 claims) → passer à Tanguy (riche DOCTRINE/sophismes) pour du vrai signal biais.

### Résultat cycle 4 : **cat 80% / verd 70%** — AUCUN EFFET. id 12 & 17 toujours FAIT_HISTORIQUE.
nemo IGNORE la règle de classification ajoutée. Fix conservé (correct, utile à un meilleur modèle), mais inopérant sur le 12B.

## 🔑 CONCLUSION STRATÉGIQUE (après 4 cycles)
3 leviers testés, 3 fois la même leçon : **le prompt ne fait pas bouger mistral-nemo:12b** (confirme l'audit 2026-05-04). 
- Levier prompt verdict → empire (reverté). Levier modèle qwen → pas de gain agrégat. Levier prompt catégorie → nul.
- Plancher mesuré sur claim PROPRE : **~80% cat / ~70% verd**. Ce n'est PAS "con" — le vrai problème UX vient de la SÉLECTION (non testée ici).
**Chemins réels vers "parfait" (aucun n'est un tweak de prompt overnight) :**
1. **Guards programmatiques déterministes** (le code n'ignore pas une règle) — étendre `_apply_post_llm_guards` : ex. override catégorie par mots-clés loi/code/règlement → JURIDIQUE. Aligné avec la philo du projet.
2. **Fine-tuning LoRA** sur les étalons (distillation) — le vrai levier qualité. Préparer le dataset cette nuit.
3. **Corriger la SÉLECTION** (filtre questions/fragments) — gain UX direct, lever #1 du PLAN, à mesurer en end-to-end.

## Cycle 5 — 03:00 — Pivot Tanguy + dataset distillation
Ruffin classé "plafond nemo". On passe à Tanguy (rfRwwvbwSPo, riche DOCTRINE/sophismes) pour un vrai signal biais. Dispatch agent étalonneur sur le VTT. En parallèle : commencer le dataset de distillation (gold → paires instruction/réponse) dans data/eval/dataset/.

## Cycle 6 — 03:00 — Tanguy (étalon 25 claims dont 10 sophismes nommés)
Score nemo : **cat 44% / verd 52% / biais 20%** (bien plus bas que Ruffin — vidéo argumentative).
🎯 DIAGNOSTIC PRÉCIS de la détection de sophismes (le cœur de la demande Fabien) :
- **Présence d'un sophisme : recall 8/10** — nemo met BIAIS sur 8 des 10 vrais sophismes. Bonne intuition.
- **Nommage exact : ~3/10** (id 9 Red Herring, 16 & 17 Ad Hominem). Sur le reste il invente un mauvais nom (Généralisation au lieu d'Appel à l'Émotion, etc.). (NB méthodo : le matcher biais de run_judgment_eval sous-compte les synonymes "(English)" — vrai chiffre ≈30% pas 20%.)
- **Précision faible : 6 FAUSSES ALARMES** — BIAIS posé sur du factuel vrai (id 4,5,10), de la doctrine (id 19,20), une opinion (id 24).
=> Le bot = **alarme à sophismes hypersensible incapable de NOMMER le sophisme**. Le garde-fou LOGIQUE→BIAIS amplifie les fausses alarmes.
Catégorie 44% : même cause — sur-routage vers LOGIQUE de claims factuels/doctrinaux. Plus les ambiguïtés taxo habituelles.

## SYNTHÈSE 2 VIDÉOS (Ruffin + Tanguy)
| Vidéo  | Cat | Verd | Biais | Profil d'échec dominant |
|--------|-----|------|-------|--------------------------|
| Ruffin | 80% | 70%  | 0/2   | sous-confirme le vrai (dit FAUX/NON_VERIF sur faits vrais) |
| Tanguy | 44% | 52%  | ~30%  | sur-étiquette LOGIQUE/BIAIS (fausses alarmes sophisme) |
Les deux faces d'un même problème : **nemo ne calibre pas le doute**. Et le prompt ne le corrige pas (3 leviers nuls).
Dataset distillation : **50 ex** (Ruffin+Tanguy) prêt dans data/eval/dataset/sft.jsonl — base LoRA.

## Cycle 7 (à venir) — LE levier indépendant du modèle : la SÉLECTION
La sélection (questions, fragments ASR analysés comme affirmations) est ce qui faisait paraître le bot "con" en usage réel, et c'est du **Python déterministe** (stream_engine), donc corrigeable indépendamment du 12B. C'est le meilleur ROI concret restant. Prochain cycle : filtre de sélection (rejet "?", fragments non-assertifs) + mesure end-to-end sur un VTT.

## Cycle 7 — 03:15 — LEVIER SÉLECTION (déterministe) ✅ GAIN RÉEL
Mesure du problème : sur les 24 sélections RÉELLES du pipeline Ruffin → **29% de déchet** (3 questions + 4 fragments analysés comme des affirmations). C'est ça qui faisait "con".
Fix : `_is_analyzable_claim()` dans stream_engine.py (rejette questions "?", fragments commençant en minuscule = coupe ASR, clauses subordonnées). Haute précision (garde en cas de doute). Appliqué dans `_run_fact_checker_window` avant analyse.
Test unitaire sur les 24 vraies sélections : **6 rejetés (25%), 18 gardés, 0 faux positif** (toutes les vraies affirmations factuelles préservées). Import OK.
=> 1er levier qui apporte un GAIN MESURÉ et qui TIENDRA (déterministe, indépendant du 12B). Commit `tuning(selection)`.
Validation en cours : run end-to-end du VTT Tanguy dans le pipeline complet (serveur redémarré pour charger le filtre).


## Cycle 8 — 03:25 — VALIDATION IN-SITU du filtre sélection ✅
Run end-to-end du VTT Tanguy (238 phrases) dans le pipeline complet, serveur avec filtre chargé.
Le filtre a tiré in-situ (rejets loggés : 'Vous parlez d'alliance de la honte?', fragments).
Mesure : **0% de déchet** parmi les 21 affirmations analysées (vs 29% avant filtre). Gain confirmé en conditions réelles.

## ✅ FIN DE NUIT — voir RAPPORT_MATIN.md
Synthèse priorisée pour Fabien dans data/eval/RAPPORT_MATIN.md. Conclusions atteintes :
le bot n'est pas "con" (80/70 sur claim propre), la sélection était le coupable (corrigée),
le prompt ne bouge pas le 12B, qwen non supérieur, et la voie qualité = LoRA distillation (dataset 50 ex amorcé).
Reste en cours : étoffer le dataset (Zemmour/Leclerc) pour viser 150+ ex.
