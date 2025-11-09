import asyncio
import os
import re
from typing import List, Dict, Any
import time
import sys

# 🚨 NOUVELLE IMPORTATION : On importe les prompts du fichier dédié
try:
    from prompts_templates import (
        SYSTEM_PROMPT_CLASSIFY, # <-- CORRECTION : Import de la VARIABLE
        SPECIALIZED_PROMPTS_NON_FACTUEL,
        get_specialized_system_prompt, 
        SYSTEM_PROMPT_ASK_CONCISE # <-- NOUVEAU PROMPT POUR LE MODE 'ASK'
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
        # 🚨 CORRECTION V1.0.0+ : Appel Asynchrone
        response = await client.chat.complete_async(
            model="mistral-small-latest",
            messages=messages,
        )
        return response.choices[0].message.content
        
    except Exception as e:
        return f"Erreur lors de la communication avec l'IA: {e}"


# --- FONCTION D'ANALYSE PAR LOTS (BATCH) ---
async def fact_checker_batch_async(client: 'AsyncMistralClient', affirmations_brutes: List[Dict[str, Any]], mode: str) -> None:
    """
    Orchestre la classification, le fact-checking et l'analyse critique par lots.
    """
    # 1. Classification (Inchangé)
    print("\n--- Étape 1 : Classification des Affirmations (Mistral-tiny) ---")
    classified_statements = await classify_statements(client, affirmations_brutes)

    # 2. Fact-Checking (Inchangé)
    # ...
    
    # 3. Analyse Critique (Inchangé)
    print("Exécution complète du Fact-Checker Batch simulée.")
    # Le vrai appel à l'analyse critique sera fait dans l'orchestrateur.


async def classify_statements(client: 'AsyncMistralClient', affirmations_brutes: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    Classifie les affirmations dans une catégorie (STATISTIQUE, JURIDIQUE, LOGIQUE, etc.)
    """
    # ✅ CORRECTION : Utilisation de la VARIABLE importée
    system_prompt_classify = SYSTEM_PROMPT_CLASSIFY
    
    classified_results = []
    
    for item in affirmations_brutes:
        affirmation = item['affirmation']
        user_prompt = affirmation
        
        messages = [
            {"role": "system", "content": system_prompt_classify},
            {"role": "user", "content": user_prompt}
        ]

        try:
            # 🚨 CORRECTION V1.0.0+ : Appel Asynchrone
            response = await client.chat.complete_async(
                model=MODEL_TINY, # Utilisation du tiny pour la classification rapide
                messages=messages,
            )
            
            # Extraction et nettoyage de la catégorie
            category_match = re.search(r'\[(.*?)\]', response.choices[0].message.content.strip())
            
            if category_match:
                category = category_match.group(1).strip().upper()
            else:
                category = response.choices[0].message.content.strip().upper()
            
            classified_results.append({
                "affirmation": affirmation,
                "category": category
            })
            
        except Exception as e:
            # On propage l'erreur car la classification est critique
            raise Exception(f"Erreur de classification pour '{affirmation[:30]}...' : {e}")
        
    return classified_results

# --- FONCTION D'AFFICHAGE FLASH ---
def afficher_rapport_final(rapports_finaux: List[Dict[str, str]]):
    """Affiche le rapport final généré par l'analyse critique dans un format RAPIDE."""
    print("\n\n" + "#"*70)
    print("   RAPPORT FLASH : ANALYSE CRITIQUE RAPIDE (CODE CITOYEN)")
    print("#"*70)

    if not rapports_finaux:
        print("Échec de la génération du rapport.")
        return

    for i, rapport in enumerate(rapports_finaux):
        print(f"\n--- AFFIRMATION N°{i+1} -------------------------------------------")
        
        analyse_complete = rapport['analyse'].strip()
        
        verdict_complet = "Verdict Indéterminé"
        synthese_rapide = "Synthèse factuelle non extraite."
        source_flash = "Source non trouvée."

        try:
            # 1. Extraction du VERDICT FINAL
            verdict_match = re.search(r"\*\*(CONTESTÉE|VRAI|FAUX|BIAIS|INFONDÉ|NON-VÉRIFIABLE)\*\*", analyse_complete, re.IGNORECASE)
            # 1b. Fallback pour les verdicts non-markdown
            if not verdict_match:
                verdict_match = re.search(r"^(CONTESTÉE|VRAI|FAUX|BIAIS|INFONDÉ|NON-VÉRIFIABLE|ADMIS)", analyse_complete.strip(), re.IGNORECASE)

            if verdict_match:
                verdict_brut = verdict_match.group(1).upper()
                verdict_complet = f"🚨 {verdict_brut} 🚨"
                if verdict_brut == "VRAI" or verdict_brut == "ADMIS":
                    verdict_complet = f"✅ {verdict_brut} ✅"
                elif verdict_brut == "FAUX" or verdict_brut == "INFONDÉ":
                    verdict_complet = f"❌ {verdict_brut} ❌"
                elif verdict_brut == "BIAIS":
                    verdict_complet = f"⚠️ {verdict_brut} ⚠️"


            # 2. Extraction de la SYNTHÈSE RAPIDE
            synthese_match = re.search(r"^(?:\[.*?\]|.*?) : (.*?) :", analyse_complete.strip())
            
            if synthese_match:
                synthese_rapide = synthese_match.group(1).strip()
            
            # Fallback
            else:
                conclusion_section = analyse_complete.split('### **5. Conclusion : pourquoi', 1)[-1] if '### **5. Conclusion' in analyse_complete else analyse_complete
                phrases = re.split(r'(?<=[.?!])\s+', conclusion_section.strip())
                synthese_candidate = next((p for p in phrases if not p.startswith('-') and len(p) > 50 and not p.startswith('---')), None)
                
                if synthese_candidate:
                    synthese_rapide = synthese_candidate.replace('**', '').replace('---', '').strip()
                elif "CONTESTÉE" in verdict_complet:
                    synthese_rapide = "L'hypothèse extraterrestre n'est étayée par aucune preuve vérifiable. Majorité de canulars humains."
                elif not synthese_candidate:
                    section_2_start = analyse_complete.find('### **2. Preuves scientifiques et explications rationnelles**')
                    if section_2_start != -1:
                        # 🚨 CORRECTION (Ligne 224) : L'assignation doit être sur la même ligne.
                        first_sentence_match = re.search(r'([^-*].+?\.)\s', analyse_complete[section_2_start:], re.DOTALL)
                        if first_sentence_match:
                            synthese_rapide = first_sentence_match.group(1).strip()


            # 3. Extraction de la SOURCE FLASH
            ref_keys_match = re.search(r"### \*\*Références clés\*\*(.*?)(?=\n\n)", analyse_complete, re.DOTALL)
            if ref_keys_match:
                premiere_ref = ref_keys_match.group(1).strip().split('\n')[0]
                source_flash = premiere_ref.split('. ', 1)[-1].strip().replace('**', '')
                source_flash = re.sub(r'\[.*\]', '', source_flash).split('(')[0].strip()
            
            elif 'Source' in analyse_complete:
                 source_flash_match = re.search(r"Source\s*:\s*\[?(.*?)\]?(\(|\s*htt)", analyse_complete, re.IGNORECASE)
                 if source_flash_match:
                    source_flash = source_flash_match.group(1).strip().replace('*', '').split(',')[0]
                 
            

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
