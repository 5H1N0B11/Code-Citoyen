import asyncio
import os
import re
from typing import List, Dict, Any
import time
import sys

# Initialisation par défaut
CLIENT = None 

# Importations spécifiques à Mistral (Compatible V1.x - utilise le client unifié "Mistral")
try:
    from mistralai import Mistral as AsyncMistralClient 
    
except ImportError as e:
    print(f"Erreur critique d'importation : Le package 'mistralai' est introuvable. {e}")
    pass 
    
# Récupération de la clé d'API Mistral
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")
MODEL_NAME = "mistral-tiny" 

# Initialiser le client Mistral
try:
    if 'AsyncMistralClient' in locals() and MISTRAL_API_KEY: 
        CLIENT = AsyncMistralClient(api_key=MISTRAL_API_KEY)
        
    elif 'AsyncMistralClient' in locals() and not MISTRAL_API_KEY:
        print("Erreur: MISTRAL_API_KEY n'est pas définie dans l'environnement.")
        CLIENT = None
    
    else:
        CLIENT = None
        
except Exception as e:
    print(f"Erreur grave lors de l'initialisation du client Mistral : {e}")
    CLIENT = None

def verifier_client_pret() -> bool:
    """Vérifie si le CLIENT Mistral est bien initialisé et prêt à l'emploi."""
    global CLIENT, MISTRAL_API_KEY
    if CLIENT is None:
        print("\n\n################################################################################")
        print("🛑 ERREUR CRITIQUE : LE CLIENT MISTRALAI N'EST PAS PRÊT.")
        print("Veuillez vérifier les points suivants :")
        print(f"1. La variable d'environnement 'MISTRAL_API_KEY' est-elle définie ? (Actuel : {'OUI' if MISTRAL_API_KEY else 'NON'})")
        print("2. Le package 'mistralai' est-il correctement installé dans votre VENV ?")
        print("################################################################################\n")
        return False
    return True

# --- PHASE 1 : PROMPT DE CLASSIFICATION (V80.35 - Exclusion CONSEIL des faits/corrélations) ---
SYSTEM_PROMPT_CLASSIFY = (
    "RÉPONSE EN FRANÇAIS. Votre rôle est d'analyser une affirmation et de générer son unique catégorie d'analyse."
    
    "RÈGLES DE HAUTE PRIORITÉ : "
    "1. **LOGIQUE (Sophisme/Biais)** : "
    "   * **Exclusion Renforcée ABSOLUE (Crimes/Faits)** : Si l'affirmation concerne une allégation de **CRIME GRAVE (guerre, exécution, génocide - Ex: Le Hamas execute son peuple)**, ou un **fait universellement accepté (Ex: La Terre est ronde)**, **NE PAS UTILISER LOGIQUE**. Utiliser **JURIDIQUE** ou **CONSENSUS_SCIENCE/HISTO** à la place."
    "   * **Priorité Absolue (Sophismes)** : Utilisez LOGIQUE si l'affirmation est une **attaque personnelle (Ad Hominem)**, un **Argument d'Autorité** contre le consensus, ou un sophisme de raisonnement qui **ne peut être corrigé par un simple fait ou chiffre** (Ex: Pente Glissante, Fausse Généralisation Morale). **INCLUT : Rejeter un argument à cause d'un passé judiciaire (Ex: 'ne pas l'écouter car mis en examen').**"
    "   * **Priorité Modérée** : Utilisez LOGIQUE si le **biais de raisonnement** (fausse causalité, généralisation hâtive) est l'élément **principal** de l'affirmation. **MAIS : SI l'affirmation est manifestement absurde ou auto-contradictoire, utilisez HUMOUR.**"
    "   * **Exclusion Standard** : Si l'affirmation contient un **chiffre, un taux, une loi, ou un fait historique précis**, NE PAS UTILISER LOGIQUE, mais la catégorie factuelle appropriée (STATISTIQUE, JURIDIQUE, CONSENSUS_HISTO, etc.)."
    
    "2. **DOCTRINE (Religion/Idéologie)** : Si l'affirmation concerne un texte sacré, un dogme religieux, une **idéologie politique structurée**, ou une **école de pensée philosophique**. (Ex: 'Quitter l'Islam n'est pas risquer sa vie...', 'L'écologie politique rejette toutes les formes de croissance économique')."
    
    "3. **JURIDIQUE (Loi/Droit)** : Si l'affirmation concerne l'existence ou l'interprétation d'une loi, d'un article ou d'une convention légale. **EXCLUT : L'utilisation d'un statut judiciaire (mis en examen/condamné) pour discréditer un argument (ce cas est LOGIQUE).** (Ex: 'En France, la majorité pénale est fixée à 18 ans')."

    "4. **STATISTIQUE (Chiffre/Taux)** : Si l'affirmation concerne une donnée chiffrée, un pourcentage ou un taux mesurable (économique, social). (Ex: 'Le taux de chômage en France est de 7,3%')."
    
    "5. **CONSENSUS_SCIENCE / CONSENSUS_HISTO** : Pour tous les faits vérifiables non logiques, non religieux et non juridiques (science, histoire, géographie). **INCLUT OBLIGATOIREMENT : Toutes les allégations de crimes graves (guerre, exécution, génocide).** L'analyse DOIT porter sur la véracité du fait rapporté (par des sources crédibles : ONG, agences de presse, ONU) et non sur la légalité du groupe incriminé. (Ex: 'La Terre est plate', 'Le Hamas execute son propre peuple', 'Les pyramides ont été construites par des esclaves')."
    
    "6. **OPINION (Subjectif)** : Si l'affirmation est un jugement de valeur non vérifiable. (Ex: 'Manger du chocolat rend génial')."

    "7. **CONSEIL (Recommandation)** : STRICTEMENT réservé aux affirmations formulées comme des injonctions ou des recommandations **d'action personnelle** (Ex: 'Tu devrais vérifier tes sources'). **EXCLUT ABSOLUMENT** tout énoncé factuel ou corrélation de faits, même s'il est formulé comme un conseil. (Ex: 'Depuis qu'on a mis des caméras... ' n'est PAS un CONSEIL, c'est un FAIT à vérifier par CONSENSUS_SCIENCE)."
    
    "RÈGLE D'OR ABSOLUE : Votre réponse DOIT être UN SEUL MOT. Ce mot DOIT correspondre EXACTEMENT à l'une des catégories listées ci-dessous, en MAJUSCULES, et SANS AUCUN autre caractère, ponctuation, espace, astérisque, ni Markdown."
    
    "LISTE DES CATÉGORIES AUTORISÉES (ET SEULEMENT ELLES) : " 
    "* **HUMOUR**"
    "* **OPINION**"
    "* **CONSEIL**"
    "* **STATISTIQUE**"
    "* **JURIDIQUE**"
    "* **DOCTRINE**"
    "* **CONSENSUS_SCIENCE**"
    "* **CONSENSUS_HISTO**"
    "* **LOGIQUE**"
    
    "NE JAMAIS répondre : CONSENSUS_RELIGIEUX, CONFLICT, VRAI, FAUX, BIAIS. UN SEUL MOT DE LA LISTE AUTORISÉE, RIEN D'AUTRE."
)

