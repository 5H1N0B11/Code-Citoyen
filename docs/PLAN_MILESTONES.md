# 🇫🇷 Feuille de Route et Jalons du Projet Codecitoyen (PLAN)
# 🇬🇧 Codecitoyen Project Roadmap and Milestones (PLAN)

## 🎯 OBJECTIF PRINCIPAL (CORE MISSION)

Développer un outil de Fact-Checking critique et automatisé pour l'analyse de contenu conversationnel (vidéos, podcasts, transcriptions), capable non seulement de vérifier les faits, mais surtout d'identifier les **biais logiques, la désinformation et les sophismes**, tout en maintenant la **mémoire du contexte** de la conversation.

---

## 🛠️ Phase 0 : Stabilisation du Core & Outils d'Analyse (High Priority)

| Tâche | Statut | Objectif Détaillé | Fichiers Clés |
| :--- | :--- | :--- | :--- |
| **0.1. Rigueur Statistique (Finalisation)** | À FAIRE | Forcer le moteur IA (Phase 2) à toujours utiliser la donnée statistique **la plus récente chronologiquement** pour la correction des affirmations. | `prompts_templates.py` |
| **0.2. Base de Biais Cognitifs** | ✅ **FAIT** | Créer une liste de biais/sophismes et l'intégrer au système prompt de la catégorie `LOGIQUE` pour améliorer la précision de l'identification. | `src/core/bias_list.py` |
| **0.3. Score de Confiance (Transparence)** | À FAIRE | Intégrer la récupération du score de confiance de l'API (si disponible) ou une estimation basée sur la complexité/multiplicité des sources. | `Analyse_Critique_IA.py` |
| **0.4. Stabilisation et Décorrélation IA** | ✅ **FAIT** | **Stabilisation complète du moteur Mistral.** Résolution des bugs d'import, gestion du rate limiting (Erreur 429) avec un `Semaphore(1)`. Le code est maintenant prêt pour le refactoring multi-provider. | `src/core/analyse_critique.py` |
| **0.5. Déploiement Git** | ✍️ **EN COURS** | Publier toutes les corrections et mises à jour de la Phase 0. | Tous |

---

## 🧠 Phase 1 : Mémoire, Contexte et Locuteur (Critical Priority)

| Tâche | Statut | Objectif Détaillé | Fichiers Clés |
| :--- | :--- | :--- | :--- |
| **1.1. Identification Locuteur** | À FAIRE | Adapter l'ingestion VTT pour extraire et associer l'ID du Locuteur (Speaker ID) à chaque affirmation. | `ingestion_pipeline.py` |
| **1.2. Mémoire Conversationnelle (Rolling Context)** | ✍️ **PROCHAINE ÉTAPE** | **Implémenter un mécanisme de mémoire.** Modifier la méthode `analyze` pour qu'elle accepte un historique des affirmations précédentes. Modifier les prompts pour injecter cet historique (ex: les 5 dernières affirmations) avant l'analyse de l'affirmation actuelle. | `src/core/analyse_critique.py`, `src/core/prompts_templates.py` |
| **1.3. Contexte Locuteur (Prompt)** | À FAIRE | Modifier les *system prompts* pour injecter le rôle ou le titre de la personne qui parle avant de classer ou de vérifier son affirmation. | `prompts_templates.py` |
| **1.4. Ingestion Horodatage** | À FAIRE | Récupérer et associer le timestamp précis de chaque affirmation dans les résultats. | `ingestion_pipeline.py` |

---

## 💻 Phase 2 : Architecture, Outils & Collaboration (Long Terme)

| Tâche | Statut | Objectif Détaillé | Fichiers Clés |
| :--- | :--- | :--- | :--- |
| **2.1. Outil de Contextualisation Code (Gemini)** | À DÉFINIR | Définir une méthode pour permettre à l'IA (Gemini/Moi) de lire l'intégralité des fichiers du projet à chaque nouvelle session pour maintenir la connaissance du code source. | NOUVEAU: Convention CLI |
| **2.2. Structuration de l'Historique de Discussion** | À DÉFINIR | Mettre en place un fichier structuré (JSON ou Markdown) pour sauvegarder notre historique de discussion et me le fournir pour une continuité parfaite. | NOUVEAU: `history.json` |
| **2.3. Mode Auto-Fact-Check (URL)** | À DÉVELOPPER | Ajouter la fonctionnalité pour analyser une vidéo YouTube directement via son URL. | Nouveau module |
| **2.4. Rapport Final Détaillé** | À DÉVELOPPER | Améliorer la lisibilité du rapport final : inclusion du Locuteur, de l'Horodatage et du Biais Précis. | `live_fact_checker.py` |
| **2.5. Interface Utilisateur (UI)** | À DÉVELOPPER | Création d'une interface Web simple (Streamlit ou Flask) pour l'interaction utilisateur. | NOUVEAU: Web |

---
