from mistralai.client import MistralClient
import os
from typing import List, Dict, Any

# Récupération de la clé d'API Mistral (DOIT être définie dans votre environnement !)
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")
MODEL_NAME = "mistral-tiny" # Modèle rapide et efficace pour le fact-checking

# Le prompt système dicte la méthode et la déontologie de l'IA (votre esprit critique)
SYSTEM_PROMPT_CRITIQUE = (
    "Votre rôle est d'agir comme un vérificateur de faits (fact-checker) neutre et objectif. "
    "Vous devez baser chaque affirmation sur des sources crédibles, récentes et vérifiables. "
    "NE JAMAIS inventer, extrapoler ou deviner. Si l'information n'est pas vérifiable, écrivez : 'Je ne sais pas - Information non sourcée/vérifiable.' "
    "Expliquez le raisonnement critique, identifiez les biais éventuels, et PRIORISEZ l'exactitude."
    "Le rapport final doit être structuré de manière concise."
)


def analyser_et_critiquer(resultats_fact_checker: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    Analyse les affirmations et les preuves pour générer un rapport critique sourcé.
    """
    
    if not MISTRAL_API_KEY:
        print("Erreur: La clé MISTRAL_API_KEY n'est pas définie dans l'environnement.")
        return []

    client = MistralClient(api_key=MISTRAL_API_KEY)
    rapports_finaux = []
    
    print("\n--- Démarrage du Module 5 : Analyse Critique (V. Robuste) ---")
    
    for item in resultats_fact_checker:
        affirmation = item['affirmation']
        preuves = item['preuves']
        
        # 1. Formatage des preuves pour le LLM
        preuves_formattees = "\n".join([f"- Titre: {p.get('title', 'N/A')}\n  URL: {p.get('href', 'N/A')}" for p in preuves])
        if not preuves_formattees or "N/A" in preuves_formattees:
             preuves_formattees = "AUCUNE SOURCE WEB UTILE TROUVÉE PAR LE FACT-CHECKER AUTOMATIQUE. Basez l'analyse uniquement sur des connaissances génériques et reconnaissez que l'affirmation est Non-vérifiable pour l'instant."
        
        user_prompt = f"""
        Affirmation à vérifier: "{affirmation}"

        Sources et liens trouvés:
        {preuves_formattees}

        En utilisant les principes de vérification stricts:
        1. Évaluez la véracité de l'affirmation.
        2. Identifiez et citez le lien le plus pertinent ou les faits clés.
        3. Si les sources sont insuffisantes ou non pertinentes, indiquez-le clairement.
        4. Fournissez un verdict (Vrai, Faux, Non-vérifiable, Nuancé).
        """
        
        # 2. Utilisation de la structure Dictionnaire standard (messages=...) au lieu de ChatMessage
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT_CRITIQUE},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            chat_response = client.chat(model=MODEL_NAME, messages=messages)
            
            rapport_final = {
                "affirmation": affirmation,
                "analyse": chat_response.choices[0].message.content
            }
            rapports_finaux.append(rapport_final)
            print(f"✅ Rapport généré pour: '{affirmation[:40]}...'")
            
        except Exception as e:
            print(f"Erreur d'appel API Mistral pour '{affirmation[:40]}...': {e}")
            
    return rapports_finaux


# --- Test (Simulé) ---
if __name__ == '__main__':
    # Nous simulons une sortie pour tester le Module 5, même avec des preuves vides
    resultats_simules = [
        {
            "affirmation": "Le chômage a baissé de 10% depuis 2022.",
            "preuves": [] 
        },
        {
            "affirmation": "Le coût du programme spatial français atteint 3 milliards d'euros cette année.",
            "preuves": [ 
                {"title": "Fact-check: Budget CNES 2024", "href": "https://www.fakelink.com/cnes-budget"},
                {"title": "L'Europe spatiale et le budget national", "href": "https://www.fakelink.com/espace-europe"}
            ]
        }
    ]
    
    rapports = analyser_et_critiquer(resultats_simules)
    
    print("\n--- RÉSULTATS FINAUX (Simulation) ---")
    for rapport in rapports:
        print("\n" + "="*50)
        print(f"AFFIRMATION: {rapport['affirmation']}")
        print("="*50)
        print(rapport['analyse'])
