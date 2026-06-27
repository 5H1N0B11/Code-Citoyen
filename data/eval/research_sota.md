# Revue SOTA — Fact-checking & détection de sophismes pour LLM local (mistral-nemo:12b, RTX 5070 Ti Blackwell)

> Cible : bot CodeCitoyen, débats politiques FR, en LOCAL (Ollama). Problèmes actuels : sur-étiquetage des sophismes, incapacité à les NOMMER précisément, chiffres non nuancés.
> Date : 2026-06-27. Toutes les affirmations sont sourcées (URLs en bas de chaque section).

---

## 0. TL;DR décisions (détail en §6)

1. **Fermer la taxonomie + constrained decoding** : liste fermée de sophismes (taxonomie MAFALDA, ~23 classes regroupées en 3 super-classes) + JSON forcé par grammaire GBNF/structured outputs. Ajouter explicitement une classe `aucun_sophisme` pour casser le sur-étiquetage.
2. **Prompting multi-tour + définitions** : pour un petit modèle, le schéma "définis le sophisme candidat → vérifie → décide" (multi-round / CoT) gagne +5 à +7 points F1 vs single-shot. Few-shot pur n'apporte presque rien (<2 pts).
3. **Verdicts façon FEVER + abstention calibrée** : pipeline retrieval → NLI/verdict, avec NON_VERIFIABLE réservé aux cas SANS preuve récupérée (pas un défaut paresseux), et séparation explicite fait / opinion / doctrine en amont.
4. **Fine-tuning local = QLoRA via torchtune (torchao NF4), SANS bitsandbytes** : c'est le chemin le plus sûr sur Blackwell sm_120 / CUDA 13 / torch 2.11. 200–500 exemples par tâche suffisent pour bouger une classif. Export Ollama via `convert_lora_to_gguf.py` + `ADAPTER` dans le Modelfile.

---

## 1. Détection de sophismes / fallacies par LLM

### Datasets de référence
- **MAFALDA** (NAACL 2024) — benchmark qui unifie les datasets précédents avec une **taxonomie à 3 niveaux** : niveau 0 = sophisme ou non ; niveau 1 = 3 super-classes (*appeal to emotion*, *fallacy of credibility*, *fallacy of logic*) ; niveau 2 = **~23 sophismes nommés**. Fournit annotations + explications + un schéma d'éval pensé pour la **subjectivité** (matching partiel par spans, pas exact-match). C'est la meilleure base pour NOMMER. Repo + guidelines d'annotation publics.
- **LOGIC / LogicClimate** — issus de matériel pédagogique ; LOGIC est le plus "dur" (taxonomie fine, hors-distribution).
- **Argotario** — crowdsourcing gamifié, classes équilibrées, le plus "facile/compréhensible".
- **ElecDeb60to20 / DISPUTool 3.0** — **débats présidentiels US 1960–2020**, annotation token-level : composants argumentatifs (claims/premises), relations (support/attack) et **6 sophismes** : *Ad Hominem, Appeal to Authority, Appeal to Emotion, False Cause, Slippery Slope, Slogans*. Le plus proche de notre cas d'usage (débat politique). Le SOTA y combine représentations Transformer + features argumentatives/ingénierées (le texte seul ne suffit pas).
- Autres : Propaganda (techniques de propagande), Reddit, COVID-19, MISSCI (fallacies santé).

### Comment les SOTA NOMMENT le bon sophisme
- **Classification contrainte (taxonomie fermée) >> génération libre** pour la cohérence : on impose le choix dans un ensemble fini + on donne les **définitions** des classes dans le prompt. MAFALDA et les études zero-shot évaluent toutes contre une taxonomie fermée ; la génération libre rend l'éval ininterprétable et explose la variance des noms.
- **Multi-tour / "definition-grounded"** : "Are LLMs Good Zero-Shot Fallacy Classifiers?" (EMNLP 2024) montre que des schémas multi-tours (générer la définition du sophisme candidat, "general fallacy analysis with warm-up", puis décider) battent le single-shot — **+1.6 à +7.5 points F1**, gains **les plus forts sur les petits modèles** (Llama3 +7.54). Zero-shot CoT est 2e et a le plus faible taux d'échec de format.
- Travaux complémentaires : **Logical Structure Tree** (EMNLP 2024) et **knowledge-augmented / "Follow My Lead"** (2025) — injecter la structure logique de l'argument aide tous les modèles.

