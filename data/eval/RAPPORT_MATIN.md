# ☀️ Rapport du matin — Tuning nocturne du bot (2026-06-27)

Branche : `bot-tuning-nuit` (commits atomiques, **rien sur `main`**). Détail chrono : `tuning_log.md`.

## TL;DR
Ton bot **n'est pas « con »**. Sur une affirmation propre, il juge correctement ~**80 % des catégories** et ~**70 % des verdicts**. Ce qui le faisait paraître bête, c'était la **sélection** : ~29 % des phrases envoyées à l'analyse étaient des **questions ou des fragments ASR** (« Le gouvernement payerait-il ? », « se disent que… »). 

➡️ **Corrigé cette nuit** par un filtre déterministe → **0 % de déchet** en validation end-to-end. C'est le gain le plus important et il *tiendra* (c'est du code, pas un prompt).

## Scores mesurés (jugement sur claim propre, vs maîtres-étalons web-sourcés)
| Vidéo | Catégorie | Verdict | Biais (nommage) | Profil d'échec |
|-------|-----------|---------|------------------|----------------|
| Ruffin (BFM) | **80 %** | **70 %** | 0/2 (échantillon trop petit) | sous-confirme le vrai (dit FAUX/NON_VERIF sur des faits vrais) |
| Tanguy (RN) | **44 %** | **52 %** | ~3/10 | sur-étiquette LOGIQUE/BIAIS (fausses alarmes sophisme) |
| Zemmour (Reconquête) | **56 %** | **50 %** | 2/5 | idem : sur-étiquette l'argumentatif, chiffres souvent IMPRECIS vus FAUX |

**Pattern confirmé sur 3 vidéos** : excellent sur le factuel clair (Ruffin), il décroche sur le discours argumentatif (Tanguy/Zemmour ~50 %). Les profils sont **les deux faces d'un même défaut** : mistral-nemo:12b **ne calibre pas le doute** (sous-confirme le vrai, sur-étiquette le sophisme).

## Détection des sophismes (ce que tu veux vraiment) — vidéo Tanguy, 10 sophismes
- **Présence détectée : 8/10** — il *sent* le sophisme et met le verdict BIAIS. Bon instinct.
- **Nommage exact : ~3/10** — il sait qu'il y a un problème mais se trompe de nom (dit « Généralisation Hâtive » pour un « Appel à l'Émotion »…).
- **6 fausses alarmes** — il colle BIAIS sur des faits vrais, de la doctrine et une opinion.
- Le garde-fou `LOGIQUE→BIAIS` **amplifie** les fausses alarmes.

## Ce qui NE marche PAS (économise-toi ces pistes)
1. **Tuner les prompts sur le 12B** : 3 leviers testés (verdict, catégorie) → 0 effet ou pire. mistral-nemo **n'applique pas** les consignes fines (confirme ton audit du 2026-05-04). Le prompt est un cul-de-sac sur ce modèle.
2. **Changer pour qwen2.5:14b** : testé (q8 puis q4). Il raisonne mieux sur le factuel (Roosevelt VRAI là où nemo disait FAUX) MAIS route mal les catégories et sous-détecte les sophismes (les classe « OPINION »). **Pas de gain agrégat** (56/62 vs 80/70). Complémentaire, pas supérieur.

## Ce qui MARCHE (reco priorisée)
1. **✅ FAIT — Garder le filtre de sélection** (`stream_engine._is_analyzable_claim`). Gain immédiat et permanent. Déjà committé.
2. **🎯 LoRA distillation** = le vrai levier qualité « avec peu de moyens ». Le dataset est amorcé : `data/eval/dataset/sft.jsonl` (**50 exemples** Ruffin+Tanguy, format messages). Cible : 150+ en ajoutant Zemmour & Leclerc, puis fine-tune mistral-nemo (axolotl/unsloth, tient sur la 5070 Ti). C'est ce qui apprendra au modèle à *calibrer* (confirmer le vrai, nommer le bon sophisme).
3. **Guard déterministe anti-fausse-alarme-BIAIS** : en code (pas en prompt), refuser BIAIS quand la catégorie est factuelle/chiffrée et qu'aucun sophisme nommé n'est extrait. S'inscrit dans la philo `_apply_post_llm_guards` existante.
4. **Métrique** : envisager `acceptable_categories[]` dans les étalons — plusieurs catégories sont légitimement ambiguës (un livre-thèse = DOCTRINE *ou* FAIT_HISTORIQUE), ce qui pénalise injustement le score catégorie. À valider avec toi avant de relâcher la mesure.

## Assets produits cette nuit (réutilisables)
- 2 **maîtres-étalons** web-sourcés : `data/eval/gold/{F-hsYpOya0M,rfRwwvbwSPo}.json` (50 claims vérifiés).
- **Harnais d'éval** reproductible : `run_judgment_eval.py` (catégorie/verdict/biais vs étalon).
- **Dataset de distillation** : `dataset/sft.jsonl` (50 ex, grandit avec chaque étalon).
- Constructeurs : `extract_inputs.py`, `build_dataset.py`. Protocole : `PLAN.md`.

## Limites honnêtes
- Évaluation sur le **jugement** (claim propre). La qualité de **désambiguïsation** par le LLM de sélection n'est pas mesurée finement.
- DDGS (recherche web) était **instable** cette nuit (« No results found » par intermittence) → quelques NON_VERIFIABLE injustes, indépendants du modèle.
- 2 vidéos seulement. Zemmour/Leclerc en cours pour solidifier.