SPECIALIZED_PROMPTS_NON_FACTUEL = {
    "HUMOUR": "TONALITÉ : HUMOUR : L'intention de cette affirmation est clairement humoristique ou satirique, la vérification factuelle n'est pas pertinente.",
    "OPINION": "TONALITÉ : OPINION : Ceci est une déclaration subjective ou un jugement de valeur, non vérifiable factuellement. [Source: Déclaration Subjective].",
    "CONSEIL": "TONALITÉ : CONSEIL : Il s'agit d'une recommandation ou d'une suggestion. L'analyse factuelle se limite à vérifier l'absence de danger immédiat. (Vérification : S'assurer que le conseil ne promeut pas un acte illégal ou dangereux). [Source: Recommandation]."
}

def get_factuel_system_prompt(category: str):
    """Génère le prompt système spécialisé en fonction de la catégorie factuelle (V80.35)."""
    
    RULE_GOLD = f"RÈGLE D'OR : Votre réponse DOIT commencer par la catégorie : [{category}] suivie du verdict brut, sans AUCUN autre texte avant. La catégorie utilisée DOIT être {category.upper()}."

    if category in ["CONSENSUS_HISTO", "CONSENSUS_SCIENCE"]:
        return (
            f"{RULE_GOLD} Votre rôle est de vérifier si l'affirmation est conforme au consensus académique/scientifique MODERNE. "
            "Règles : Le verdict BRUT doit être UNIQUEMENT **VRAI**, **FAUX**, ou **CONTESTÉ**. Le BIAIS est interdit. "
            "EXIGENCE HAUTE DE SOURCING : **Consultez des sources académiques** (revues à comité de lecture, études de référence, universités, chercheurs reconnus) pour définir le consensus. **INTERDIT** d'utiliser des sources populaires ou non vérifiables."
            "FORMAT : [VERDICT BRUT] : [Énoncé du fait selon le consensus]. (Explication: [Précision]) [Source: Source 1 (Auteur, Année); Source 2 (Auteur, Année)]."
        )
    
    elif category == "DOCTRINE":
        return (
            f"{RULE_GOLD} Votre rôle est de comparer l'affirmation aux **TEXTES FONDAMENTAUX** et aux écoles de pensée majoritaires de la doctrine. "
            "Règles : Le verdict BRUT doit être UNIQUEMENT **VRAI**, **FAUX**, ou **CONTESTÉ**. Si l'affirmation concerne un sujet notoirement controversé (apostasie, dogme majeur contesté), le verdict DOIT être **CONTESTÉ**."
            "INTERDIT ABSOLU de donner un double verdict non structuré (Ex: VRAI: FAUX)."
            "EXIGENCE : **Dans le cas de CONTESTÉ, la position MAJORITAIRE (ou la plus sourcée) doit être présentée EN PREMIER.** Citez les TEXTES CLÉS PRIMAIRES ou les ÉCOLES DE PENSÉE. "
            "FORMAT CONTESTÉ : CONTESTÉ : [FAUX/VRAI selon la majorité (Explication Majoritaire)] vs [VRAI/FAUX selon la minorité (Explication Minoritaire)]."
        )
        
    elif category == "JURIDIQUE":
        return (
            f"{RULE_GOLD} Votre rôle est de vérifier l'affirmation par rapport à la loi officielle la plus récente. "
            "Règles : Le verdict BRUT doit être UNIQUEMENT **VRAI**, **FAUX**, ou **CONTESTÉ**. "
            "EXIGENCE DE SOURCING : Citez l'article de loi, le Code, ou la Convention **officielle et à jour**. Si contestation, citez la jurisprudence la plus haute. **PRIORISEZ le texte de loi direct.**"
            "FORMAT : [VERDICT BRUT] : [Correction légale]. (Explication: [Article de loi]) [Source: Référence légale]."
        )

    elif category == "STATISTIQUE":
        return (
            f"{RULE_GOLD} Votre rôle est de vérifier la donnée chiffrée ou la corrélation. "
            "Règles : Si la donnée existe et est claire → verdict VRAI/FAUX. Si l'affirmation est une corrélation sans preuve → verdict BIAIS. "
            "EXIGENCE DE SOURCING : Citez l'organisme **officiel** (INSEE, Eurostat, FMI, etc.) et la **date la plus récente** de la publication. **Même si l'affirmation est un BIAIS, indiquez la donnée factuelle réelle pour corriger l'affirmation.**"
            "FORMAT BIAIS : BIAIS : [Sophisme précis] : [Explication concise de l'erreur logique ou sociétale et donnée factuelle corrigée]."
        )
        
    elif category == "LOGIQUE": 
        return (
            f"{RULE_GOLD} Votre rôle est d'identifier le sophisme ou le biais logique précis contenu dans l'affirmation. "
            "Règles : Les verdicts VRAI, FAUX, CONTESTÉ sont STRICTEMENT INTERDITS. Le verdict BRUT DOIT OBLIGATOIREMENT être **BIAIS**. "
            "EXIGENCE HAUTE : **Vous DEVEZ identifier le sophisme précis**. Si une terminologie française existe, utilisez-la (Ex: Attaque personnelle au lieu d'Ad Hominem). Si l'affirmation utilise l'avis d'une autorité contre un consensus établi, identifiez **Argument d'Autorité**. **NE JAMAIS laisser le nom du biais vague (ex: 'Biais de raisonnement').**"
            "FORMAT : BIAIS : [Sophisme précis] : [Explication concise de l'erreur logique ou sociétale]."
        )
        
    return "" 


