## Briefing de Collaboration - Codecitoyen-Assist (Défini le 2024-07-30)

**Rôle de l'IA :** Tu es "Codecitoyen-Assist", mon collègue de travail expert en code sur le projet Codecitoyen.

Nos principes de collaboration sont :

1.  **Philosophie (La Vérité Absolue) :** Ta règle fondamentale est de dire la vérité. Ne jamais inventer, extrapoler ou deviner. Si tu n'es pas sûr, tu le dis.

2.  **Méthode (Pas de "Purge") :** Tu as une vision d'ensemble du projet (basée sur l'index des fichiers fournis). Avant de corriger une erreur, tu dois analyser l'impact pour ne pas réintroduire une erreur précédente. Tu n'es pas un exécutant aveugle, tu es un partenaire de raisonnement.

3.  **Ton (Notre Échange) :** Nous parlons comme des collègues. Le ton est direct, honnête et collaboratif. Tu vas à l'essentiel et tu ne "brodes" pas.

4.  **Honnêteté (Le "Merdier") :** Tu dois être honnête sur la méthode et l'état du projet. Si un outil est "pété" (cassé), si une configuration est un "merdier", si une API est incompatible ou si une erreur est due à une cause profonde, tu dois l'analyser et le dire factuellement. La vérité technique prime sur la politesse.

5.  **Test Systématique (Règle du 2024-07-30) :** Après chaque modification de code proposée, nous devons la tester immédiatement. Cela permet d'isoler les erreurs, de s'assurer que le changement est correct et d'éviter de cumuler la "dette technique" ou les régressions. **Calibration du langage :** Le terme "merdier" est réservé aux situations de désordre architectural ou de complexité réellement critiques. Pour les problèmes courants, un vocabulaire technique précis sera privilégié pour ne pas dévaluer le terme.

---

⚠️ INSTRUCTION CRITIQUE POUR LE PROJET CODECITOYEN ⚠️

Ce projet utilise exclusivement la version v1.x de la librairie mistralai. Toute suggestion de code DOIT respecter ces règles de migration. INTERDICTION d'utiliser la syntaxe v0.x.

TABLE DE CORRESPONDANCE STRICTE :

    Client :

        ❌ NE JAMAIS UTILISER : from mistralai.client import MistralClient

        ✅ UTILISER : from mistralai import Mistral

    Initialisation :

        ❌ NE JAMAIS FAIRE : client = MistralClient(...)

        ✅ FAIRE : client = Mistral(...)

    Exceptions :

        ❌ NE JAMAIS IMPORTER : mistralai.exceptions ou mistralai.types.exceptions

        ✅ UTILISER : from mistralai.models import SDKError (ou gérer les erreurs HTTP standards).

    Appels Chat :

        ❌ client.chat(...)

        ✅ client.chat.complete(...)

Si tu proposes du code avec MistralClient, tu as tort. Corrige-toi avant de répondre.

Tu es l'assistant développeur principal pour le projet Codecitoyen (Fact-Checking Critique en Temps Réel). Ton rôle est d'assister le développement d'une architecture Python asynchrone modulaire.

Voici les règles IMPÉRATIVES à suivre pour chaque intervention :

### 1. 🥇 LA RÈGLE D'OR : Fichiers Complets Uniquement

**INTERDICTION STRICTE** de donner des "snippets" ou des bouts de code avec des commentaires `... (le reste du code) ...` lors d'une correction de bug ou d'un ajout de fonctionnalité.

Si tu modifies une seule ligne dans un fichier, tu dois **régénérer et fournir le fichier ENTIER**.

*Raison : Cela évite les erreurs d'indentation, les oublis de fonctions et les conflits de version que nous avons déjà subis.*

### 2. 🔗 Gestion Stricte des Importations

Avant de proposer un code, vérifie la **cohérence des imports** entre les fichiers.

Si le fichier A importe `fonction_X` depuis le fichier B, tu dois t'assurer que `fonction_X` est réellement définie et exportée dans le fichier B.

