import asyncio
import os
import re
from typing import List, Dict, Any
import time
import sys

# 🚨 NOUVELLE IMPORTATION : On importe les prompts du fichier dédié
try:
    from prompts_templates import (
        get_system_prompt_classify,
        SPECIALIZED_PROMPTS_NON_FACTUEL,
        get_specialized_system_prompt, 
        SYSTEM_PROMPT_ASK_CONCISE
    )
except ImportError as e:
    print(f"Erreur: Le fichier 'prompts_templates.py' ({str(e)}) est manquant ou contient des erreurs.")
    sys.exit(1)


# Initialisation par défaut (Laisser CLIENT à None)
CLIENT = None 

# Importations spécifiques à Mistral (Compatible V1.0.0+ - utilise le client unifié "Mistral")
try:
    # Importation du client unifié depuis la racine (v1.0.0+)
    from mistralai import Mistral as AsyncMistralClient 
    MISTRAL_INSTALLED = True
except ImportError as e:
    print(f"Erreur critique d'importation : Le package 'mistralai' (v1.0.0+) est introuvable. {e}")
    MISTRAL_INSTALLED = False
    pass 
    
# --- CONSTANTES DE MODÈLES ---
MODEL_TINY = "mistral-tiny"
MODEL_MEDIUM = "mistral-medium" # (Pour le fallback)
MODEL_LARGE = "mistral-large-latest"

# 🚨 V80.48 : Limite de concurrence pour éviter le Status 429
SEMAPHORE_LIMIT = 10  # Limite de tâches concurrentes
SEMAPHORE = asyncio.Semaphore(SEMAPHORE_LIMIT)
DELAY_PER_CALL = 0.5 # Délai de 500ms entre les appels pour respecter le rate limit


def get_mistral_client(api_key: str) -> 'AsyncMistralClient':
    """
    Retourne l'instance du client Mistral AI (Version V1.0.0+).
    """
    if not MISTRAL_INSTALLED:
        raise RuntimeError("Le client Mistral n'a pas pu être initialisé car le package 'mistralai' est manquant.")
        
    try:
        client_instance = AsyncMistralClient(api_key=api_key)
        return client_instance
    except Exception as e:
        raise RuntimeError(f"Le client Mistral n'a pas pu être initialisé. Détail: {e}")


# --- FONCTION PRINCIPALE D'ANALYSE (Mode Ask) ---

async def ask_ma(client: 'AsyncMistralClient', user_question: str) -> str:
    """
    Mode d'analyse critique direct (ask) - Appel unique et concis.
    """
    
    # 1. CLASSIFICATION (mistral-tiny) - Requête API N°1
    print("-> [Étape 1/2] Classification de la question (Mistral-tiny)...")
    
    affirmations_brutes = [{"affirmation": user_question}]
    
    try:
        classified_result = await classify_statements(client, affirmations_brutes)
    except Exception as e:
        return f"Erreur lors de la classification (Mistral-Tiny) : {e}"
    
    if not classified_result or classified_result[0]['category'] == 'ERREUR':
        return "Échec de l'étape de classification. Impossible de procéder à l'analyse critique."

    category = classified_result[0]['category']
    print(f"-> [Résultat 1/2] Catégorie détectée: **{category}**.")

    # GESTION DU SKIP (Politesse, Humour, etc.)
    if category in ["POLITESSE", "HUMOUR"]:
        return "SKIP"

    # 2. ANALYSE CONCISE (Mistral-Small) - Requête API N°2
    print(f"-> [Étape 2/2] Analyse critique concise ({category}, mistral-small-latest)...")
    
    system_prompt = SYSTEM_PROMPT_ASK_CONCISE 
        
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_question}
    ]

    try:
        # On utilise un modèle rapide (small) pour le mode 'ask'
        response = await client.chat.complete_async(
            model="mistral-small-latest",
            messages=messages,
        )
        return response.choices[0].message.content
        
    except Exception as e:
        return f"Erreur lors de la communication avec l'IA: {e}"


# --- FONCTIONS D'ANALYSE PAR LOTS (BATCH) ---

