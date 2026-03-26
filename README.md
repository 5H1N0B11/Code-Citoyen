## 🇫🇷 Code Citoyen - Fact-Checker Critique

**Code Citoyen** est un outil d'analyse critique et de fact-checking conçu pour évaluer la véracité et la nature des affirmations issues de discours, d'articles ou de transcriptions. Il utilise des modèles de langage avancés (via l'API Mistral) pour corriger, classifier et analyser chaque affirmation en temps réel.

## ✨ Fonctionnalités principales

-   **Analyse multi-sources** : URL YouTube directes, fichiers `.vtt`, ou mode interactif en console.
-   **Moteur "Radar" à contexte dynamique** : Une boucle IA asynchrone surveille en continu la conversation pour détecter les changements de sujets et de sous-sujets, évitant à l'analyseur d'être perdu par les digressions.
-   **Correction ASR Intelligente et Désambiguïsation** : L'IA nettoie les bégaiements, corrige phonétiquement les noms propres mal transcrits (ex: "le loup" -> "le Louvre") et remplace les pronoms ("il a dit") par leurs sujets réels pour rendre le fact-checking possible sur les moteurs de recherche.
-   **Classification en 9 catégories** : Chaque affirmation est classée (Statistique, Logique, Doctrine, Juridique, Consensus Scientifique, etc.) pour une analyse pertinente.
-   **Fact-checking avec Recherche Google** : Les affirmations factuelles déclenchent des recherches web automatisées (via DDGS) pour extraire le contexte d'articles journalistiques récents avant de rendre un verdict.
-   **Détection de sophismes et de biais** : Identifie les arguments fallacieux et les biais cognitifs/rhétoriques.
-   **Interfaces synchronisées** : Une interface web moderne (Flask + AJAX) et un outil en ligne de commande (CLI) qui partagent exactement le même "cerveau" d'analyse.

## 🧠 Méthodologie d'analyse

L'outil utilise une architecture asynchrone **Hybride (Groq + Mistral)** pour allier vitesse, contexte profond, et respect des quotas d'API (Rate Limits) :

1.  **Moteur Radar (Background)** : Utilise Groq (Llama-3) avec un "Résumé Roulant" pour mettre à jour la thématique du débat toutes les minutes, pour un coût token quasi-nul.
2.  **Moteur de Sélection (Toutes les 15s)** : Groq lit la fenêtre temporelle, identifie la phrase la plus pertinente (priorité aux faits divers, lois, statistiques), la corrige et la désambiguïse.
3.  **Moteur de Fact-Checking** : L'affirmation propre est envoyée à Google pour trouver des sources web, puis le tout est compilé et envoyé à Mistral pour un verdict final précis et argumenté.

## Installation

### Pré-requis

* Python 3.10+
* Une clé API **Mistral AI** (`MISTRAL_API_KEY`) pour l'analyse profonde.
* Une clé API **Groq** (`GROQ_API_KEY`) pour la classification et le radar ultra-rapides.

### Étapes d'Installation

1.  **Cloner le dépôt et créer l'environnement virtuel :**
    ```bash
    git clone https://github.com/votre-repo/CodeCitoyen.git
    cd CodeCitoyen
    python3 -m venv .venv
    source .venv/bin/activate  # Linux/Mac
    # .venv\Scripts\activate   # Windows
    ```

2.  **Installer les dépendances Python :**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configurer les clés d'API :**
    Exporter les clés comme variables d'environnement :
    ```bash
    export MISTRAL_API_KEY="VOTRE_CLE_API_MISTRAL"
    export GROQ_API_KEY="VOTRE_CLE_API_GROQ"
    ```

## Utilisation

### 1. Interface Web (Recommandé)
Lancez le serveur Flask via :

```bash
python3 src/web/server.py
```

Suivez les instructions du menu interactif :

-   **1. Mode interactif** : Analyse phrase par phrase.
-   **2. Mode batch** : Analyse d'un bloc de texte collé.
-   **3. Mode fichier** : Analyse d'un fichier `.txt`.
-   **4. Mode VTT** : Simulation de direct depuis un fichier de sous-titres.
-   **5. Mode YouTube** : Téléchargement et analyse directe depuis une URL YouTube.
-   **6. Mode par défaut** : Test sur un jeu de données pré-établi.

Les résultats sont sauvegardés dans `src/results/`.

## Structure du projet

-   `src/` : Code source.
    -   `web/` : Interface Web (Serveur Flask, HTML, CSS, JS).
    -   `cli/` : Interface Console (`console_app.py`).
    -   `core/` : Le Cerveau du système.
        -   `orchestrator.py` : Chef d'orchestre IA (Mixte Groq/Mistral).
        -   `stream_engine.py` : Moteur asynchrone (Boucles Radar et Fact-Checking).
        -   `history_manager.py` : Gestion sécurisée de la mémoire d'analyse.
    -   `ingestion/` : Parsers et téléchargeurs (`vtt_parser.py`, `youtube_parser.py`).
    -   `prompts/` : L'Ingénierie de Prompts (`templates.py`, `bias_list.py`).
    -   `tools/` : Outils externes de recherche web (`web_search.py`, `context_fetcher.py`).
    -   `utils.py` : Fonctions utilitaires.
    -   `results/` : Rapports JSON de sortie.
-   `data/` : Données brutes (VTT de test, uploads).
-   `scripts/` : Scripts de traitement en masse (MLOps, évaluation LLM-as-a-Judge).
    -   `docs/` : Documentation interne du projet.

## Contribution

Les contributions sont les bienvenues ! Consultez les fichiers dans `docs/` pour comprendre la roadmap.

---
*Documentation mise à jour le 15/03/2026.*
