## 💻 Référence des Commandes du Projet (`COMMANDS.md`)

Ce document liste les commandes essentielles pour l'installation, l'exécution et la maintenance de l'environnement virtuel et des dépendances du projet **Code Citoyen**.

### 1. ⚙️ Gestion de l'Environnement Virtuel (`venv`)

| Action | Commande |
| :--- | :--- |
| Créer l'environnement | `python3 -m venv venv_code_citoyen` |
| **Activer l'environnement** | `source venv_code_citoyen/bin/activate` |
| Désactiver l'environnement | `deactivate` |
| Supprimer l'environnement | `rm -rf venv_code_citoyen` |

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
| Vérifier la clé | `echo $MISTRAL_API_KEY` |

---

### 4. ▶️ Exécution et Tests

| Action | Commande |
| :--- | :--- |
| **Lancer l'application** | `python3 -m src.live_fact_checker` |
| Lancer le script de test `main` | `python3 -m src.main` |

---

### 5. 🗑️ Nettoyage (Facultatif)

| Action | Commande |
| :--- | :--- |
| Supprimer le fichier de test | `rm test_mistral.py` |
| Supprimer le cache | `rm -rf __pycache__` |
