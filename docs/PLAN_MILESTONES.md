# 🇫🇷 Feuille de Route et Jalons du Projet Codecitoyen (PLAN)
# 🇬🇧 Codecitoyen Project Roadmap and Milestones (PLAN)

## 🎯 OBJECTIF PRINCIPAL (CORE MISSION)

Développer un outil de Fact-Checking critique et automatisé pour l'analyse de contenu conversationnel (vidéos, podcasts, transcriptions), capable non seulement de vérifier les faits, mais surtout d'identifier les **biais logiques, la désinformation et les sophismes**, tout en maintenant la **mémoire du contexte** de la conversation.

---

## 🛠️ Phase 0 : Stabilisation du Core & Outils d'Analyse (High Priority)

| Tâche | Statut | Objectif Détaillé | Fichiers Clés |
| :--- | :--- | :--- | :--- |
| **0.1. Rigueur Statistique (Finalisation)** | ✅ **FAIT** | Forcer le moteur IA (Phase 2) à toujours utiliser la donnée statistique **la plus récente chronologiquement** pour la correction des affirmations. | `prompts_templates.py` |
| **0.2. Base de Biais Cognitifs** | ✅ **FAIT** | Créer une liste de biais/sophismes et l'intégrer au système prompt de la catégorie `LOGIQUE` pour améliorer la précision de l'identification. (La liste existe dans `src/core/bias_list.py`). | `src/core/bias_list.py` |
| **0.3. Score de Crédibilité (Pédagogie)** | ✅ **FAIT** | Intégrer un **Score de Crédibilité (0-100%)** généré par l'IA dans le verdict pour quantifier le degré de vérité ou de "dinguerie" de l'affirmation (ex: 0% = Mensonge total). | `prompts_templates.py` |
| **0.3b. Durcissement Analyse Doctrinale** | ✅ **FAIT** | Modifier le prompt `DOCTRINE` pour éviter le relativisme ("padamalgam") et forcer une vérification technique des termes (ex: totalitarisme) par rapport aux textes fondateurs. | `prompts_templates.py` |
| **0.4. Stabilisation et Décorrélation IA** | ✅ **FAIT** | **Stabilisation complète du moteur Mistral.** Résolution des bugs d'import, gestion du rate limiting (Erreur 429) avec un `Semaphore(1)`. Le code est maintenant prêt pour le refactoring multi-provider. | `src/core/analyse_critique.py` |
| **0.5. Documentation et Finalisation** | ✅ **FAIT** | Mettre à jour l'ensemble de la documentation du projet (`.md`) pour refléter l'état actuel du code et des fonctionnalités. | `README.md`, `docs/*.md` |

---

## 🧠 Phase 1 : Objectif "Analyse Live" (Critical Priority)

| Tâche | Statut | Objectif Détaillé | Fichiers Clés |
| :--- | :--- | :--- | :--- |
| **1.1. Identification Locuteur** | ✅ **FAIT** | Adapter l'ingestion VTT pour deviner les noms des locuteurs à partir du nom de fichier et permettre à l'utilisateur de les confirmer. | `live_fact_checker.py`, `src/core/context_fetcher.py` |
| **1.2. Mémoire Conversationnelle (Rolling Context)** | ✅ **FAIT** | Implémentation d'un `HistoryManager` pour conserver un historique des analyses et l'injecter comme contexte dans les nouvelles requêtes. | `live_fact_checker.py` |
| **1.3. Contexte Locuteur (Prompt)** | ✅ **FAIT** | Implémentation de `fetch_speaker_background` pour enrichir le prompt système avec des informations sur les intervenants. | `live_fact_checker.py`, `src/core/context_fetcher.py` |
| **1.4. Ingestion Horodatage** | ✅ **FAIT** | Récupérer et associer le timestamp précis de chaque affirmation dans les résultats (Intégré dans le JSON de sortie). | `ingestion_pipeline.py` |
| **1.5. Analyse VTT Intelligente** | ✅ **FAIT** | Refonte complète de la logique du mode VTT (v3.1) pour éliminer les répétitions et détecter les locuteurs. Le système construit désormais une transcription propre et analyse les phrases complètes séquentiellement. | `live_fact_checker.py`, `ingestion_pipeline.py` |

---

## 💻 Phase 2 : Architecture, Outils & Collaboration (Long Terme)

| Tâche | Statut | Objectif Détaillé | Fichiers Clés |
| :--- | :--- | :--- | :--- |
| **2.1. Outil de Contextualisation Code (Gemini)** | ✅ **FAIT** | Mise en place d'un script (`invoke`) qui fournit à l'IA l'ensemble des fichiers pertinents du projet à chaque session, assurant une connaissance complète et à jour du code source. | `invoke.yaml`, `tasks.py` |
| **2.2. Structuration de l'Historique de Discussion** | ✅ **FAIT** | Création et maintenance du fichier `docs/historique_discussion_gemini.md` qui sert de mémoire conversationnelle, résumant les objectifs, les problèmes résolus et les décisions prises à chaque session. | `docs/historique_discussion_gemini.md` |
| **2.3. Mode Auto-Fact-Check (URL)** | À DÉVELOPPER | Ajouter la fonctionnalité pour analyser une vidéo YouTube directement via son URL. | Nouveau module |
| **2.4. Rapport Final Détaillé** | À DÉVELOPPER | Améliorer la lisibilité du rapport final : inclusion du Locuteur, de l'Horodatage et du Biais Précis. | `live_fact_checker.py` |
| **2.5. Interface Utilisateur (UI)** | À DÉVELOPPER | Création d'une interface Web simple (Streamlit ou Flask) pour l'interaction utilisateur. | NOUVEAU: Web |

---
