# bias_list.py

# Dictionnaire des biais cognitifs et sophismes pour la classification LOGIQUE.
# Ce dictionnaire doit être importé dans Analyse_Critique_IA.py.
# L'IA (Mistral ou Gemini) utilisera ces descriptions pour identifier le biais précis
# et rédiger une analyse critique plus pertinente.

BIAS_LIST = {
    # --- Biais liés à la perception et à l'interprétation ---
    "Biais de Confirmation (Confirmation Bias)": "Tendance à privilégier les informations qui confirment nos propres croyances, et à ignorer ou discréditer celles qui les contredisent.",
    "Biais d'Ancrage (Anchoring Bias)": "Tendance à se fier trop fortement à la première information reçue (l'ancre) pour formuler un jugement.",
    "Biais de Disponibilité (Availability Heuristic)": "Tendance à surévaluer la probabilité d'événements facilement rappelables ou imaginables, souvent parce qu'ils sont récents ou émotionnellement marquants.",
    "Effet Dunning-Kruger": "Tendance des personnes les moins compétentes dans un domaine à surestimer leur propre compétence (et inversement pour les plus compétentes).",
    "Biais Rétrospectif (Hindsight Bias)": "Tendance à croire, après qu'un événement s'est produit, qu'il était prévisible ('Je le savais bien').",
    "Effet de Cadre (Framing Effect)": "Tendance à tirer des conclusions différentes à partir des mêmes informations, selon la manière dont elles sont présentées (cadre positif ou négatif).",
    "Illusion de Corrélation (Illusory Correlation)": "Perception d'une relation entre deux variables ou événements alors qu'elle n'existe pas ou est beaucoup plus faible en réalité.",
    "Biais de Négativité (Negativity Bias)": "Tendance à donner plus de poids aux expériences négatives qu'aux expériences positives ou neutres.",
    "Biais de Ressemblance (Similarity Bias)": "Tendance à être plus facilement d'accord ou à faire plus confiance à ceux qui nous ressemblent (âge, milieu social, opinions).",
    "Effet de Halo": "Tendance à laisser une seule caractéristique (souvent positive) d'une personne influencer notre jugement global sur tous ses autres aspects.",

    # --- Biais liés à l'action et la décision ---
    "Aversion à la Perte (Loss Aversion)": "Tendance à préférer éviter une perte plutôt que d'acquérir un gain équivalent.",
    "Biais du Statu Quo (Status Quo Bias)": "Tendance à préférer que les choses restent telles qu'elles sont, évitant le risque du changement.",
    "Erreur Fondamentale d'Attribution": "Tendance à surestimer les facteurs personnels (caractère) et à sous-estimer les facteurs situationnels (contexte) pour expliquer le comportement d'autrui.",
    "Biais d'Optimisme (Optimism Bias)": "Tendance à croire que l'on est moins susceptible que les autres de subir des événements négatifs (maladie, accident).",
    "Effet de Foule (Bandwagon Effect)": "Tendance à adopter une croyance ou un comportement en fonction de la quantité de personnes qui l'ont déjà adopté ('Si tout le monde le dit...').",
    "Effet d'Autorité (Authority Bias)": "Tendance à attribuer une plus grande précision à l'opinion d'une figure d'autorité et à être influencé par elle, même en l'absence de preuves.",
    "Biais de Projection (Projection Bias)": "Tendance à surestimer la mesure dans laquelle les autres partagent nos pensées, croyances et valeurs actuelles.",
    "Biais du Choix de Soutien (Choice-Supportive Bias)": "Tendance à se souvenir des choix que l'on a faits comme meilleurs qu'ils ne l'étaient réellement.",
    "Effet IKEA": "Tendance à accorder une valeur disproportionnée aux objets que l'on a construits ou assemblés soi-même.",
    "Biais de Réactance (Reactance Bias)": "Tendance à faire l'inverse de ce qui est demandé ou suggéré, par esprit de contradiction ou pour préserver son libre arbitre.",

    # --- Sophismes (Fallacies) et erreurs de logique ---
    "Attaque Ad Hominem": "Sophisme qui consiste à attaquer la personne qui émet l'argument plutôt que l'argument lui-même.",
    "Fausse Dichotomie (Faux Dilemme)": "Présenter seulement deux options comme étant les seules possibilités, alors qu'il en existe d'autres (p. ex., 'Soit vous êtes avec moi, soit vous êtes contre moi').",
    "Pente Glissante (Slippery Slope)": "Affirmer qu'une action entraînera inévitablement une série d'événements négatifs sans preuve causale directe.",
    "Appel à l'Émotion (Appeal to Emotion)": "Manipulation des émotions du public au lieu d'utiliser un argument logique ou factuel.",
    "Argument d'Ignorance (Appeal to Ignorance)": "Affirmer qu'une proposition est vraie (ou fausse) parce qu'il n'existe aucune preuve prouvant le contraire.",
    "Pétition de Principe (Begging the Question)": "Utiliser la conclusion de l'argument comme l'une de ses prémisses (raisonnement circulaire).",
    "Affirmation du Conséquent (Affirming the Consequent)": "Erreur logique où, si A implique B, on conclut que B implique A (p. ex., 'S'il pleut, la rue est mouillée. La rue est mouillée, donc il a plu').",
    "Détournement de Sujet (Red Herring)": "Introduire un sujet non pertinent pour distraire l'auditeur ou le lecteur du sujet initial.",
    "Généralisation Hâtive (Hasty Generalization)": "Tirer une conclusion générale à partir d'un échantillon trop petit ou non représentatif.",
    "Biais du Tirailleur (Texas Sharpshooter Fallacy)": "Identifier un modèle dans des données aléatoires pour appuyer une hypothèse, en ignorant les données qui ne correspondent pas.",
    "Biais de Croyance (Belief Bias)": "Tendance à juger de la validité d'un argument en fonction de la plausibilité de sa conclusion plutôt que de la logique de son raisonnement.",
    "Erreur de l'Historien (Historian's Fallacy)": "Croire que les personnes du passé prenaient des décisions sans avoir accès aux connaissances qu'on possède aujourd'hui (jugement anachronique).",

    # --- Biais d'information/mémoire et sociaux ---
    "Biais de Désirabilité Sociale": "Tendance à se présenter sous un jour favorable en modifiant son comportement ou ses réponses pour correspondre aux normes sociales.",
    "Effet Barnum (Forer Effect)": "Tendance à croire qu'une description de la personnalité est très précise alors qu'elle est suffisamment vague pour s'appliquer à n'importe qui.",
    "Oubli de la Fréquence de Base (Base Rate Neglect)": "Tendance à ignorer les statistiques générales (fréquence de base) au profit d'informations spécifiques (souvent anecdotiques).",
    "Biais de Saliency (Saliency Bias)": "Tendance à concentrer l'attention sur les informations les plus saillantes, même si elles sont moins importantes que d'autres informations moins visibles.",
    "Effet de Simple Exposition (Mere Exposure Effect)": "Tendance à développer une préférence pour des choses simplement parce qu'on les a déjà vues ou rencontrées.",
    "Biais de Faux Consensus (False Consensus Effect)": "Tendance à surestimer la mesure dans laquelle les autres sont d'accord avec nous.",
    "Biais de l'Acteur-Observateur": "Tendance à attribuer nos propres actions aux facteurs externes (contexte) et les actions des autres aux facteurs internes (personnalité).",
    "Biais de l'Illusion de Contrôle": "Tendance à croire que l'on peut contrôler ou influencer des événements sur lesquels on n'a objectivement aucune influence."
}