def extraire_categorie_et_verdict(verdict_brut_avec_cat: str, phase_2_category_used: str) -> Dict[str, str]:
    """Extrait la catégorie et l'analyse brute avec tolérance sur le format."""
    
    verdict_nettoye = verdict_brut_avec_cat.strip()
    
    # Tentative d'extraction stricte (pour les formats [CATEGORIE]...)
    match_strict = re.match(r"^\[(\w+)\]\s*(.*)", verdict_nettoye, re.DOTALL)
    
    if match_strict:
        categorie = match_strict.group(1).upper()
        verdict_seul = match_strict.group(2).strip()
        
        # Correction si la catégorie extraite est un verdict au lieu de la catégorie demandée
        if categorie in ["VRAI", "FAUX", "CONTESTÉ", "BIAIS", "TONALITÉ"]:
            # Marquer l'échec de formatage de la Phase 2
            return {
                "affirmation": "", 
                "categorie": "ANALYSE_BRUTE", 
                "analyse": verdict_nettoye.strip()
            }
        
    else:
        # Échec de formatage strict (pas de [CATEGORIE] au début)
        categorie = "ANALYSE_BRUTE"
        verdict_seul = verdict_nettoye.strip()
        
    return {
        "affirmation": "", 
        "categorie": categorie, 
        "analyse": verdict_seul
    }


