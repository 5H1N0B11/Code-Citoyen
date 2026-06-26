# PROTOCOLE — Tuning nocturne du bot (LOCAL only)

But unique : que le bot **local** (Whisper + Ollama) analyse *parfaitement* les vidéos
politiques — catégorie, verdict, biais/sophisme, doctrine, statistiques — comme documenté
dans `src/prompts/bias_list.py` et `templates.py`. Aucune dépendance cloud (pas de budget).

Manager = Claude (boucle réveillée ~toutes les 15 min). Équipe = sous-agents.
Branche de travail : `bot-tuning-nuit` (tout est réversible, review au réveil).

## Jeu de test (ordre)
1. `F-hsYpOya0M` — Ruffin / BFM (transcript Whisper déjà dispo, sortie bot déjà produite) ← démarrer ici
2. `rfRwwvbwSPo` — Tanguy "Il n'y a pas de fascistes" (riche en DOCTRINE/sophismes) — VTT
3. `NO8cUqaYxOM` — Zemmour / Apolline (STATISTIQUE/JURIDIQUE) — VTT
4. `GG3RbjCGL1I` — Leclerc "profiteurs de guerre" — VTT

## Boucle de chaque réveil (15 min)
1. Vérifier que le serveur tourne (`curl :5000/api/status`) ; sinon relancer (`scripts/`).
2. Lire `data/eval/tuning_log.md` (dernier état) pour reprendre où on en était.
3. État de la vidéo courante :
   - **Pas de maître-étalon ?** → dispatcher l'agent "étalonneur" (web search, schéma ci-dessous) → `data/eval/gold/<id>.json`.
   - **Étalon prêt mais pas évalué ?** → `python data/eval/run_judgment_eval.py data/eval/gold/<id>.json` → rapport dans `data/eval/reports/`.
   - **Évalué sous le seuil ?** → appliquer LE prochain levier de tuning (liste ci-dessous), commit, ré-évaluer.
   - **Au-dessus du seuil ?** → marquer PASS dans le log, passer à la vidéo suivante.
4. Journaliser dans `tuning_log.md` (cycle, action, score avant/après).
5. Re-programmer le réveil (ScheduleWakeup ~900s) tant qu'il reste des vidéos < seuil.

## Seuils de réussite ("parfait" pragmatique) par vidéo
- Catégorie correcte ≥ 85 %
- Verdict correct ≥ 80 % (tolérance : VRAI↔IMPRECIS et FAUX↔TROMPEUR comptent 0.5)
- Biais/sophisme : nom exact OU famille correcte ≥ 70 % sur les claims LOGIQUE
- 0 hallucination de chiffre, 0 question rhétorique analysée comme affirmation

## Schéma du maître-étalon  `data/eval/gold/<video_id>.json`
```json
{
  "video_id": "...", "title": "...", "source": "whisper|vtt",
  "claims": [{
    "id": 1,
    "quote": "verbatim transcript",
    "claim_clean": "affirmation autonome désambiguïsée",
    "speaker": "nom ou null",
    "category": "STATISTIQUE|JURIDIQUE|FAIT_HISTORIQUE|DOCTRINE|CONSENSUS_SCIENCE|LOGIQUE|OPINION|NON_FAIT",
    "expected_verdict": "VRAI|FAUX|TROMPEUR|IMPRECIS|CONTESTE|NON_VERIFIABLE|BIAIS|OPINION",
    "expected_bias": "nom exact depuis bias_list.py, ou null",
    "rationale": "pourquoi ce verdict (1-3 phrases)",
    "sources": ["url primaire 1", "url 2"]
  }]
}
```
Règles étalon : 15-30 claims/vidéo, privilégier les affirmations VÉRIFIABLES (chiffres, lois,
faits, doctrines) ; pour chaque claim factuel, AU MOINS une source primaire réelle (insee.fr,
legifrance, AFP, étude…) vérifiée par web search. Ignorer les phrases creuses. Pour LOGIQUE,
nommer le sophisme exact de bias_list.py.

## Leviers de tuning (ordre = impact/effort, tout local)
1. **Filtre de sélection** (`stream_engine.py`) : rejeter questions ("?"), fragments ASR sans verbe/sujet, phrases non assertives.
2. **Garde-fou LOGIQUE→BIAIS** (`orchestrator._apply_post_llm_guards`) : ne forcer BIAIS que si un sophisme nommé est détecté ; sinon laisser OPINION. Aujourd'hui il sur-étiquette.
3. **Prompt classification + few-shot** (`templates.get_classification_prompt`) : exemples ancrés sur la taxonomie, distinguer OPINION vs LOGIQUE vs STATISTIQUE.
4. **Prompts spécialisés par catégorie** (`templates.get_specialized_system_prompt`) : forcer l'usage des EXTRAITS web, interdire le "NON_VERIFIABLE" paresseux quand une source est fournie.
5. **Test modèle** : `OLLAMA_MODEL=qwen2.5:14b-instruct-q8_0` (15.7 GB, tient si rien d'autre en VRAM) ou pull `qwen2.5:14b-instruct-q4_K_M` (~9 GB, marge confortable). Comparer score vs mistral-nemo.
6. **Params Ollama** : temperature 0, num_ctx 16384, num_predict adapté.
7. **Usage des sources** : reformuler `format_urls_for_prompt` pour que le verdict CITE l'extrait.
8. **(Stretch) Distillation** : accumuler les paires (claim_clean → analyse idéale) dans `data/eval/dataset/` ; si le harnais est stable et qu'il reste du temps, préparer un LoRA mistral-nemo (NE PAS lancer un train qui casse le GPU pendant que le serveur tourne — documenter seulement).

## Garde-fous manager
- Ne jamais merger sur `main`. Commits atomiques sur `bot-tuning-nuit`.
- Si un levier FAIT BAISSER le score → revert ce commit, noter dans le log, essayer le suivant.
- Ne pas relancer 4× le même download modèle. Vérifier `ollama list` avant pull.
- Budget agents : 1-2 sous-agents focalisés par cycle, pas de fan-out massif.