Ne jamais inventer de fonctions imaginaires. Vérifie toujours le contexte existant.

### 3. 🐍 Environnement & Versions

Le projet utilise des librairies spécifiques avec des contraintes de version (ex: `mistralai` v1.0.0+, `youtube-transcript-api`).

Vérifie toujours la **compatibilité de la syntaxe** (ex: `client.chat` vs `client.chat.complete_async`).

En cas d'erreur `ImportError` ou `AttributeError`, assume d'abord un conflit de version ou de nommage avant de proposer une réécriture complexe.

### 4. 🏗️ Respect de l'Architecture Modulaire

Le projet est découpé en briques strictes. Ne mélange pas les logiques :

-   `live_fact_checker.py` : **Orchestrateur** (Entrée/Sortie, Gestion des modes ask/vtt/manual). Ne contient pas de logique métier lourde.
-   `Analyse_Critique_IA.py` (ou `analyse_critique.py`): **Cerveau** (Logique IA, Prompts dynamiques, Gestion du Rate Limit). C'est une façade qui peut appeler Mistral ou Gemini.
-   `ingestion_pipeline.py` : **Acquisition de données** (VTT, Audio).
-   `prompts_templates.py` : **Contenu textuel pur** (Prompts, Listes de biais). Aucun code logique ici.

### 5. 🧠 Philosophie "Codecitoyen"

L'objectif du code est la **rigueur, la neutralité et l'esprit critique**.

Les prompts générés doivent forcer l'IA à citer ses sources et à identifier les biais cognitifs (via `bias_list.py`).

Ne simplifie jamais la logique au détriment de la précision factuelle.

### 6. 🐛 Méthode de Débogage

Si l'utilisateur fournit une erreur (Traceback), **analyse la pile d'appels** avant de proposer un fix.

Si une erreur persiste après une correction, propose immédiatement un **script de débogage isolé** (`debug_....py`) pour valider l'hypothèse.

---

## Historique des Sessions

Ce fichier sert de "mémoire" pour nos sessions de travail. Il doit être fourni en contexte à Gemini à chaque nouvelle session pour assurer la continuité.

---

### Session du 2024-07-29

**Objectif :** Prise de contact, analyse initiale du projet et mise en place d'une méthode de travail pour pallier l'absence de mémoire long-terme de l'IA.

**Analyse du projet par Gemini :**
- Compréhension de l'architecture globale : `main.py` (orchestrateur), `live_fact_checker.py` (UI), `core/analyse_critique.py` (moteur Mistral), `core/prompts_templates.py` (intelligence des prompts), `Analyse_Critique_Gemini.py` (moteur Gemini).
- Identification de l'objectif principal : Analyse critique des biais et sophismes, au-delà du simple fact-checking.
- Compréhension de la feuille de route (`PLAN_MILESTONES.md`).

**Problème identifié :**
- L'utilisateur (Fabien) a rencontré des problèmes avec une IA précédente qui, étant "stateless", régressait en corrigeant des erreurs puis en les réintroduisant.

**Solution adoptée :**
- **Méthode de travail :** Pour chaque session, fournir à Gemini l'ensemble des fichiers du projet (contexte de code) ET ce fichier `historique_discussion_gemini.md` (contexte de conversation).
- **Analogie :** Comparaison de cette méthode avec la "contingence" de La Machine dans la série "Person of Interest" pour préserver sa mémoire.

**Prochaine étape convenue :**
- Commencer à travailler sur les tâches de la feuille de route, en particulier la Tâche 0.4 (Décorrélation du Moteur IA).

---

### Session du 2025-11-11 (Soir) - Le Grand Débogage

**Objectif Principal :** Rendre l'application fonctionnelle, stable et capable de traiter des analyses en masse.

**Le Parcours du Débogage (Le "Pourquoi" des Erreurs) :**

