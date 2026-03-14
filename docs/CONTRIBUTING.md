# Guidelines et Standards de Contribution

Ce document définit les normes et bonnes pratiques pour contribuer au projet **Code Citoyen**.

## 🏗 Architecture du Code

### 1. Architecture Modulaire Hybride (V2)
Le projet utilise une architecture asynchrone séparant la Sélection/Classification (Groq) de l'Analyse Critique (Mistral).
- **Dossiers Clés** : `src/core/` (moteurs), `src/prompts/` (ingénierie textuelle).
- **Principe** : Toute nouvelle règle d'analyse doit être intégrée dans `src/prompts/templates.py`. La logique d'extraction de contexte doit rester découplée de l'analyse (voir `stream_engine.py`).

### 2. Point d'Entrée
- Le projet dispose de deux points d'entrée officiels : `src/web/server.py` (Flask) et `src/cli/console_app.py` (Console).
- **Orchestrateur** : Les deux interfaces doivent obligatoirement utiliser l'instance `AnalysisOrchestrator` de `src/core/orchestrator.py` pour garantir la même intelligence métier.

### 3. Gestion Asynchrone
- Utilisez toujours `asyncio` pour les opérations I/O (appels API, réseau).
- Utilisez `tenacity` pour gérer les retries (Rate Limiting 429).
- Le serveur web utilise un thread d'arrière-plan dédié pour la boucle asyncio (`background_loop`). Ne bloquez jamais le thread principal de Flask.

## 📝 Standards de Documentation

- **Mise à jour** : Toute modification fonctionnelle doit être répercutée dans `README.md` et `docs/CHANGELOG.md`.
- **Langue** : La documentation principale est en **Français**.
- **Commentaires** : Le code doit être commenté en Français ou Anglais (cohérence locale).

## 🧪 Tests

- Ajoutez des cas de test pour les nouvelles fonctionnalités.
- Vérifiez que vos modifications ne brisent pas le parsing VTT (`src/ingestion/vtt_parser.py`).
- Exécutez `pytest` à la racine pour valider la suite de tests unitaires.

## 🔄 Workflow Git

1. Créez une branche pour votre feature.
2. Testez localement avec `python3 src/cli/console_app.py` (Mode 5 : Par défaut).
3. Soumettez votre PR.
