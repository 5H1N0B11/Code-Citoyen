# Code Citoyen — État & TODO (2026-07-05)

Fact-checker temps réel de débats/interviews politiques. Whisper (transcription) + Ollama (LLM local
mistral-nemo-citoyen-v4) + recherche web + **identification des locuteurs** (diarisation ECAPA).

---

## 🚀 Lancer le bot (après reboot)
```bash
cd /media/fabien/DATA_4To/Programs/Programs/CodeCitoyen
bash scripts/start_factchecker.sh
# → http://localhost:5000  (interface : coller une URL YouTube)
```
Config (dans `.env`) : modèle `mistral-nemo-citoyen-v4`, reroute STAT actif, web search ON.
**GPU partagé avec cashFlow** : l'inférence du bot prend le GPU → un seul des deux à la fois.
Whisper + diarisation + ECAPA tournent sur **CPU** (pas de conflit GPU).

---

## ✅ Ce qui marche (état actuel)
- **Fact-checking** : catégorie / verdict / biais. Perf held-out (8 vidéos) : cat 73.7 / verd 67.8 / biais 59.2.
- **Sélection live** corrigée (schéma JSON contraint — le LoRA renvoyait une analyse au lieu d'une liste).
- **Reroute STAT déterministe** (chiffre porteur → STATISTIQUE) : +6.5 pts catégorie.
- **Identification des locuteurs** (voir ci-dessous) : diarisation + reconnaissance vocale + nom affiché.
- **UI** : fil d'analyse avec verdict/biais + nom du locuteur ; lien « Ouvrir sur YouTube » si embed bloqué ;
  en-têtes no-cache (les modifs d'UI s'affichent sans Ctrl+Shift+R).

## 🎤 Système « qui parle » (livré, à affiner)
- **Diarisation ECAPA-TDNN** (`src/ingestion/ecapa.py`, SpeechBrain, CPU, sans token). Bien plus discriminant
  que Resemblyzer (marge ~0.5 vs 0.93 de faux match). Modèle dans `data/models/ecapa` (symlinks cache HF, re-DL auto).
- **Base d'empreintes auto-apprenante** (`src/ingestion/voiceprints.py`, `data/voiceprints/db.json`) : chaque
  locuteur identifié est mémorisé → reconnu instantanément à la voix dans les vidéos suivantes (ex. Ruffin reconnu sim 1.00).
- **Nommage par le LLM** (`orchestrator.identify_speakers`) : déduit le vrai nom depuis le contexte + le titre,
  avec garde anti-pollution (n'affiche/apprend un nom que s'il est corroboré par le titre ou = « Journaliste »).
- ⚠️ Le template UI servi sur `/` est **`src/web/templates/index.html`** (PAS `app.html` qui est sur `/app`).

## 🔧 TODO — prochaine session (affiner l'attribution fine des locuteurs)
1. **Nommer le cluster journaliste « Journaliste »** au lieu de « Locuteur 2 ».
2. **Prises de parole brèves absorbées** : sur une interview (le dominant parle ~88 %), les questions courtes
   du journaliste sont collées au bloc du locuteur dominant (fenêtres 2.5 s + lookup au plus proche).
   → Attribuer le speaker **par segment Whisper** (embedder chaque segment) plutôt que par fenêtre fixe + lookup ;
   ou fenêtres plus fines / alignées sur les frontières Whisper.
   Réf test : vidéo Ruffin `F-hsYpOya0M` (actuel : 238 Ruffin / 32 Locuteur2).
3. Cosmétique : nettoyer l'item « INFO / undefined » en tête de fil (index.html).

## 📊 Modèle / données (ne pas refaire)
- **v4 déployé** (`mistral-nemo-citoyen-v4`). v5 ≈ v4. **v7 (retrain +5 vidéos) a ÉCHOUÉ** (sur-apprentissage,
  −6.5 verd) → plafond du 12B confirmé. Prochain levier modèle éventuel = base plus grande (qwen), pas + de données/tuning.
- Held-out (9 vidéos, jamais en train) + rubrique verdicts + golds audités : voir `data/eval/scoreboard.md`, `RUBRIQUE_VERDICTS.md`.

---

## ♻️ Notes REBOOT (important)
- **`/tmp/llama.cpp` est PERDU au reboot** — sert à convertir un adapter LoRA en GGUF. Si retrain futur :
  `git clone https://github.com/ggerganov/llama.cpp /tmp/llama.cpp` (puis `convert_lora_to_gguf.py`).
- **Persistants (OK) :** `data/models/ecapa` (re-DL auto si absent), `data/voiceprints/db.json` (base voix apprise), modèles Ollama.
- **Serveur** : ne redémarre pas tout seul → relancer via `scripts/start_factchecker.sh`.
- torch 2.11+cu130 (Blackwell) — ne pas casser ; speechbrain/torchaudio 2.11 installés OK dans `.venv`.