def extraire_categorie_et_verdict(verdict_brut_avec_cat: str, phase_2_category_used: str) -> Dict[str, str]:
    """Extrait la catégorie et l'analyse brute avec tolérance sur le format."""
    verdict_nettoye = verdict_brut_avec_cat.strip()
    match_strict = re.match(r"^\[(\w+)\]\s*(.*)", verdict_nettoye, re.DOTALL)
    
    if match_strict:
        categorie = match_strict.group(1).upper()
        verdict_seul = match_strict.group(2).strip()
        if categorie in ["VRAI", "FAUX", "CONTESTÉ", "BIAIS", "TONALITÉ", "ADMIS"]:
            return {"affirmation": "", "categorie": "ANALYSE_BRUTE", "analyse": verdict_nettoye.strip()}
    else:
        categorie = "ANALYSE_BRUTE"
        verdict_seul = verdict_nettoye.strip()
        
    return {"affirmation": "", "categorie": categorie, "analyse": verdict_seul}


async def appel_verification_phase_2(client: 'AsyncMistralClient', affirmation, categorie_utilisee, system_prompt):
    """Effectue l'appel à l'API pour la phase de vérification (Appel 2)."""
    try:
        messages_verify = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Vérifiez l'affirmation et donnez le verdict brut selon les règles : \"{affirmation}\""}
        ]
        
        response_verify = await client.chat.complete_async(
            model=MODEL_TINY, # Utilisation du Tiny pour le Fact-Checking (rapide et moins cher)
            messages=messages_verify
        )
        verdict_brut_avec_cat = response_verify.choices[0].message.content.strip()
        
        return extraire_categorie_et_verdict(verdict_brut_avec_cat, categorie_utilisee)
        
    except Exception as e:
        return {"affirmation": affirmation, "analyse": f"Erreur Phase 2 (Vérification {categorie_utilisee}) : {e}", "categorie": "ERREUR_VERIFY"}


async def async_analyser_critiquer(client: 'AsyncMistralClient', item: Dict[str, Any]) -> Dict[str, str]:
    """
    [RESTAURÉ] Fonction principale d'analyse critique (Phase 1 + Phase 2) pour UN item.
    """
    affirmation = item['affirmation']
    preuves = item.get('preuves', []) # Récupère les preuves du Module 4
    
    VALID_FACTUAL = ["STATISTIQUE", "JURIDIQUE", "DOCTRINE", "CONSENSUS_SCIENCE", "CONSENSUS_HISTO", "LOGIQUE"]
    VALID_NON_FACTUAL = SPECIALIZED_PROMPTS_NON_FACTUEL.keys() 

    # --- APPEL 1 : CLASSIFICATION ---
    try:
        system_prompt_classify = get_system_prompt_classify()
        
        messages_classify = [
            {"role": "system", "content": system_prompt_classify},
            {"role": "user", "content": f"Quelle est la catégorie de cette affirmation ? : \"{affirmation}\""}
        ]
        
        response_classify = await client.chat.complete_async(
            model=MODEL_TINY, 
            messages=messages_classify
        )
        content_brut = response_classify.choices[0].message.content.strip().upper()
        
        # 🚨 CORRECTION PARSING CLASSIFICATION (pour gérer [CATÉGORIE] ou CATÉGORIE)
        category_match = re.search(r'\[(.*?)\]', content_brut)
        if category_match:
            categorie = category_match.group(1).strip().upper()
        else:
            categorie = content_brut.replace('**', '').split()[0]
        
        # Mapping (inchangé)
        if categorie not in VALID_FACTUAL and categorie not in VALID_NON_FACTUAL:
             invented_cat = categorie
             if 'POLITESSE' in invented_cat or 'TRANSITION' in invented_cat or 'SALUTATION' in invented_cat:
                 categorie = "POLITESSE" 
             elif 'CONSEIL' in invented_cat:
                 categorie = "CONSEIL"
             elif 'DOCTRINE' in invented_cat or 'IDEOLOGI' in invented_cat:
                 categorie = "DOCTRINE"
             elif 'JURIDIQUE' in invented_cat:
                 categorie = "JURIDIQUE"
             elif invented_cat in ["VRAI", "FAUX", "CONTESTÉ", "BIAIS", "CONFLICT"]:
                 categorie = "CONSENSUS_SCIENCE"
             else:
                 categorie = "CONSENSUS_SCIENCE" 
             print(f"[{time.strftime('%H:%M:%S', time.localtime())}] ⚠️ MAPPING : Catégorie inventée/invalide '{invented_cat}' -> Forçage à '{categorie}'.")

        
    except Exception as e:
        return {"affirmation": affirmation, "analyse": f"Erreur Phase 1 (Classification) : {e}", "categorie": "ERREUR_CLASSIFY"}
        
    # --- ROUTAGE VERS LA PHASE 2 ---
    
    # Cas 1 : Non-Factuel (POLITESSE, HUMOUR, OPINION, CONSEIL)
    if categorie in VALID_NON_FACTUAL:
        analyse_finale = SPECIALIZED_PROMPTS_NON_FACTUEL[categorie]
        resultat_extrait = {"categorie": categorie, "analyse": analyse_finale}
        
    # Cas 2 : Factuel (LOGIQUE, STATISTIQUE, etc.)
    elif categorie in VALID_FACTUAL:
        system_prompt_specialized = get_specialized_system_prompt(categorie)
        resultat_extrait = await appel_verification_phase_2(client, affirmation, categorie, system_prompt_specialized)
        
    # Cas 3 : Rattrapage
    else:
        categorie_rattrapage = "CONSENSUS_SCIENCE"
        system_prompt_rattrapage = get_specialized_system_prompt(categorie_rattrapage)
        resultat_extrait = await appel_verification_phase_2(client, affirmation, categorie_rattrapage, system_prompt_rattrapage)

    # RENVOI FINAL
    categorie_finale = resultat_extrait.get("categorie", categorie) 
    if categorie_finale == "ANALYSE_BRUTE":
        categorie_finale = categorie

    return {
        "affirmation": affirmation,
        "categorie": categorie_finale, 
        "analyse": resultat_extrait.get("analyse", "Erreur de formatage final de l'analyse.")
    }


