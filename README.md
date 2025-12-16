## 🇫🇷 Code Citoyen - Fact-Checker Critique

**Code Citoyen** est un outil d'analyse critique et de fact-checking conçu pour évaluer la véracité et la nature des affirmations issues de discours, d'articles ou de transcriptions. Il utilise des modèles de langage avancés (via l'API Mistral) pour classifier, analyser et fournir un rapport détaillé sur chaque affirmation.

## Fonctionnalités principales

-   **Analyse multi-sources** : Traitez du texte depuis une entrée manuelle, un fichier `.txt`, ou un fichier de sous-titres `.vtt`.
-   **Classification intelligente en 9 catégories** : Chaque affirmation est classée dans une catégorie précise (Statistique, Logique, Doctrine, Juridique, Consensus Scientifique, etc.) pour une analyse ciblée.
-   **Fact-checking avec sources** : Pour les affirmations factuelles, l'outil tente de fournir un verdict (VRAI, FAUX, CONTESTÉ) et de citer des sources crédibles.
-   **Détection de sophismes** : Identifie les arguments fallacieux courants (attaques *ad hominem*, homme de paille, etc.).
-   **Analyse de contexte** : Avant l'analyse, l'outil peut rechercher des informations sur les intervenants pour fournir un contexte global au modèle d'IA.
-   **Analyse VTT intelligente** : Le parser VTT est spécifiquement conçu pour gérer les transcriptions de direct (sous-titres défilants). Il fusionne intelligemment les fragments de texte qui se chevauchent pour reconstituer des phrases complètes et cohérentes. Cette méthode, basée sur une détection de suffixe/préfixe commun, est une alternative performante à des calculs plus lourds comme la **distance de Levenshtein**.
-   **Analyse VTT intelligente (Parser v3.1)** : Le parser VTT est spécifiquement conçu pour gérer les transcriptions de direct (sous-titres "défilants"). Il utilise le module `difflib` de Python pour détecter et fusionner intelligemment les fragments de texte qui se chevauchent. La version 3.1 intègre une détection heuristique des locuteurs (format "NOM:") et une logique de déduplication temporelle améliorée pour éviter les répétitions.
-   **Rapports détaillés** : Génère des rapports d'analyse complets au format JSON pour chaque session.
-   **Gestion d'historique** : Conserve un historique des analyses (`history.json`) pour fournir un contexte conversationnel lors des analyses suivantes.

## 🧠 Méthodologie d'analyse

L'outil fonctionne selon un pipeline en deux phases pour garantir une analyse fine et pertinente :

1.  **Phase 1 : Classification**
    Une première requête est envoyée à l'IA pour classifier l'affirmation dans l'une des neuf catégories prédéfinies. Cette étape permet d'orienter l'analyse.

2.  **Phase 2 : Analyse Spécialisée**
    Une seconde requête est effectuée avec un prompt système spécialisé, adapté à la catégorie déterminée. Par exemple, une affirmation classée `LOGIQUE` sera analysée avec un prompt axé sur la détection de sophismes, tandis qu'une affirmation `STATISTIQUE` sera traitée avec un prompt exigeant une vérification chiffrée et sourcée.

## Installation

### Pré-requis

* Python 3.8+
* Une clé API **Mistral AI** active.

### Étapes d'Installation

1.  **Cloner le dépôt et créer l'environnement virtuel :**
    ```bash
    git clone https://github.com/votre-repo/CodeCitoyen.git
    cd CodeCitoyen
    python3 -m venv venv
    source venv/bin/activate
    ```

2.  **Installer les dépendances Python :**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configurer la clé d'API Mistral :**
    L'outil nécessite une clé d'API pour fonctionner. Le moyen le plus sûr est de l'exporter comme variable d'environnement :
    ```bash
    export MISTRAL_API_KEY="VOTRE_CLE_API_MISTRAL"
    ```

## Utilisation

Le script principal est `src/live_fact_checker.py`. Lancez-le via le menu interactif :

```bash
python3 src/live_fact_checker.py
```

Suivez ensuite les instructions du menu pour choisir votre mode d'analyse :

-   **1. Mode interactif** : Analysez des phrases une par une.
-   **2. Mode batch** : Collez un bloc de texte contenant plusieurs affirmations.
-   **3. Mode fichier** : Analysez le contenu d'un fichier `.txt`.
-   **4. Mode VTT (simuler un direct)** : Analysez une transcription `.vtt` en simulant le rythme du direct. Ce mode propose de détecter les intervenants pour enrichir le contexte.
    -   **Note pour les intervenants** : Pour une identification automatique et fiable des interlocuteurs, il est recommandé de formater votre fichier VTT en incluant des balises `<v NOM>` avant le texte de la personne qui parle. Par exemple : `WEBVTT ... 00:00:10.500 --> 00:00:12.000 <v Jean-Luc Mélenchon> Bonjour à tous.` Si ces balises sont absentes, le programme tentera de deviner les noms à partir du nom du fichier.
-   **5. Mode par défaut** : Lance une analyse sur un jeu d'affirmations prédéfinies pour tester le système.

Les résultats sont affichés dans la console et sauvegardés au format JSON dans le dossier `src/results/`. Un fichier `history.json` est également créé pour conserver l'historique entre les sessions.

## Structure du projet

-   `src/` : Contient le code source de l'application.
    -   `core/` : Le cœur de la logique d'analyse.
        -   `orchestrator.py` : Gère le pipeline d'analyse en deux phases (classification puis analyse spécialisée).
        -   `ingestion_pipeline.py` : Fonctions pour parser les fichiers `.vtt`.
        -   `context_fetcher.py` : Fonctions pour deviner et rechercher le background des intervenants.
        -   `prompts_templates.py` : (Fichier non fourni) Contient probablement tous les prompts système utilisés par l'IA.
        -   `providers/` : (Dossier non fourni) Contient probablement l'abstraction pour les fournisseurs de modèles d'IA.
    -   `utils.py` : Fonctions utilitaires (validation, formatage, configuration).
    -   `results/` : Dossier où sont sauvegardés les rapports d'analyse JSON.
    -   `live_fact_checker.py` : Point d'entrée principal de l'application.
    -   `main.py` : **(Obsolète)** Ancien script de test, conservé pour archivage.
-   `data/` : Contient les données d'entrée (fichiers `.txt`, `.vtt`).
-   `docs/` : Contient la documentation du projet.
-   `requirements.txt` : Liste des dépendances Python.
-   `README.md` : Ce fichier.

## Contribution

Les contributions sont les bienvenues ! N'hésitez pas à ouvrir une *issue* pour signaler un bug ou proposer une amélioration, ou une *pull request* pour soumettre vos modifications.

---
*Documentation mise à jour le 14/11/2025.*
