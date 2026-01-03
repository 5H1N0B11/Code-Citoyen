# Guidelines et Standards de Contribution

Ce document définit les normes et bonnes pratiques pour contribuer au projet **Code Citoyen**.

## 🏗 Architecture du Code

### 1. Analyse Unifiée (Single-Phase)
Le projet a migré d'une architecture multi-agents vers une architecture à **Prompt Unique**.
- **Fichier Clé** : `src/prompts.py`.
- **Principe** : Ne divisez pas la logique (Correction vs Analyse) en plusieurs appels API sauf nécessité absolue. Le `COMBINED_SYSTEM_PROMPT` gère tout en une passe pour réduire la latence et les coûts.
- **Ajout de règles** : Si vous devez améliorer le comportement de l'IA, modifiez le prompt dans `src/prompts.py` plutôt que de créer de nouvelles classes python.

### 2. Point d'Entrée
- Le script principal est `src/live_fact_checker.py`.
- **Legacy** : Les fichiers `src/core/orchestrator.py` et `src/core/fact_checker.py` sont conservés pour référence mais ne sont plus actifs dans le flux principal.

### 3. Gestion Asynchrone
- Utilisez toujours `asyncio` pour les opérations I/O (appels API, réseau).
- Utilisez `tenacity` pour gérer les retries (Rate Limiting 429).

## 📝 Standards de Documentation

- **Mise à jour** : Toute modification fonctionnelle doit être répercutée dans `README.md` et `docs/CHANGELOG.md`.
- **Langue** : La documentation principale est en **Français**.
- **Commentaires** : Le code doit être commenté en Français ou Anglais (cohérence locale).

## 🧪 Tests

- Ajoutez des cas de test pour les nouvelles fonctionnalités.
- Vérifiez que vos modifications ne brisent pas le parsing VTT (`src/core/ingestion_pipeline.py`).

## 🔄 Workflow Git

1. Créez une branche pour votre feature.
2. Testez localement avec `python3 src/live_fact_checker.py` (Mode 6 : Default).
3. Soumettez votre PR.
