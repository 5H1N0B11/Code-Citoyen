## 💻 Référence des Commandes du Projet (`COMMANDS.md`)

Ce document liste les commandes essentielles pour l'installation, l'exécution et la maintenance de l'environnement virtuel et des dépendances du projet **Code Citoyen**.

### 0. ✅ Prérequis

- **Python 3.10+**
- **`pip`** et **`venv`** installés
- Des clés API valides pour Mistral et Groq

### 1. ⚙️ Gestion de l'Environnement Virtuel (`venv`)

| Action | Commande |
| :--- | :--- |
| Créer l'environnement | `python3 -m venv venv` |
| **Activer l'environnement** | `source venv/bin/activate` |
| Désactiver l'environnement | `deactivate` |
| Supprimer l'environnement | `rm -rf venv` |

---

### 2. 📦 Gestion des Dépendances

| Action | Commande |
| :--- | :--- |
| **Installer les dépendances** | `pip install -r requirements.txt` |
| Mettre à jour une librairie | `pip install --upgrade [nom_librairie]` |
| Forcer la réinstallation | `pip install --upgrade --force-reinstall [nom_librairie]` |
| Lister les dépendances | `pip freeze` |
| Mettre à jour `requirements.txt` | `pip freeze > requirements.txt` |

---

### 3. 🔑 Gestion de la Clé API Mistral

| Action | Commande |
| :--- | :--- |
| **Définir la Clé API** | `export MISTRAL_API_KEY="VOTRE_CLÉ_ICI"` |
| **Définir la Clé API Groq** | `export GROQ_API_KEY="VOTRE_CLÉ_ICI"` |
| Vérifier la clé | `echo $MISTRAL_API_KEY` |

---

### 4. ▶️ Exécution des Applications

| Action | Commande |
| :--- | :--- |
| **Lancer l'Interface Web (Recommandé)** | `python3 src/web/server.py` |
| **Lancer l'Interface Console (CLI)** | `python3 src/cli/console_app.py` |

---

### 5.  Gestion de Version (Git)

| Action | Commande |
| :--- | :--- |
| **Ajouter tous les changements** | `git add .` |
| **Créer un commit** | `git commit -m "Votre message de commit"` |
| **Pousser les changements** | `git push` |

---

### 6. 🗑️ Nettoyage (Facultatif)

| Action | Commande |
| :--- | :--- |
| Supprimer les fichiers de résultats | `rm src/results/*.json` |
| Supprimer le cache Python | `find . -type d -name "__pycache__" -exec rm -rf {} +` |
| Supprimer les logs | `rm *.log` |