### Few-shot vs fine-tuning : gains typiques
- **Zero-shot LLM ≈ ou > fine-tuned** sur datasets open-domain et surtout **hors-distribution** : GPT-4 78.94 F1 sur Argotario vs T5-3B fine-tuné 69.13. Mais sur datasets "durs/spécifiques" (LOGIC), le fine-tuné gagne (T5-3B 64.95 vs GPT-4 50.43).
- **Few-shot pur ≈ inutile** ici : amélioration marginale (GPT-4 LOGIC 48.45→50.54), souvent aucun gain au-dessus du meilleur zero-shot. → **Ne pas miser sur "ajouter des exemples few-shot" pour nommer mieux**; miser sur définitions + multi-tour + (si besoin) fine-tuning ciblé.
- **Synthèse** : pour un 12B local, le levier #1 = **liste fermée + définitions + raisonnement multi-tour court**, le #2 = QLoRA sur quelques centaines d'exemples du domaine FR.

Sources :
- MAFALDA — https://aclanthology.org/2024.naacl-long.270/ · https://arxiv.org/abs/2311.09761 · https://github.com/ChadiHelwe/MAFALDA
- Are LLMs Good Zero-Shot Fallacy Classifiers? — https://arxiv.org/html/2410.15050v1
- Fallacies in Political Debates (EMNLP 2023) — https://aclanthology.org/2023.emnlp-main.684/ · DISPUTool 3.0 — https://aclanthology.org/2025.acl-demo.45/ · repo https://github.com/pierpaologoffredo/FallacyDetection
- Logical Structure Tree — https://aclanthology.org/2024.emnlp-main.730.pdf · Follow My Lead — https://arxiv.org/html/2510.09970v1

---

## 2. Vérification de claims / fact-checking automatique

### Pipeline FEVER-style
3 sous-tâches : **(1) document retrieval** (TF-IDF/dense) → **(2) sentence selection** (ranking des phrases-preuves) → **(3) NLI/verdict** : SUPPORTED / REFUTED / **NEI (Not Enough Info)**. C'est le squelette canonique à reproduire (retrieval → verdict NLI).

### Éviter le NON_VERIFIABLE paresseux ET le faux positif
- **NEI doit être un état de preuve, pas un refus** : dans FEVER, NEI = aucune phrase-preuve pertinente trouvée. Règle d'implémentation : ne renvoyer NON_VERIFIABLE **que si le retrieval ramène 0 preuve exploitable** (after dense+web search). Si des preuves existent mais contradictoires → CONTESTE, pas NON_VERIFIABLE.
- **Calibration / abstention** : les LLM sont **mal calibrés** (sur-confiants quand faux, sous-confiants quand justes) ; la confiance verbale corrèle faiblement avec l'exactitude. Solutions : **selective prediction** (répondre seulement si confiance > seuil, sinon abstention explicite), consistance (auto-cohérence sur plusieurs échantillons), et seuils par catégorie. → produire un **score de confiance** + politique d'abstention plutôt qu'un verdict binaire forcé.
- **Anti-faux-positif** : exiger une preuve citée (URL/quote) pour tout verdict VRAI/FAUX ; sinon dégrader vers IMPRECIS/NON_VERIFIABLE. (Le projet a déjà des garde-fous post-LLM, cf. commit 9686785 — les aligner sur cette règle "pas de verdict tranché sans preuve liée".)

### Distinction fait / opinion / doctrine
- À traiter **comme un routeur en amont** du fact-check : une *opinion* ("c'est scandaleux") et une *doctrine* ("l'immigration doit être réduite par principe") ne sont **pas falsifiables** → ne pas leur attribuer VRAI/FAUX ; on peut détecter biais/sophisme mais le verdict factuel doit être `N/A (opinion)` / `N/A (doctrine)`. Seuls les **claims factuels vérifiables** (statistique, juridique, fait) entrent dans le pipeline retrieval→verdict. Ça réduit mécaniquement les faux positifs.

Sources :
- FEVER shared task / pipeline — https://www.emergentmind.com/topics/fever-fact-verification-task · survey ACM — https://dl.acm.org/doi/10.1145/3485127 · pipeline multilingue — https://link.springer.com/article/10.1007/s00521-024-10113-5
- Calibration/abstention — https://openreview.net/forum?id=JJPAy8mvrQ (SelectLLM) · https://arxiv.org/html/2502.11028v3 (overconfidence) · https://arxiv.org/html/2601.02574 (fact-checking via certainty & consistency)