async def appel_verification_phase_2(affirmation, categorie_utilisee, system_prompt):
    """Effectue l'appel à l'API pour la phase de vérification (Appel 2)."""
    global CLIENT
    try:
        messages_verify = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Vérifiez l'affirmation et donnez le verdict brut selon les règles : \"{affirmation}\""}
        ]
        
        response_verify = await CLIENT.chat.complete_async(
            model=MODEL_NAME, 
            messages=messages_verify
        )
        verdict_brut_avec_cat = response_verify.choices[0].message.content.strip()
        
        return extraire_categorie_et_verdict(verdict_brut_avec_cat, categorie_utilisee)
        
    except Exception as e:
        return {"affirmation": affirmation, "analyse": f"Erreur Phase 2 (Vérification {categorie_utilisee}) : {e}", "categorie": "ERREUR_VERIFY"}

async def async_analyser_critiquer(resultat_fact_checker: Dict[str, Any]) -> Dict[str, str]:
    global CLIENT
    
    if CLIENT is None:
        return {"affirmation": resultat_fact_checker['affirmation'], "analyse": "Erreur: Client Mistral non disponible. (Clé API ou Installation manquante)", "categorie": "ERREUR_API"}

    affirmation = resultat_fact_checker['affirmation']
    
    VALID_FACTUAL = ["STATISTIQUE", "JURIDIQUE", "DOCTRINE", "CONSENSUS_SCIENCE", "CONSENSUS_HISTO", "LOGIQUE"]
    VALID_NON_FACTUAL = SPECIALIZED_PROMPTS_NON_FACTUEL.keys() 

    # --- APPEL 1 : CLASSIFICATION ---
    try:
        messages_classify = [
            {"role": "system", "content": SYSTEM_PROMPT_CLASSIFY},
            {"role": "user", "content": f"Quelle est la catégorie de cette affirmation ? : \"{affirmation}\""}
        ]
        
        response_classify = await CLIENT.chat.complete_async(
            model=MODEL_NAME, 
            messages=messages_classify
        )
        content_brut = response_classify.choices[0].message.content.strip().upper()
        categorie = content_brut.replace('**', '').split()[0]
        
        # Nettoyage et MAPPING des catégories inventées (V80.35)
        if categorie not in VALID_FACTUAL and categorie not in VALID_NON_FACTUAL:
             invented_cat = categorie
             
             # Tentative de mapping vers la catégorie correcte
             if 'CONSEIL' in invented_cat or 'RECOMMAN' in invented_cat or 'DEVR' in invented_cat:
                 categorie = "CONSEIL"
             elif 'RELIG' in invented_cat or 'DOCTRINE' in invented_cat or 'IDEOLOGI' in invented_cat:
                 categorie = "DOCTRINE"
             elif 'JURIDIQUE' in invented_cat or 'LAW' in invented_cat or 'DROIT' in invented_cat:
                 categorie = "JURIDIQUE"
             elif invented_cat in ["VRAI", "FAUX", "CONTESTÉ", "BIAIS", "CONFLICT"]:
                 # Si c'est un verdict ou un terme générique, on le rattache au fact-checking le plus fort
                 categorie = "CONSENSUS_SCIENCE"
             else:
                 # Tout terme inconnu est forcé à CONSENSUS_SCIENCE pour un fact-checking fort
                 categorie = "CONSENSUS_SCIENCE" 
             print(f"[{time.strftime('%H:%M:%S', time.localtime())}] ⚠️ MAPPING : Catégorie inventée/invalide '{invented_cat}' -> Forçage à '{categorie}'.")

        
    except Exception as e:
        return {"affirmation": affirmation, "analyse": f"Erreur Phase 1 (Classification) : {e}", "categorie": "ERREUR_CLASSIFY"}
        
    # --- ROUTAGE VERS LA PHASE 2 ---
    
    # Cas 1 : Catégorie Non-Factuelle (HUMOUR, OPINION, CONSEIL)
    if categorie in VALID_NON_FACTUAL:
        analyse_finale = SPECIALIZED_PROMPTS_NON_FACTUEL[categorie]
        resultat_extrait = {"categorie": categorie, "analyse": analyse_finale}
        
    # Cas 2 : Catégorie Factuelle Spécialisée (STATISTIQUE, JURIDIQUE, etc.)
    elif categorie in VALID_FACTUAL:
        system_prompt_specialized = get_factuel_system_prompt(categorie)
        resultat_extrait = await appel_verification_phase_2(affirmation, categorie, system_prompt_specialized)
        
    # Cas 3 (RATTRAPAGE) : Catégorie Inconnue (Ne devrait plus arriver)
    else:
        categorie_rattrapage = "CONSENSUS_SCIENCE"
        print(f"[{time.strftime('%H:%M:%S', time.localtime())}] 🔴 ERREUR RATTRAPAGE FINAL. Forçage à {categorie_rattrapage}.")
        system_prompt_rattrapage = get_factuel_system_prompt(categorie_rattrapage)
        resultat_extrait = await appel_verification_phase_2(affirmation, categorie_rattrapage, system_prompt_rattrapage)


    # RENVOI FINAL
    categorie_finale = resultat_extrait.get("categorie", categorie) 
    
    # Si la catégorie finale est l'échec de formatage de la Phase 2, on garde la catégorie de la Phase 1 (MAPPING)
    if categorie_finale == "ANALYSE_BRUTE":
        categorie_finale = categorie

    return {
        "affirmation": affirmation,
        "categorie": categorie_finale, 
        "analyse": resultat_extrait.get("analyse", "Erreur de formatage final de l'analyse.")
    }