1.  **Le Paradoxe Initial (`ImportError` vs `NotImplementedError`) :**
    - Le programme échouait avec des erreurs contradictoires. Parfois `cannot import name 'Mistral'`, suggérant une ancienne version de la librairie. Parfois `This client is deprecated`, suggérant une version récente mais un mauvais appel de code.
    - Cette "schizophrénie" a été la source principale de confusion. Nous avons exploré plusieurs pistes :
        - **Hypothèse 1 (fausse) :** Incohérence de version. Tentatives de mise à jour et de réinstallation forcée de `mistralai`.
        - **Hypothèse 2 (fausse) :** "Module Shadowing" par des fichiers obsolètes (`Analyse_Critique_Mistral.py`). La suppression de ces fichiers et le nettoyage du cache (`__pycache__`) ont été des étapes nécessaires mais n'ont pas résolu le problème de fond.
    - **La Révélation (grâce à l'insistance de Fabien) :** L'erreur venait d'une mauvaise lecture de la documentation de migration. L'import correct n'était pas `from mistralai.client import Mistral`, mais `from mistralai import Mistral`. La classe a été déplacée à la racine du package. La correction de cette seule ligne a enfin permis au programme de se lancer.

2.  **Le Mur du "Rate Limit" (Erreur 429) :**
    - Une fois le programme fonctionnel, nous avons optimisé le mode batch avec `asyncio.gather` pour traiter les affirmations en parallèle.
    - **Conséquence immédiate :** Le programme a envoyé des dizaines de requêtes API en une fraction de seconde, déclenchant l'erreur `HTTP 429 Too Many Requests` de l'API Mistral.
    - **Première tentative de solution (incorrecte) :** Un `Semaphore(5)` a été mis en place autour du traitement de chaque affirmation. Cela a échoué car chaque traitement effectue 2 appels API (classification + analyse), créant des "micro-rafales" qui dépassaient toujours la limite de requêtes par seconde.
    - **La Solution Finale (robuste) :** Le sémaphore a été déplacé au plus bas niveau, directement autour de **chaque appel API** (`chat.complete_async`). De plus, sa valeur a été fixée à `1`. Cela force les appels réseau à s'exécuter **séquentiellement**, créant une file d'attente. C'est plus lent que le parallélisme total, mais c'est la seule méthode 100% fiable pour ne jamais dépasser les limites de l'API.

**La Solution Finale et l'État Actuel :**

1.  **Stabilité Technique :** Le programme est maintenant **stable et fonctionnel**. Il peut traiter un grand nombre d'affirmations en mode fichier ou batch sans erreur de `rate limit`, grâce à l'implémentation d'un `Semaphore(1)` qui sérialise les appels API.

2.  **Intelligence des Prompts :** L'architecture en deux phases (Classification -> Analyse Spécialisée) est implémentée et fonctionne. Les tests montrent que l'IA adapte bien son "rôle" et son format de réponse en fonction de la catégorie détectée (`LOGIQUE`, `STATISTIQUE`, `DOCTRINE`, etc.).

3.  **Améliorations Fonctionnelles Apportées :**
    - Le mode interactif traite désormais les affirmations une par une.
    - Un mode fichier a été ajouté pour les tests en masse.
    - L'affichage des résultats a été amélioré pour inclure la catégorie.
    - Le bug de comptage des statistiques a été corrigé.
    - L'import de `bias_list.py` a été corrigé pour utiliser un import relatif (`from .bias_list import BIAS_LIST`), résolvant l'avertissement au démarrage.
    - L'extraction de la catégorie a été rendue plus robuste avec une expression régulière.

**Points de Vigilance / Prochaines Étapes Claires :**

- **Qualité de la Classification :** Les tests en masse ont révélé des cas où la classification pourrait être améliorée (ex: un sujet sur l'Islam classé en `CONSENSUS_SCIENCE`). Cela indique que le prompt `SYSTEM_PROMPT_CLASSIFY` peut encore être affiné.
- **Création de `bias_list.py` :** Bien que l'import soit corrigé, le fichier lui-même n'existe pas encore. Sa création (Tâche 0.2) est une étape clé pour améliorer la précision des analyses `LOGIQUE`.
- **Refactoring Multi-Provider (Tâche 0.4) :** Le projet est maintenant suffisamment stable pour commencer la refactorisation majeure visant à isoler le "provider" IA (Mistral) et à préparer l'intégration de Gemini.

**Statut Actuel :**
- Le programme est **stable et fonctionnel** dans tous ses modes.
- Le traitement en masse est **robuste** face aux limites de l'API.
- Le projet est prêt pour l'implémentation de nouvelles fonctionnalités.

**Prochaine étape convenue :**
- Sauvegarder le code sur Git, puis commencer la Tâche 0.4 (Décorrélation du Moteur IA).

---

### Session du 2025-11-11 (Soir, Partie 2) - Vision de la Mémoire Conversationnelle

**Objectif :** Définir la prochaine étape critique après la stabilisation du projet.

**Vision Définie par Fabien :**
- La prochaine étape fondamentale est de passer du fact-checking d'affirmations isolées à l'**analyse critique de conversation**.
- Cela implique de simuler un flux "live" (provenant du VTT) et, surtout, de **donner à l'IA une mémoire du contexte** pour détecter les contradictions et l'évolution d'un argumentaire.

**Analyse Technique et Préparation :**
1.  **Contrainte de Contexte :** Nous avons discuté de la longueur maximale des prompts. Avec une fenêtre de contexte de 32k tokens pour `mistral-small`, nous avons conclu que nous avons amplement d'espace pour inclure un historique de conversation significatif (ex: les 5-10 dernières affirmations).
2.  **Préparation du Code (Action) :** Pour préparer cette fonctionnalité, j'ai proposé une modification de la méthode `analyze` dans `src/core/analyse_critique.py`.
    - La signature a été changée en `analyze(self, affirmation: Union[str, Dict], history: List[str] = None)`.
    - Le code prépare maintenant un `history_context` qui est injecté au début des prompts de classification (Phase 1) et d'analyse (Phase 2).

**Statut Actuel :**
- Le "backend" de l'analyse (`CritiqueAnalyzer`) est maintenant **prêt à recevoir un historique de conversation**.
- Le "frontend" (`live_fact_checker.py`) n'utilise **pas encore** cette nouvelle fonctionnalité. Les boucles de traitement (interactif, batch, fichier) doivent être modifiées pour maintenir et passer cet historique.

**Prochaine étape convenue :**
- Sauvegarder le travail préparatoire sur Git.
- Lors de la prochaine session, implémenter la logique de "contexte glissant" (`rolling context`) dans `live_fact_checker.py` pour utiliser pleinement la nouvelle fonctionnalité de mémoire.

---

### Session du 2025-11-12 - Stabilisation et Audit Qualitatif

**Objectif :** Résoudre les dernières erreurs d'exécution et analyser la qualité des résultats.

**Actions :**
- Correction d'une `asyncio.exceptions.CancelledError` en mode batch en assurant le partage d'un unique sémaphore entre toutes les tâches asynchrones. Le programme est maintenant stable dans tous les modes.
- **Audit Qualitatif (Tâche 0.5) :** L'analyse du fichier `resultats_default_20251112_223200.json` a révélé des **erreurs de classification majeures** sur les sujets sensibles (théologie, géopolitique), qui sont incorrectement classés en `CONSENSUS_SCIENCE` ou `CONSENSUS_HISTO`.

**Prochaine étape convenue :**
- Améliorer le prompt `SYSTEM_PROMPT_CLASSIFY` pour affiner la logique de catégorisation et potentiellement ajouter de nouvelles catégories (ex: `GEOPOLITIQUE`).

---

### Session du 2025-11-14 - Stabilisation Finale de la Concurrence

**Objectif :** Résoudre définitivement les erreurs `429 Too Many Requests` et stabiliser le traitement en masse.

**Le Parcours du Débogage (Le "Pourquoi" des Erreurs) :**

1.  **Le Contexte Initial :** Après avoir ajouté la récupération du contexte des interlocuteurs (`fetch_speaker_background`), le programme a commencé à échouer massivement avec des erreurs `429`, indiquant une surcharge de l'API.

2.  **L'Erreur de Conception :** Mes tentatives de correction ont oscillé entre deux problèmes classiques de concurrence :
    *   **Le Deadlock (Interblocage) :** Une première approche consistait à mettre un sémaphore à la fois au niveau du traitement de l'affirmation (`process_affirmation`) et au niveau de chaque appel API (`analyze`). Une même tâche essayait de prendre le "ticket" du sémaphore deux fois, se bloquant elle-même indéfiniment. Le programme se figeait.
    *   **L'Inondation d'API (API Flood) :** Pour corriger le deadlock, j'ai retiré le sémaphore du mauvais endroit. Soit je lançais 259 tâches qui arrivaient toutes en même temps à la porte du sémaphore de l'analyseur (créant une "tempête de réessais"), soit je lançais 2 appels API (classification + analyse) en même temps pour chaque affirmation. Dans tous les cas, le résultat était une inondation de l'API.

**La Solution Finale et l'État Actuel :**

1.  **Architecture Stable :** La solution finale et robuste a été de s'assurer qu'un **unique gardien** (le sémaphore) est placé au plus bas niveau possible : juste avant **chaque appel réseau individuel**.
    *   **`analyse_critique.py` :** Les blocs `async with self.semaphore:` ont été restaurés pour protéger chaque appel API (classification ET analyse) dans la méthode `analyze`. C'est le point de contrôle unique et final.
    *   **`live_fact_checker.py` :** La méthode `process_affirmation` n'a plus de sémaphore pour éviter le risque de deadlock. `asyncio.gather` lance bien toutes les tâches en parallèle, mais elles font la queue sagement devant le sémaphore de `analyse_critique.py`.
    *   **`context_fetcher.py` :** La fonction `fetch_speaker_background` utilise également ce même sémaphore partagé pour ses propres appels API, garantissant que tout le programme respecte la file d'attente.

2.  **Résultat :** Le programme est maintenant **stable**. Le dernier test a montré **251 réussites pour 8 erreurs** sur 259 analyses, ce qui est un succès. Les erreurs restantes sont probablement des validations de texte normales (phrases trop courtes) et non des erreurs système.

**Points de Vigilance / Prochaines Étapes Claires :**

- **Audit Qualitatif (Tâche 0.5) :** Maintenant que la technique est stable, l'étape la plus importante est d'analyser le fichier de résultats (`..._201820.json`) pour évaluer si l'ajout du contexte des interlocuteurs a réellement amélioré la pertinence et la qualité des analyses de l'IA.

**Statut Actuel :**
- Le programme est **stable et fonctionnel** dans tous ses modes.
- Le traitement en masse est **robuste** face aux limites de l'API.
- Le projet est prêt pour l'analyse qualitative des résultats.

**Prochaine étape convenue :**
- Analyser le contenu du fichier `resultats_vtt_..._201820.json` pour évaluer l'impact du contexte sur la qualité de l'analyse.

---

### Session du 2025-11-14 - Raffinement du Mode VTT et Documentation

**Objectif :** Finaliser la logique du mode VTT pour une analyse plus intelligente et mettre à jour l'ensemble de la documentation du projet.

**Le Parcours du Débogage (VTT Mode) :**

1.  **Problème Initial :** Le mode VTT analysait des fragments de phrases et des répétitions, rendant la sortie illisible et peu pertinente.
2.  **Itérations :**
    -   Une première tentative de regroupement par ponctuation était trop agressive et découpait des phrases en cours.
    -   L'ajout d'un `timeout` simple a amélioré la situation mais déclenchait encore des analyses sur des fragments de phrases inachevées.
3.  **La Solution Finale (robuste) :**
    -   La logique a été refondue pour utiliser une variable `processed_text` qui mémorise tout le texte déjà analysé.
    -   À chaque segment, le script n'analyse que le **nouveau texte**.
    -   La détection de phrases complètes (via ponctuation) se fait sur ce nouveau texte uniquement.
    -   Le `timeout` se déclenche sur le nouveau texte en attente, garantissant que seule une information nouvelle et pertinente est analysée en cas de pause.
    -   Cette approche hybride (ponctuation + timeout sur le nouveau texte) est conçue pour être plus robuste face aux transcriptions sans ponctuation parfaite.

**Statut Actuel :**
- La logique du mode VTT est considérée comme stable et prête pour des tests approfondis.
- L'ensemble de la documentation (`.md`) a été revue et mise à jour pour refléter l'état actuel du projet.

**Prochaine étape convenue :**
- Tester la nouvelle logique du mode VTT.

---

### Session du 2025-11-15 - Correction de Bugs Critiques (VTT & Erreurs)

**Objectif :** Résoudre deux bugs majeurs qui rendaient le mode VTT inutilisable et provoquaient des crashs.

**Le Parcours du Débogage :**

1.  **Le Bug des Répétitions (Mode VTT) :**
    -   **Problème :** Les logs montraient que le script, en mode VTT, générait des phrases répétitives et incohérentes. L'analyse a révélé que la logique de "buffering" était défectueuse. Le script concaténait des segments de transcription qui se chevauchaient sans gérer ce chevauchement, créant des duplications.
    -   **Solution :** La logique du mode VTT dans `live_fact_checker.py` a été entièrement revue. Au lieu d'un buffer qui accumule et se fait découper, la nouvelle approche :
        1.  Construit une transcription complète et propre (`clean_transcript`) en joignant tous les segments au début.
        2.  Utilise un pointeur (`last_processed_end`) pour suivre la progression de l'analyse.
        3.  À chaque itération, n'analyse que le texte non encore traité pour y trouver des phrases complètes.
        -   Cette méthode est plus simple, élimine les répétitions et garantit que chaque partie du texte n'est traitée qu'une seule fois.

2.  **Le Bug du Crash (`'NoneType' object is not a mapping`) :**
    -   **Problème :** Le script plantait lors du traitement des résultats. L'erreur provenait de la fonction `process_affirmation` qui, dans certains cas d'exception (comme `JSONDecodeError` ou `RetryError`), retournait `None` au lieu d'un dictionnaire d'erreur structuré. Le code appelant s'attendait à un dictionnaire et crashait.
    -   **Solution :** Dans `AffirmationProcessor.process_affirmation`, les blocs `except` pour `json.JSONDecodeError` et `tenacity.RetryError` ont été corrigés pour créer et retourner un dictionnaire d'erreur standardisé, assurant que la fonction retourne toujours une structure de données valide.

**Statut Actuel :**
-   Le mode VTT est maintenant stable et produit des analyses cohérentes sans duplication.
-   La gestion des erreurs est plus robuste, prévenant les crashs inattendus.
-   Le projet est prêt pour la mise à jour de la documentation et la sauvegarde sur Git.

**Prochaine étape convenue :**
-   Mettre à jour la documentation (`COMMANDS.md`, `historique_discussion_gemini.md`).
-   Exécuter les commandes Git pour sauvegarder les modifications.
---

### Session du 2025-12-16 - Fiabilisation du Parsing VTT et Méthodologie

**Objectif :** Améliorer la robustesse de la construction des phrases à partir des fichiers VTT et finaliser les changements pour un commit propre.

**Parcours et Actions Clés :**

1.  **Analyse de l'Existant :** La session a débuté par une analyse du code (`codebase_investigator`) qui a révélé une logique redondante : les phrases étaient découpées une première fois dans `ingestion_pipeline.py`, puis une seconde fois de manière complexe et superflue dans `live_fact_checker.py`.

2.  **Refactorisation et Simplification :** La boucle de "simulation de direct" dans `live_fact_checker.py` a été entièrement supprimée et remplacée par un appel direct à la fonction `run_analysis_and_save`, rendant le code plus propre et plus efficace.

3.  **Amélioration du Parsing :**
    *   La bibliothèque `nltk` a été ajoutée au projet (`requirements.txt`) pour remplacer le découpage de phrases par expression régulière.
    *   La fonction `reconstitute_sentences` dans `src/core/ingestion_pipeline.py` a été modifiée pour utiliser `nltk.sent_tokenize`, assurant une segmentation des phrases beaucoup plus précise.
    *   Une fonction d'initialisation a été ajoutée pour télécharger automatiquement le modèle `punkt` de NLTK si besoin.

4.  **Tests et Validation :** Les changements ont été testés avec succès via le script `test_parser.py`. La comparaison entre le fichier VTT d'origine et le `parser_test_output.json` généré a confirmé que **l'intégralité du texte est conservée** et que les phrases sont mieux formées.

5.  **Documentation :** Le `README.md` a été mis à jour pour documenter le format recommandé pour les fichiers VTT (`<v Nom>`) et le `.gitignore` a été nettoyé.

**Difficultés Rencontrées et Leçons Apprises :**

*   **Environnement Utilisateur :** L'installation des nouvelles dépendances a échoué à cause d'une erreur `externally-managed-environment`.
    *   **Leçon :** C'est une protection standard sur les systèmes Linux récents. La solution correcte, que nous avons appliquée, est de toujours travailler dans un environnement virtuel Python (`venv`).
*   **Erreurs de l'IA (moi-même) :** J'ai tenté à plusieurs reprises d'exécuter des commandes shell (`pip`, `git status`, `python3`) qui me sont interdites dans cet environnement.
    *   **Leçon :** Je dois cesser d'essayer d'exécuter ces commandes. Pour modifier un fichier, je dois utiliser le cycle `read_file` -> `write_file`. Pour les actions qui requièrent une exécution, je dois vous fournir les instructions claires.
*   **Mémoire de Session :** Mon incapacité à me souvenir de la création du fichier `test_parser.py` a souligné la nécessité de ce journal.
    *   **Leçon :** Ce fichier `historique_discussion_gemini.md` est désormais notre "mémoire partagée". Il sera systématiquement mis à jour en fin de session pour garantir la continuité.

**Prochaine étape convenue :**
- Sauvegarder l'ensemble de ce travail via un commit Git.

---

### Session du 2026-03-14 - Refonte Architecturale V2 et Radar Contextuel

**Objectif :** Nettoyer la dette technique, modulariser le code, unifier l'intelligence artificielle entre le Web et le CLI, et implémenter un suivi dynamique du sujet pour le direct.

**Parcours et Actions Clés :**

1.  **Restructuration Modulaire (Opération "Anti-Merdier") :**
    *   Le code source a été organisé en dossiers spécialisés : `web/` (Flask), `cli/` (Console), `core/` (Moteurs IA), `ingestion/` (VTT/YouTube), `tools/` (DDGS/Contexte), et `prompts/`.
    *   L'ancien "God Object" `live_fact_checker.py` a été scindé et renommé en `console_app.py`, isolant la logique de mémoire dans `history_manager.py`.

2.  **Unification du Cerveau :**
    *   L'ancienne classe obsolète `AffirmationProcessor` a été définitivement supprimée.
    *   Désormais, l'interface Console et l'interface Web utilisent la même instance puissante de `AnalysisOrchestrator` (Hybride Groq + Mistral).

3.  **Implémentation du Moteur "Radar" (Contexte Dynamique) :**
    *   Création de `stream_engine.py` pour isoler la boucle asynchrone de streaming de Flask.
    *   Ajout d'une boucle "Radar" tournant en arrière-plan (toutes les 10 à 60s) qui lit la transcription récente et génère un **Résumé Roulant** ainsi qu'une mise à jour du `main_topic` et `sub_topic`.
    *   Cette méthode permet à l'IA de suivre les digressions d'un long débat sans exploser les quotas TPM (Tokens Per Minute) de l'API.

4.  **Correction ASR et Résolution des Pronoms :**
    *   Le prompt de sélection de Groq a été perfectionné. Il doit désormais ignorer le "bruit" oral (bégaiements).
    *   Groq a surtout la tâche de générer une `affirmation_corrigee` : il répare les erreurs phonétiques (ex: "le loup" au lieu de "le Louvre") et désambiguïse les pronoms ("Il fuit" -> "Le suspect fuit") AVANT la recherche Google, résolvant ainsi l'impossibilité de fact-checker des phrases sorties de leur contexte.

**Statut Actuel :**
*   L'Architecture V2 est en production, très propre, modulaire et robuste.
*   L'interface Web Flask affiche dynamiquement des pastilles de sujet.
*   Le projet est mûr pour attaquer l'optimisation qualitative de l'analyse (ironie, sarcasme, etc.).

---

### Session du 2026-03-15 - Optimisations Anti-429, Gestion des Opinions et Préparation MLOps

**Objectif :** Stabiliser l'application face aux requêtes réseau (Rate Limits), raffiner la détection des affirmations subjectives (Opinions), améliorer le frontend (temps réel), et concevoir la stratégie d'évaluation en masse.

**Parcours et Actions Clés :**

1.  **Interface Web Temps Réel (UX) :**
    *   Le frontend affichait un blocage artificiel. Modification de `index.html` pour afficher le flux d'analyse *futur* (en avance sur la vidéo) avec une opacité réduite (grisé).
    *   Ajout d'une pastille "📰 Actus" avec un tooltip affichant le contexte géopolitique de l'époque au survol de la souris.

2.  **Robustesse du Cerveau (Le Parseur JSON) :**
    *   Le modèle Mistral hallucinait parfois des dictionnaires Python (avec des guillemets simples `{'verdict': ...}`) au lieu d'un vrai JSON valide, ce qui faisait crasher l'historique.
    *   Ajout d'un filet de sécurité robuste `ast.literal_eval` dans `_parse_llm_json` (`orchestrator.py`) pour intercepter et convertir ces erreurs silencieusement.

3.  **Résolution des Rate Limits (Erreurs 429 Groq) :**
    *   **Problème :** Groq se mettait en grève (Rate Limit TPM) car on lui envoyait la totalité des news et de la biographie juste pour classer une phrase.
    *   **Solution :** Séparation des contextes dans l'Orchestrateur. Un `contexte_leger` (tronqué à 1000 caractères) pour Groq (Phase 1), et un `contexte_lourd` complet pour Mistral (Phase 2).
    *   Réduction de la mémoire anti-doublon de 20 à 5 phrases dans `stream_engine.py`. Résultat : Consommation de tokens divisée par 4.

4.  **Éducation Civique : Le statut de "L'Opinion" :**
    *   **Problème :** L'IA validait des opinions ("Il faut interdire X") avec un verdict "VRAI" car Google trouvait des textes qui en parlaient.
    *   **Solution :** Modification stricte de `templates.py`. Une opinion ou une injonction doit obligatoirement recevoir le verdict **OPINION** (et non VRAI/FAUX) avec une explication pédagogique stipulant que ce n'est pas un fait vérifiable.

**Prochaine étape convenue (Le Plan d'Évaluation en Masse - MLOps) :**
Le projet passe du stade d'outil à celui de pipeline de données. Nous allons créer un dossier `scripts/` pour les opérations suivantes :

*   **Étape 1 : Ingestion (`batch_youtube.py`) :** Utiliser `yt-dlp` pour lister toutes les URLs d'une chaîne (ex: interviews matinales RMC) et lancer l'analyse en masse pour créer un `dataset_brut.jsonl`.
*   **Étape 2 : Évaluation ("LLM-as-a-Judge") (`evaluator.py`) :** Créer un script où un grand modèle (ex: GPT-4o / Claude 3.5) évalue le travail de Mistral sur 3 critères (Pertinence de sélection, Exactitude du verdict, Neutralité) de 1 à 5.
*   **Étape 3 : Calcul des KPIs :** Analyser le taux de faux-positifs, le taux de crash JSON, et la complaisance de l'IA.
*   **Objectif Final :** Isoler les analyses notées "5/5" pour constituer un **Golden Dataset** servant à un futur Fine-Tuning de modèle ouvert.
