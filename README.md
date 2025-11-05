## 🇫🇷 Code Citoyen : Fact-Checker Critique (V80.4)

## 🎯 Objectif du Projet

Ce projet implémente un système de Fact-Checking avancé, conçu pour l'analyse **critique et nuancée** d'affirmations issues de sources dynamiques (live vidéo, discussions).

L'outil dépasse la simple vérification binaire Vrai/Faux en utilisant une méthodologie basée sur **neuf catégories d'analyse** (JURIDIQUE, LOGIQUE, DOCTRINE, etc.) pour identifier :

* Les **erreurs factuelles** (FAUX).
* Les **erreurs de raisonnement** (BIAIS).
* La **complexité/le consensus** (CONTESTÉ, CONSENSUS_SCIENCE).

Le projet s'appuie sur des solutions **libres et locales** pour la partie ingestion (ASR) afin de garantir un outil sans coût d'API récurrent.

---

## ⚙️ Architecture Technique Actuelle (V80.4)

| Module | Rôle | Technologie | Note Critique |
| :--- | :--- | :--- | :--- |
| **`ingestion_pipeline.py`** | Acquisition du flux (URL vidéo, live) et **transcription audio-texte (ASR)**. | Python, **Whisper (ASR Libre)**, `yt-dlp` | Configurée en **mode CPU/Small** pour compatibilité GTX 970. |
| **`live_fact_checker.py`** | Orchestrateur, gestion de l'asynchronisme et affichage. | Python (`asyncio`) | Cœur du Fact-Checking Critique (Classification + Vérification spécialisée). |
| **Fact-Checking IA (Cœur)** | **Analyse critique et catégorisation (9 Catégories)**, recherche de sources et production du verdict. | Mistral AI (`mistral-tiny` ou similaire) | Méthodologie V80.x. |

---

## 🧠 Méthodologie du Verdict (Système V80.x - Le Fact-Checker Critique)

L'analyse est régie par un pipeline en deux phases (Classification puis Vérification spécialisée), permettant une grande granularité du verdict. Le système utilise neuf catégories pour router l'affirmation vers la vérification la plus appropriée (ex: **LOGIQUE** pour les sophismes, **DOCTRINE** pour les sujets complexes).

* **Format de sortie strict :** Le système contraint le modèle à générer une sortie structurée (Dict/JSON) pour faciliter l'intégration en temps réel.

---

## 🛠️ Installation et Configuration

### Pré-requis

* Python 3.8+
* Une clé API active de **Mistral AI**.
* **FFmpeg** (installé au niveau du système, **essentiel** pour l'extraction audio).

### Étapes d'Installation

1.  **Cloner le dépôt et créer l'environnement virtuel :**
    ```bash
    git clone [LIEN_VERS_VOTRE_DEPOT]
    cd CodeCitoyen
    python3 -m venv venv_code_citoyen_new
    source venv_code_citoyen_new/bin/activate
    ```

2.  **Installer les dépendances (y compris l'ASR) :**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Installer FFmpeg (Système) :**
    ```bash
    # Exemple pour Linux Debian/Ubuntu
    sudo apt install ffmpeg
    ```

4.  **Configurer la Clé API Mistral (Obligatoire) :**
    ```bash
    export MISTRAL_API_KEY="VOTRE_CLÉ_MISTRAL_ICI"
    ```

---

## 🚀 Utilisation (Test des Modules)

| Action | Commande | Description |
| :--- | :--- | :--- |
| **Tester la Transcription ASR** | `python ingestion_pipeline.py` | Valider l'acquisition vidéo/audio et la transcription locale (Whisper CPU). |
| **Lancer le Fact-Checker Core** | `python live_fact_checker.py` | Tester l'analyse critique sur les saisies texte. |
| **Lancer le Projet Complet** | `python main.py` | *(Commande future pour combiner Ingestion et Fact-Checking en flux.)* |
