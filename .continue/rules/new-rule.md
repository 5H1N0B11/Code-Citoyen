# Contexte du Projet Codecitoyen

## 1. Objectif Principal
Le projet est un outil d'éducation civique pour le fact-checking et l'analyse critique d'affirmations. L'objectif est de fournir des analyses factuelles, critiques et sourcées sur des sujets de société. Le ton doit être pédagogique et neutre.

## 2. Environnement (TRÈS IMPORTANT)
Le projet DOIT TOUJOURS être exécuté dans l'environnement virtuel (venv) situé ici :
`venv_code_citoyen_new/`
Toutes les dépendances (comme `mistralai`, `googlesearch-python`) doivent être installées dans ce venv.

## 3. Architecture du Projet
Le projet est structuré comme suit :

* `live_fact_checker.py`: C'est le point d'entrée principal en ligne de commande. Il prend une affirmation en argument.
* `PLAN_MILESTONES.md`: Contient la feuille de route du projet.

* `src/core/`: **C'est le cœur de la logique métier.**
    * `analyse_critique.py`: Contient la logique principale d'analyse critique (où l'IA intervient).
    * `ingestion_pipeline.py`: Gère la recherche et la collecte de données (utilise `googlesearch`).
    * `fact_checker.py`: Gère la vérification des faits bruts.
    * `prompts_templates.py`: Stocke les modèles de prompts pour l'IA.
    * `bias_list.py`: Contient la liste des biais cognitifs.

* `src/utils/`: Contient les fonctions utilitaires.
    * `api_helpers.py`: (Probablement) Gère les appels concrets aux API (Mistral).
    * `error_handling.py`: Gère les erreurs et exceptions.

* `data/`: Contient les données d'entrée ou les ressources.
* `results/`: Contient les sorties et les rapports générés.
* `tests/`: Contient les tests unitaires.

## 4. Standards de Codage
* **Commentaires :** Le code doit être *extrêmement* commenté (presque ligne par ligne) car il a une vocation pédagogique.
* **Structure :** Le code doit rester simple, modulaire et facile à lire.
* **Bibliothèques Clés :** `mistralai` (pour l'IA), `googlesearch-python` (pour la recherche).