# 🇫🇷 CodeCitoyen : Fact-Checker en Temps Réel

## 🎯 Objectif du Projet

Ce projet implémente un système de vérification d'affirmations conçu pour un affichage en temps réel (type sous-titre ou "overlay"). Il combine la vitesse de la recherche web (simulée ici par une latence fixe de 2 secondes) avec la puissance d'analyse critique d'un modèle de langage (Mistral-tiny) pour produire un verdict immédiat, tranché et hautement formaté.

La méthodologie est conçue pour respecter les principes stricts d'exactitude, d'honnêteté et d'identification des biais, avec une sortie brute d'une seule ligne.

## ⚙️ Architecture Technique

| Composant | Rôle | Technologie |
| :--- | :--- | :--- |
| **`live_fact_checker.py`** | Orchestrateur, interface utilisateur et gestion de l'asynchronisme. | Python (`asyncio`) |
| **`fact_checker_api.py`** | Simulation de la recherche web et récupération des sources. | Python (`time.sleep`) |
| **`Analyse_Critique_IA.py`** | Moteur d'analyse critique pour le verdict (le cœur du système). | Mistral AI (modèle `mistral-tiny`) |

## 🧠 Méthodologie du Verdict (Système V18)

L'analyse critique est régie par un `SYSTEM_PROMPT` strict qui force le modèle d'IA à classer l'affirmation selon trois préfixes prioritaires.

### 1. Logique de Classification

Le modèle doit identifier la faille la plus pertinente selon l'ordre de priorité suivant :

| Préfixe | Condition d'Application | Exemple d'Affirmation |
| :--- | :--- | :--- |
| **VRAI :** | Si l'affirmation est une vérité simple ou une tautologie. **(Inclut une Règle de Sécurité pour les faits dangereux, ex: brûlures à 60°C).** | `Le feu brûle.` / `L'eau à 60°C brûle la peau.` |
| **BIAIS :** | Si l'affirmation contient une **erreur de raisonnement** (Sophisme). Le sophisme doit être nommé (ex: Appel au Peuple, Généralisation Abusive, Euphémisme). | `Tous les prêtres sont pédophiles.` |
| **FAUX :** | Si l'affirmation est une **erreur factuelle simple** ou une **croyance non fondée** (pseudo-science, ex: sourcellerie), et n'est pas un biais ou une vérité. | `Les moutons ont 5 pattes.` / `Trouver de l'eau avec un sourcier.` |

### 2. Formatage Strict de la Sortie

Le modèle est contraint de ne générer qu'une seule ligne de texte brut, sans aucun Markdown ni en-tête.

* `[PRÉFIXE] : [Explication concise du verdict ou du sophisme]`

## 🛠️ Installation et Configuration

### Pré-requis

* Python 3.8+
* Une clé API active de **Mistral AI**.

### Étapes d'Installation

1.  **Cloner le dépôt et créer l'environnement virtuel :**
    ```bash
    git clone [LIEN_VERS_VOTRE_DEPOT]
    cd CodeCitoyen
    python3 -m venv venv_code_citoyen
    source venv_code_citoyen/bin/activate
    ```

2.  **Installer les dépendances :**
    ```bash
    pip install mistralai
    ```

3.  **Configurer la Clé API (Obligatoire) :**
    Pour éviter de re-définir la clé à chaque session, ajoutez-la à votre fichier de profil (`~/.bashrc` ou `~/.zshrc`) :
    ```bash
    echo 'export MISTRAL_API_KEY="VOTRE_CLÉ_MISTRAL_ICI"' >> ~/.bashrc
    source ~/.bashrc
    ```

## 🚀 Utilisation

Exécutez le script principal dans votre terminal :

```bash
python3 live_fact_checker.py