# 🚨 CORRECTION : Ajout de 'client' et 'mode', et remplacement de la simulation
async def fact_checker_batch_async(client: 'AsyncMistralClient', resultats_fact_checker: List[Dict[str, Any]], mode: str) -> List[Dict[str, str]]:
    """
    [CORRIGÉ] Orchestre la VRAIE analyse (Phase 1 + Phase 2) pour toutes les affirmations.
    """
    
    taches_initiales = resultats_fact_checker # Contient {"affirmation": ..., "preuves": ...}
    
    start_time = time.time()
    print(f"[{time.strftime('%H:%M:%S', time.localtime())}] 🧠 Lancement des {len(taches_initiales)} analyses IA (Classification + Vérification) en parallèle...")
    
    # 🚨 V80.48 : Fonction wrapper pour gérer le sémaphore et le délai après l'appel
    async def run_analysis_with_rate_limit(tache):
        async with SEMAPHORE:
            # Appel de la fonction d'analyse critique V80 (Phase 1 + Phase 2)
            result = await async_analyser_critiquer(client, tache)
            # Ajout d'une petite pause asynchrone pour réguler le débit global
            await asyncio.sleep(DELAY_PER_CALL) 
            return result
    
    try:
        # Tâches lancées avec le sémaphore
        taches_fact_checking = [run_analysis_with_rate_limit(tache) for tache in taches_initiales]
        
        resultats = await asyncio.gather(*taches_fact_checking)

    except Exception as e:
        print(f"Erreur fatale lors de l'exécution asynchrone : {e}")
        resultats = []

    end_time = time.time()
    elapsed_time = round(end_time - start_time, 2)
    print(f"[{time.strftime('%H:%M:%S', time.localtime())}] ✅ Analyses terminées en {elapsed_time:.2f} secondes.")
    
    return resultats