---

## 3. Améliorer un PETIT LLM local (12B) sans gros moyens

### (a) Few-shot prompting efficace
- **3 exemples par classe** est le standard de la littérature fallacy (3 paires texte→label par type, exclus de l'éval). Mais sur ces tâches le few-shot apporte **<2 pts** (cf. §1) → préférer **définitions explicites des classes + 1–2 exemples canoniques** par super-classe, pas une longue liste.
- Format : instruction → taxonomie+définitions → (exemples courts) → claim → **sortie JSON contrainte**. Garder le prompt d'inférence STABLE (servira de gabarit au dataset de fine-tuning, cf. (c)).

### (b) Constrained decoding / grammars (le plus gros levier "gratuit")
- **GBNF (llama.cpp)** force la sortie à une grammaire : JSON valide garanti + **enum fermé** pour le champ sophisme/verdict/catégorie. On filtre la distribution de tokens à chaque pas → impossible d'inventer un nom de sophisme hors-liste, impossible de produire du JSON cassé. Convertisseur JSON-Schema→GBNF intégré (utilisable depuis Pydantic).
- Concrètement : définir un schéma avec `enum` = liste fermée des sophismes (noms MAFALDA) + `enum` verdicts + `enum` catégories, + un champ `confidence` (number) + `evidence` (string/URL). Ollama supporte `format` JSON-schema (structured outputs) ; llama.cpp expose `--grammar`/`grammar`.
- Effet attendu sur NOS bugs : (i) plus de noms inventés/flous → ils tombent dans la liste ; (ii) ajouter `"aucun_sophisme"` dans l'enum + l'autoriser explicitement casse le **sur-étiquetage** (le modèle a une "sortie de secours" légitime).

### (c) Distillation / QLoRA — ordres de grandeur réalistes
- **Minimum utile : 50–100 exemples** ; **200–500 exemples LoRA suffisent** pour une tâche de classification/extraction sur un modèle ouvert (Llama3/Mistral/Qwen) et atteindre le haut des 90 % sur la bonne tâche. **QLoRA perd 1–2 % vs LoRA full** (négligeable).
- **Qualité >> quantité** : 200 exemples propres battent 2000 sales.
- **Format du dataset = MIROIR EXACT du prompt d'inférence** : mêmes instructions, même taxonomie, même schéma JSON de sortie. C'est la règle la plus importante : le modèle apprend à remplir EXACTEMENT le gabarit qu'il verra en prod (sinon dégradation). Inclure des exemples `aucun_sophisme` et des `N/A (opinion)` pour calibrer l'abstention.
- Stratégie cheap : **distiller** un gros modèle (générer des annotations sur nos VTT FR Zemmour/Tanguy/Leclerc), corriger à la main les cas limites, puis QLoRA le 12B dessus. 300–600 exemples FR ciblés = un bon premier palier.

Sources :
- GBNF / structured outputs — https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md · https://deepwiki.com/ggml-org/llama.cpp/7.3-grammar-and-structured-output · guide constrained decoding — https://www.aidancooper.co.uk/constrained-decoding/
- Données nécessaires — https://particula.tech/blog/how-much-data-fine-tune-llm · https://introl.com/blog/fine-tuning-infrastructure-lora-qlora-peft-scale-guide-2025 · QLoRA≈LoRA — https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12633606/

---

## 4. Fine-tuning LOCAL sur Blackwell (sm_120, CUDA 13, torch 2.11) — CRITIQUE

### État des lieux des frameworks (juin 2026)
| Framework | Quant 4-bit | bitsandbytes requis ? | Statut Blackwell sm_120 | Risque "1er coup" |
|---|---|---|---|---|
| **torchtune** | NF4 via **torchao** (pur PyTorch) | **NON** | Suit PyTorch : si torch voit sm_120, torchao aussi | **Le plus faible** |
| **unsloth** | bitsandbytes NF4 + kernels Triton custom | OUI (mais kernels Blackwell maison) | Supporté officiellement (RTX 5060–5090), via installer dédié | Faible-moyen (pièges torch/cache) |
| **axolotl** | bitsandbytes | OUI | Dépend de bnb/torch | Moyen |
| **peft + bitsandbytes** | bitsandbytes NF4 | OUI | bnb sm_120 fragile selon CUDA/OS | **Le plus élevé sur CUDA 13** |

### bitsandbytes a-t-il des wheels sm_120 / cu13 ?
- **Pas fiable sur CUDA 13.** Les wheels bnb ciblent cu12.x ; sur driver CUDA 13 + sm_120 on voit `RuntimeError: CUDA error: no kernel image is available for execution on the device`. bnb a ajouté du support Blackwell récent (≥0.47, builds cu128/cu129) mais **les wheels cu13 / sm_120 ne sont pas garantis**, et il y a conflit "build CUDA 12.x vs driver 13.x". Sur **Linux + cu128** bnb peut marcher ; sur **CUDA 13 c'est le maillon faible**.
- **Conséquence** : éviter de faire reposer la réussite sur bitsandbytes. **torchtune QLoRA (torchao NF4) n'a PAS besoin de bitsandbytes** → c'est l'alternative pure-torch, la plus compatible Blackwell/CUDA 13.

### Pièges Blackwell connus (tous frameworks)
- torch **2.10+cu128 n'avait pas les bons kernels cuBLAS sm_120** ; fix = **torch ≥ 2.11.0** (cu128/cu129/cu130). (Le projet est déjà en torch 2.11+cu130 → OK.)
- `torch.compile`/inductor (Triton) peut **échouer à lancer sur sm_120** → désactiver : `TORCHDYNAMO_DISABLE=1` (+ `UNSLOTH_COMPILE_DISABLE=1` si unsloth).
- Cache compilé périmé après upgrade torch (`/tmp/unsloth_compiled_cache/`) → le purger.
- Triton **≥ 3.3.1** requis pour Blackwell (unsloth) ; xformers optionnel (compiler avec `TORCH_CUDA_ARCH_LIST="12.0"`), sinon fallback SDPA natif PyTorch.

### RECETTE la plus sûre du 1er coup (RECOMMANDÉE) : torchtune QLoRA, sans bitsandbytes
torchtune utilise `NF4Tensor`/`linear_nf4` de **torchao** (quantif 4-bit pure PyTorch). Aucune dépendance bnb → le seul prérequis est un torch qui voit sm_120 (déjà le cas).

```bash
# venv dédié, on garde le torch 2.11+cu130 déjà installé
python -m venv .ft && source .ft/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cu130   # ou réutiliser l'existant
pip install torchtune torchao
export TORCHDYNAMO_DISABLE=1                 # évite les kernels Triton qui crashent sur sm_120
# (optionnel) export CUDA_VISIBLE_DEVICES=0

# Mistral-Nemo 12B n'a pas de recette torchtune officielle prête : utiliser le builder generic
# 1) télécharger les poids base (HF) ; 2) copier une config QLoRA mono-GPU et l'adapter :
tune cp llama3_1/8B_qlora_single_device ./nemo12b_qlora.yaml
# éditer nemo12b_qlora.yaml : model=mistral-nemo, tokenizer, dataset (notre JSONL), 
#   batch_size=2, gradient_accumulation, compile=False, dtype=bf16
tune run lora_finetune_single_device --config ./nemo12b_qlora.yaml
```
- VRAM : un QLoRA 12B en NF4 tient sous 16 Go (réf. : QLoRA 40B sur 1 GPU Blackwell 32 Go ; 12B << ça). Garder `batch_size` petit + grad accumulation + `compile=False`.
- Sortie : un adapter LoRA (safetensors) → §5.

### RECETTE alternative (si on veut la vitesse unsloth)
```bash
# installer unsloth Blackwell-aware (venv + kernels custom)
curl -fsSL https://unsloth.ai/install.sh | sh        # crée un venv py3.13 avec kernels sm_120
# OU : pip install unsloth unsloth_zoo bitsandbytes "triton>=3.3.1"
export UNSLOTH_COMPILE_DISABLE=1 TORCHDYNAMO_DISABLE=1
rm -rf /tmp/unsloth_compiled_cache                   # purge cache si torch a bougé
```
Risque : dépend de bitsandbytes (fragile en CUDA 13). Si `no kernel image is available` → repasser sur torchtune.

Sources :
- torchtune QLoRA (NF4/torchao, sans bnb) — https://github.com/pytorch/torchtune/blob/main/docs/source/tutorials/qlora_finetune.rst · torchao finetuning — https://docs.pytorch.org/ao/stable/eager_tutorials/finetuning.html
- unsloth Blackwell — https://unsloth.ai/docs/blog/fine-tuning-llms-with-blackwell-rtx-50-series-and-unsloth · pièges issue #5154 — https://github.com/unslothai/unsloth/issues/5154 · NVIDIA blog — https://developer.nvidia.com/blog/train-an-llm-on-an-nvidia-blackwell-desktop-with-unsloth-and-scale-it/
- bitsandbytes sm_120 cassé — https://github.com/bitsandbytes-foundation/bitsandbytes/issues/1937 · releases — https://github.com/bitsandbytes-foundation/bitsandbytes/releases
- PyTorch sm_120 — https://github.com/pytorch/pytorch/issues/159207 · https://github.com/pytorch/pytorch/issues/164342

---

## 5. Export vers Ollama (adapter LoRA)

### Étapes
1. **Adapter → GGUF** avec llama.cpp :
```bash
python llama.cpp/convert_lora_to_gguf.py /chemin/adapter_dir --base /chemin/base_model --outfile nemo_fallacy_lora.gguf
```
2. **Modelfile** :
```
FROM mistral-nemo:12b
ADAPTER ./nemo_fallacy_lora.gguf
```
3. `ollama create codecitoyen-ft -f Modelfile` puis `ollama run codecitoyen-ft`.

Ollama accepte aussi un **dossier safetensors** directement dans `ADAPTER` (il convertit), pour les familles Llama/Mistral/Mixtral/Gemma — donc Mistral-Nemo OK.

### Pièges
- **Même base model obligatoire** dans `FROM` que celui utilisé pour l'entraînement, sinon "résultats erratiques". Vérifier que `mistral-nemo:12b` Ollama == base HF du fine-tune (mêmes poids/version).
- **Préférer un adapter NON quantifié** pour la conversion (les frameworks quantifient différemment) : exporter l'adapter LoRA en fp16/bf16, pas l'adapter QLoRA quantifié, avant `convert_lora_to_gguf`.
- Adapter LoRA appliqué à l'inférence : llama.cpp `--lora` / `--lora-scaled` ; via Ollama c'est transparent une fois le Modelfile créé.

Sources :
- Ollama import — https://docs.ollama.com/import · convert_lora_to_gguf — https://github.com/ggml-org/llama.cpp/blob/master/convert_lora_to_gguf.py · GGUF-my-LoRA — https://huggingface.co/blog/ngxson/gguf-my-lora · unsloth→Ollama — https://unsloth.ai/docs/basics/inference-and-deployment/saving-to-ollama

---

## 6. Plan d'action ordonné pour CodeCitoyen

1. **(Gratuit, immédiat) Constrained decoding** : passer la sortie en JSON-schema avec `enum` fermés (catégorie, verdict, sophisme MAFALDA + `aucun_sophisme`), via Ollama `format`/GBNF. Casse sur-étiquetage + noms inventés.
2. **(Gratuit) Prompt multi-tour + définitions** : intégrer les définitions des ~23 sophismes ; routine "candidat → vérifie définition → décide", abstention `aucun_sophisme`. Router opinion/doctrine hors du verdict factuel.
3. **(Gratuit) Verdicts calibrés** : NON_VERIFIABLE seulement si 0 preuve récupérée ; CONTESTE si preuves contradictoires ; exiger une URL/quote pour VRAI/FAUX ; ajouter un champ `confidence` + seuil d'abstention.
4. **(Quand 2-3 stabilisés) QLoRA local** : construire 300–600 exemples FR (distillés d'un gros modèle + correction manuelle sur nos VTT), **format = miroir exact du prompt d'inférence**, entraîner via **torchtune (torchao NF4, sans bitsandbytes)**, exporter en GGUF, charger dans Ollama via `ADAPTER`.

---

### Annexe — récap pièges Blackwell
- torch ≥ 2.11 obligatoire (OK ici). `TORCHDYNAMO_DISABLE=1`. bitsandbytes = maillon faible sur CUDA 13 → privilégier torchao/torchtune. Purger les caches compilés après tout upgrade torch. Adapter non quantifié pour l'export GGUF. Base model identique entre fine-tune et Ollama.
