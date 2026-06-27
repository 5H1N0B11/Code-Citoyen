# PLAN-OBJECTIF — Rendre le bot BON (pas juste diagnostiqué)

Carte blanche de Fabien (2026-06-27, ~04h) : manager d'agents en boucle, atteindre l'objectif,
puis recommencer avec d'autres vidéos politiques trouvées par moi. Recherche libre (science,
état de l'art). Tout LOCAL (pas de budget cloud). Base mistral-nemo:12b, GPU Blackwell 16 Go
(torch 2.11+cu13 OK, training possible).

## Objectif & critère "ATTEINT"
Le bot doit, sur une affirmation propre, atteindre sur les 4 étalons (moyenne) :
- **Catégorie ≥ 80 %**, **Verdict ≥ 75 %**, **Biais nommé ≥ 60 %** (matcher amélioré, synonymes EN/FR).
- ET 0 régression UX (filtre sélection conservé).
Baseline de départ (mistral-nemo, claim propre) : Ruffin 80/70 · Tanguy 44/52/~30 · Zemmour 56/50/40 · Leclerc 56/37/50.
=> Cibles dures : remonter Tanguy/Zemmour/Leclerc (l'argumentatif + les chiffres) et le NOMMAGE des sophismes.

## Échelle des leviers (du moins cher au plus lourd — escalader seulement si plateau)
1. **Matcher d'éval honnête** (préalable) : corriger run_judgment_eval pour compter les synonymes de biais ("Attaque personnelle (Ad Hominem)" == "Attaque Ad Hominem"). Sinon on sous-estime les gains.
2. **Few-shot via Modelfile Ollama** : exemples (input→output) tirés des étalons, PAS des règles (les règles ne bougent pas nemo — prouvé). Tester sur classification + analyse. CHEAP, possiblement décisif.
3. **Nommage de sophisme = classification contrainte** : au lieu de générer le nom librement (3/10), donner la liste fermée des 40 biais + définitions et forcer un choix (+ "aucun"). Grammar/JSON contraint si possible.
4. **Guards déterministes ciblés** : ex. si verdict=BIAIS mais catégorie factuelle/chiffrée évidente (regex nombre/%/€ + entité) → rétrograder ; anti-fausse-alarme. Bornés mais sûrs.
5. **QLoRA distillation** (artillerie) : sur les étalons (dataset au FORMAT INFERENCE réel). Voir research_sota.md pour la recette Blackwell (torchtune vs unsloth vs peft+bnb). Convertir en adapter GGUF → Ollama Modelfile ADAPTER → re-éval. N exemples mini réaliste : voir recherche (probable 200-500 → étoffer le dataset avec +vidéos).
6. **Ensemble / 2-passes** si besoin (nemo classe + 2e passe focalisée verdict/biais).

## Protocole de boucle (chaque réveil)
1. Lire ce plan + tuning_log.md (état). Vérifier serveur (curl :5000/api/status), relancer local mistral-nemo sinon.
2. Récupérer le travail des agents en cours (recherche, install, étalonnage).
3. Appliquer LE prochain levier non encore testé (ordre ci-dessus), commit atomique sur bot-tuning-nuit.
4. **Mesurer** (run_judgment_eval sur les 4 vidéos, ou un sous-ensemble représentatif). Garder si gain net, REVERT sinon. Journaliser avant→après.
5. Si critère ATTEINT sur les 4 → phase EXTENSION : trouver de nouvelles vidéos politiques FR (chaînes BFM/LCP/Public Sénat/France Info, débats, interviews), récupérer transcript (yt-dlp VTT ou Whisper), étalonner via agent, ré-évaluer, et continuer à durcir le modèle (plus de données = meilleur LoRA).
6. Reprogrammer le réveil (~1200-1500s). Ne jamais merger sur main. Serveur laissé tournant.

## Garde-fous manager
- Mesurer avant de déclarer un gain. Pas d'auto-congratulation : chiffres à l'appui.
- Un levier qui régresse → revert immédiat + note.
- Entraînement : ne pas saturer le GPU pendant qu'une éval tourne (sérialiser). Sauvegarder les checkpoints.
- Honnêteté : si un levier plafonne, le dire et escalader. Si 100 ex ne suffisent pas au LoRA, étoffer les étalons AVANT d'entraîner.
- État de l'art d'abord (research_sota.md) : ne pas réinventer, s'appuyer sur les méthodes qui marchent.

## Suivi
- Scores : `data/eval/scoreboard.md` (à créer, courbe par vidéo et par levier).
- Journal : `tuning_log.md`. Synthèse : `RAPPORT_MATIN.md`. Recherche : `research_sota.md`.