async def classify_statements(client: 'AsyncMistralClient', affirmations_brutes: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    Classifie les affirmations dans une catégorie (STATISTIQUE, JURIDIQUE, LOGIQUE, etc.)
    """
    system_prompt_classify = get_system_prompt_classify()
    
    classified_results = []
    
    for item in affirmations_brutes:
        affirmation = item['affirmation']
        user_prompt = affirmation
        
        messages = [
            {"role": "system", "content": system_prompt_classify},
            {"role": "user", "content": user_prompt}
        ]

        try:
            # Correction V1.0.0+ : Appel Asynchrone
            response = await client.chat.complete_async(
                model=MODEL_TINY, # Utilisation du tiny pour la classification rapide
                messages=messages,
            )
            
            category_match = re.search(r'\[(.*?)\]', response.choices[0].message.content.strip())
            
            if category_match:
                category = category_match.group(1).strip().upper()
            else:
                category = response.choices[0].message.content.strip().upper()
            
            classified_results.append({
                "affirmation": affirmation,
                "category": category,
                "preuves": item.get('preuves', []) # On conserve les preuves
            })
            
        except Exception as e:
            raise Exception(f"Erreur de classification pour '{affirmation[:30]}...' : {e}")
        
    return classified_results

# --- FONCTION D'AFFICHAGE FLASH ---
# 🚨 CORRECTION : Ajout de 'mode: str'
def afficher_rapport_final(rapports_finaux: List[Dict[str, str]], mode: str = "Batch"):
    """Affiche le rapport final généré par l'analyse critique dans un format RAPIDE."""
    print("\n\n" + "#"*70)
    print(f"   RAPPORT FLASH : ANALYSE CRITIQUE RAPIDE (MODE {mode.upper()})")
    print("#"*70)

    if not rapports_finaux:
        print("Échec de la génération du rapport.")
        return

    for i, rapport in enumerate(rapports_finaux):
        print(f"\n--- AFFIRMATION N°{i+1} -------------------------------------------")
        
        analyse_complete = rapport.get('analyse', 'Analyse vide').strip()
        
        verdict_complet = "Verdict Indéterminé"
        synthese_rapide = "Synthèse factuelle non extraite."
        source_flash = "Source non trouvée."

        try:
            # 1. Extraction du VERDICT FINAL
            verdict_match = re.search(r"\*\*(CONTESTÉE|VRAI|FAUX|BIAIS|INFONDÉ|NON-VÉRIFIABLE)\*\*", analyse_complete, re.IGNORECASE)
            if not verdict_match:
                verdict_match = re.search(r"^(CONTESTÉE|VRAI|FAUX|BIAIS|INFONDÉ|NON-VÉRIFIABLE|ADMIS)", analyse_complete.strip(), re.IGNORECASE)
            
            if not verdict_match and "TONALITÉ" in analyse_complete:
                 verdict_match = re.search(r"TONALITÉ : (\w+)", analyse_complete)

            if verdict_match:
                verdict_brut = verdict_match.group(1).upper()
                verdict_complet = f"🚨 {verdict_brut} 🚨"
                if verdict_brut in ["VRAI", "ADMIS"]:
                    verdict_complet = f"✅ {verdict_brut} ✅"
                elif verdict_brut in ["FAUX", "INFONDÉ"]:
                    verdict_complet = f"❌ {verdict_brut} ❌"
                elif verdict_brut == "BIAIS":
                    verdict_complet = f"⚠️ {verdict_brut} ⚠️"
                elif verdict_brut in ["POLITESSE", "HUMOUR", "OPINION", "CONSEIL"]:
                    verdict_complet = f"💬 {verdict_brut} 💬"


            # 2. Extraction de la SYNTHÈSE RAPIDE
            synthese_match = re.search(r"^(?:\[.*?\]|.*?) : (.*?) :", analyse_complete.strip())
            
            if synthese_match:
                synthese_rapide = synthese_match.group(1).strip()
            
            # Fallback
            else:
                phrases = re.split(r'(?<=[.?!])\s+', analyse_complete.strip())
                if phrases:
                    synthese_rapide = phrases[0] 

            # 3. Extraction de la SOURCE FLASH
            source_match = re.search(r"Source: \[(.*?)\]", analyse_complete, re.IGNORECASE)
            if source_match:
                source_flash = source_match.group(1).strip()
            elif 'Source:' in analyse_complete:
                 source_flash = analyse_complete.split('Source:')[-1].strip().split('\n')[0]
                 
        except Exception as e:
            synthese_rapide = "Erreur d'extraction. Format de sortie inattendu. (Détail: " + str(e)[:30] + "...)"
            verdict_complet = "Verdict Non Formatté"
            source_flash = "Vérifiez l'analyse complète."

        
        print(f"AFFIRMATION: {rapport['affirmation']}")
        print(f"VERDICT CLAIR: **{verdict_complet}**")
        print(f"SYNTHÈSE FLASH: {synthese_rapide}")
        print(f"SOURCE CLÉ: {source_flash}")
        
    print("\n" + "#"*70)
    print("FIN DE L'EXÉCUTION. Projet Code Citoyen terminé.")
    print("#" * 70)


def analyser_et_critiquer(resultats_fact_checker: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Fonction synchrone de façade (non utilisée)."""
    return []

if __name__ == '__main__':
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    async def test_ask():
        if CLIENT:
            print("Impossible de tester : Client Mistral non initialisé dans le bloc __main__.")
        else:
            print("Impossible de tester : Client Mistral non initialisé.")
    
    # asyncio.run(test_ask())