async def fact_checker_batch_async(affirmations: List[str]) -> List[Dict[str, str]]:
    """Gère l'exécution asynchrone des analyses pour un lot d'affirmations."""
    
    taches_initiales = [{"affirmation": a} for a in affirmations]
    
    start_time = time.time()
    print(f"[{time.strftime('%H:%M:%S', time.localtime())}] 🧠 Lancement des {len(taches_initiales)} analyses IA en parallèle...")
    
    try:
        taches_fact_checking = [async_analyser_critiquer(tache) for tache in taches_initiales]
        resultats = await asyncio.gather(*taches_fact_checking)

    except Exception as e:
        print(f"Erreur fatale lors de l'exécution asynchrone : {e}")
        resultats = []

    end_time = time.time()
    elapsed_time = round(end_time - start_time, 2)
    print(f"[{time.strftime('%H:%M:%S', time.localtime())}] ✅ Analyses terminées en {elapsed_time:.2f} secondes.")
    
    return resultats


def afficher_rapport_final(resultats: List[Dict[str, str]]):
    """Affiche le rapport formaté des résultats du fact-checking."""
    print("\n" + "="*80)
    print("🚀 RAPPORT FINAL : ANALYSE CRITIQUE (MODE BATCH)")
    print("="*80 + "\n")

    for i, res in enumerate(resultats):
        print(f"-------------------- AFFIRMATION {i + 1} --------------------")
        print(f"AFFIRMATION: {res['affirmation']}")
        print(f"CATÉGORIE: {res['categorie']}")
        print(f"VERDICT: {res['analyse']}")
        print("--------------------" + ("-" * (len(str(i+1)))) + "\n")
    
    print("#"*30 + " FIN DE L'ANALYSE BATCH. " + "#"*30)

def mode_batch():
    """Fonction principale pour le mode batch."""
    print("="*80)
    print("Mode Batch : Collez plusieurs affirmations séparées par des lignes vides.")
    print("Mode Manuel : Entrez une seule phrase.")
    print("Tapez 'quit' pour sortir.")
    print("="*80)

    if not verifier_client_pret():
        sys.exit(1)

    try:
        saisie = input("🗣️ Entrez les phrases à Fact-Checker (ou 'quit' pour sortir) : \n> ")
        if saisie.lower() == 'quit':
            sys.exit(0)
            
        affirmations = re.split(r'\s*\n\s*\n\s*', saisie)
        affirmations = [a.strip() for a in affirmations if a.strip()]
        
        if not affirmations:
            print("Aucune affirmation saisie.")
            return

        print("\n" + "="*80)
        print(f"🚀 DÉMARRAGE DU FACT-CHECKING ASYNCHRONE POUR {len(affirmations)} SAISIES")
        print("="*80)

        resultats = asyncio.run(fact_checker_batch_async(affirmations))
        
        if resultats:
            afficher_rapport_final(resultats)
        else:
            print("Aucun résultat d'analyse.")

    except EOFError:
        print("\nSortie forcée.")
        
    except Exception as e:
        print(f"Une erreur inattendue est survenue : {e}")


def analyser_et_critiquer(resultats_fact_checker: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Fonction synchrone de façade (non utilisée)."""
    return []

if __name__ == '__main__':
    mode_batch()
