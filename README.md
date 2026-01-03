## 🇫🇷 Code Citoyen - Fact-Checker Critique

**Code Citoyen** est un outil d'analyse critique et de fact-checking conçu pour évaluer la véracité et la nature des affirmations issues de discours, d'articles ou de transcriptions. Il utilise des modèles de langage avancés (via l'API Mistral) pour corriger, classifier et analyser chaque affirmation en temps réel.

## Fonctionnalités principales

-   **Analyse multi-sources** : Traitez du texte depuis une entrée manuelle, un fichier `.txt`, un fichier de sous-titres `.vtt` ou directement depuis une URL YouTube.
-   **Correction Intelligente de Transcription** : L'IA corrige d'abord les erreurs de transcription (ASR) en se basant sur le contexte avant d'analyser, garantissant une meilleure précision.
-   **Classification en 9 catégories** : Chaque affirmation est classée (Statistique, Logique, Doctrine, Juridique, Consensus Scientifique, etc.) pour une analyse pertinente.
-   **Fact-checking avec sources** : Pour les affirmations factuelles, l'outil fournit un verdict (VRAI, FAUX, CONTESTÉ, NON_VÉRIFIABLE) et tente de citer des sources crédibles.
-   **Détection de sophismes et de biais** : Identifie les arguments fallacieux et les biais cognitifs/rhétoriques.
-   **Contexte Riche** :
    -   **Global** : Recherche automatique du background des intervenants.
    -   **Conversationnel** : Maintient un historique "glissant" de la conversation pour comprendre les références.
-   **Analyse VTT intelligente** : Gestion avancée des fichiers de sous-titres (fusion des fragments, détection de locuteurs, simulation de direct).
-   **Rapports détaillés** : Génère des rapports JSON complets et sauvegarde l'historique de session.

## 🧠 Méthodologie d'analyse

L'outil utilise désormais une architecture unifiée **"Single-Phase Analysis"** pour maximiser la cohérence et la performance :

1.  **Prompt Système Unifié** : Au lieu de multiplier les appels, un unique prompt complexe (`COMBINED_SYSTEM_PROMPT`) instruit le modèle pour effectuer deux tâches simultanées :
    *   **Tâche 1 : Correction Conservatrice** : Correction des fautes de frappe ou d'écoute (ASR) sans altérer le sens ni les noms propres (sauf certitude absolue).
    *   **Tâche 2 : Analyse Critique** : Vérification des faits, détection des biais et classification.

2.  **Contexte Dynamique** : À chaque requête, le modèle reçoit :
    *   Le contexte global (qui parle ? quel est le sujet ?).
    *   L'historique immédiat des derniers échanges pour saisir les nuances de la conversation.

## Installation

### Pré-requis

* Python 3.10+
* Une clé API **Mistral AI** active.

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

3.  **Configurer la clé d'API Mistral :**
    Exporter la clé comme variable d'environnement :
    ```bash
    export MISTRAL_API_KEY="VOTRE_CLE_API_MISTRAL"
    ```

## Utilisation

Le script principal est `src/live_fact_checker.py`. Lancez-le via :

```bash
python3 src/live_fact_checker.py
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
    -   `live_fact_checker.py` : **Point d'entrée principal**. Orchestre l'application.
    -   `prompts.py` : Contient le `COMBINED_SYSTEM_PROMPT`, le "cerveau" de l'analyse.
    -   `core/` : Modules métier.
        -   `ingestion_pipeline.py` : Parsing avancé des VTT.
        -   `context_fetcher.py` : Récupération d'infos sur les speakers.
        -   `youtube_loader.py` : Téléchargement des sous-titres YouTube.
        -   `fact_checker.py` : *(Legacy)* Ancien module de recherche.
        -   `orchestrator.py` : *(Legacy)* Ancienne orchestration bi-phase.
    -   `utils.py` : Fonctions utilitaires.
    -   `results/` : Rapports JSON de sortie.
-   `data/` : Données d'entrée (VTT, TXT).
-   `docs/` : Documentation (Changelog, Milestones, Commands).

## Contribution

Les contributions sont les bienvenues ! Consultez les fichiers dans `docs/` pour comprendre la roadmap.

---
*Documentation mise à jour le 04/01/2026.*
