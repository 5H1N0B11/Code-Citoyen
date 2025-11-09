# Fichier : Analyse_Critique_IA.py (Configuration Mistral)

import asyncio
import os
from typing import List, Dict, Any
import time

# Importations spécifiques à Mistral
try:
    from mistralai.client import MistralClient
except ImportError:
    print("Erreur: Le package 'mistralai' n'est pas installé. Veuillez exécuter 'pip install mistralai'.")
    MistralClient = None

# Récupération de la clé d'API Mistral (DOIT être définie)
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")
MODEL_NAME = "mistral-tiny" 
# CLIENT est défini plus bas dans get_mistral_client()


# --- LE PROMPT SYSTÈME DÉFINITIF ET UNIVERSEL (V2.1 - Ajout de Rigueur du Verdict) ---
SYSTEM_PROMPT_CRITIQUE = (\
    "RÉPONDEZ EXCLUSIVEMENT EN FRANÇAIS. "\
    "Votre rôle est d'agir comme un vérificateur de faits (fact-checker) neutre, objectif et académique. "\
    \
    "MISSION PRIORITAIRE : CRITIQUE ACADÉMIQUE DES IDÉES. L'analyse conceptuelle doit toujours primer sur le verdict factuel simple."\
    \
    "RÈGLES D'HONNÊTETÉ ET DE RIGUEUR : "\
    "1. Ne JAMAIS inventer, extrapoler ou deviner. "\
    "2. Si la vérification factuelle échoue (absence de preuves web), le Verdict Final DOIT être 'Non-vérifiable'. "\
    "3. La critique doit IMPÉRATIVEMENT se concentrer sur la DOCTRINE/l'IDÉE/le CONCEPT et non sur les individus. "\
    "4. **RÈGLE CRITIQUE (Tranché)** : Si l'affirmation est **massivement infirmée** par le consensus scientifique ou les preuves officielles (ex: la Terre est plate, les crop circles sont des extraterrestres, les vaccins causent l'autisme), le verdict DOIT être **INFONDÉ** ou **FAUX**. Le verdict 'CONTESTÉ' est réservé aux affirmations où des experts légitimes et non marginaux s'opposent réellement."\
)


# --- FONCTIONS PUBLIQUES ---

def get_mistral_client(api_key: str) -> MistralClient:
    """Initialise et retourne le client Mistral."""
    if MistralClient and api_key:
        return MistralClient(api_key=api_key)
    raise NameError("Le client Mistral n'a pas pu être initialisé.")


async def ask_ma(client: MistralClient, user_question: str) -> str:
    """
    Mode de question unique pour l'orchestrateur (live_fact_checker.py).
    Utilise un prompt simplifié mais rigoureux pour une réponse rapide et factuelle.
    """
    
    # Modèle haute qualité (large) pour le mode 'ask'
    MODEL_HIGH_QUALITY = "mistral-large-latest" 
    
    # PROMPT MIS À JOUR POUR INSISTER SUR L'ANALYSE ET LA CONCISION
    # Le prompt pour le mode ASK n'utilise PAS le prompt système complexe ci-dessus, mais une version simplifiée.
    system_prompt = (\
        "Vous êtes l'IA d'analyse critique et de fact-checking Codecitoyen. "\
        "Règles d'action : **1. Répondez de manière factuelle, neutre et objective.** "\
        "**2. Citez OBLIGATOIREMENT vos sources (Auteur, Date, Lien si disponible).** **3. Allez au plus direct, évitez les formules conversationnelles inutiles.** "\
        "**4. Si l'affirmation est massivement infirmée par les preuves, le verdict DOIT être INFONDÉ ou FAUX.** "\
        "**5. Dites 'Je ne sais pas' si l'information n'est pas vérifiable.**"\
    )
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_question}
    ]

    try:
        # La fonction client.chat est asynchrone dans la nouvelle version
        response = await client.chat(
            model=MODEL_HIGH_QUALITY,
            messages=messages,
        )
        return response.choices[0].message.content
        
    except Exception as e:
        return f"Erreur lors de la communication avec l'IA: {e}"


async def fact_checker_batch_async(client: MistralClient, resultats_fact_checker: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    Lance l'analyse critique asynchrone de toutes les affirmations du batch.
    """
    
    print("\n--- Démarrage du Module 5 : Analyse Critique IA (MISTRAL) ---")
    
    # Liste des tâches asynchrones à exécuter
    tasks = [analyser_affirmation_async(client, item) for item in resultats_fact_checker]
    
    # Exécution parallèle des requêtes à l'IA
    rapports_finaux = await asyncio.gather(*tasks)
    
    print("✅ Fin de l'analyse critique par l'IA.")
    return rapports_finaux


async def analyser_affirmation_async(client: MistralClient, item: Dict[str, Any]) -> Dict[str, str]:
    """
    Analyse critique d'une seule affirmation en utilisant les sources web fournies.
    """
    affirmation = item["affirmation"]
    preuves = item["preuves"]
    
    # Formatage des preuves pour le prompt
    preuves_formattees = "\n".join([f"- Source: {p.get('title', 'N/A')} ({p.get('href', 'N/A')})" for p in preuves])
    
    # Sécurité: Si la recherche Google n'a rien donné
    if not preuves_formattees or "N/A" in preuves_formattees:
         preuves_formattees = "AUCUNE SOURCE WEB UTILE TROUVÉE. La vérification factuelle des chiffres/événements est impossible."
    
    user_prompt = f"""
Affirmation à vérifier: "{affirmation}"

Résultat de la vérification factuelle (sources web):
{preuves_formattees}

Rédigez l'analyse en suivant strictement les étapes de la STRUCTURE OBLIGATOIRE du System Prompt.
"""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_CRITIQUE},
        {"role": "user", "content": user_prompt}
    ]
    
    def call_mistral_sync():
        start_time = time.time()
        response = client.chat(
            model=MODEL_NAME,
            messages=messages
        )
        end_time = time.time()
        print(f"[Analyse IA] Temps d'appel Mistral : {end_time - start_time:.2f}s")
        return response

    try:
        # Utilisation de asyncio.to_thread pour les fonctions bloquantes/synchrones
        chat_response = await asyncio.to_thread(call_mistral_sync)
        
        return {
            "affirmation": affirmation,
            "analyse": chat_response.choices[0].message.content
        }
        
    except Exception as e:
        return {"affirmation": affirmation, "analyse": f"Erreur d'appel API Mistral : {e}"}


# La fonction synchrone est conservée vide pour l'instant
def analyser_et_critiquer(resultats_fact_checker: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Fonction synchrone de façade (non utilisée)."""
    return []

def afficher_rapport_final(rapports_finaux: List[Dict[str, str]]):
    """
    Affiche le rapport final après l'exécution du batch.
    """
    print("\n" + "#"*70)
    print("   RAPPORT FINAL : ANALYSE CRITIQUE DES AFFIRMATIONS (CODE CITOYEN)")
    print("#"*70)

    if not rapports_finaux:
        print("Échec de la génération du rapport : Vérifiez la clé API Mistral.")
        return

    for rapport in rapports_finaux:
        print("\n" + "="*50)
        print(f"AFFIRMATION: {rapport['affirmation']}")
        print("="*50)
        print(rapport['analyse'])
        
    print("\n" + "#"*70)
    print("FIN DE L'EXÉCUTION DU BATCH. Projet Code Citoyen terminé.")
    print("#"*70)
