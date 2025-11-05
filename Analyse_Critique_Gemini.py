# Fichier : Analyse_Critique_IA.py (Configuration Gemini 2.5 Flash)
# Ce fichier utilise le SDK Google GenAI pour l'analyse critique la plus nuancée.

import asyncio
import os
from typing import List, Dict, Any
import time

# --- Clients d'API : Utilisation de Google GenAI ---
try:
    from google import genai
    from google.genai.errors import APIError
except ImportError:
    # Ce message s'affichera si l'utilisateur n'a pas exécuté 'pip install google-genai'
    print("Erreur: Le package 'google-genai' n'est pas installé. Veuillez exécuter 'pip install google-genai'.")
    genai = None
    APIError = Exception

# Clé API Gemini : Lue depuis la variable d'environnement
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
MODEL_NAME = "gemini-2.5-flash" 

# --- LE PROMPT SYSTÈME DÉFINITIF ET UNIVERSEL (V2.0 - Rigoureux et Éthique) ---
SYSTEM_PROMPT_CRITIQUE = (
    "RÉPONDEZ EXCLUSIVEMENT EN FRANÇAIS. "
    "Votre rôle est d'agir comme un vérificateur de faits (fact-checker) neutre, objectif et académique. "
    
    "MISSION PRIORITAIRE : CRITIQUE ACADÉMIQUE DES IDÉES. L'analyse conceptuelle doit toujours primer sur le verdict factuel simple."
    
    "RÈGLES D'HONNÊTETÉ ET DE RIGUEUR : "
    "1. Ne JAMAIS inventer, extrapoler ou deviner. "
    "2. Si la vérification factuelle échoue (absence de preuves web), le Verdict Final DOIT être 'Non-vérifiable'. "
    "3. La critique doit IMPÉRATIVEMENT se concentrer sur la DOCTRINE/l'IDÉE/le CONCEPT et non sur les individus (croyants, populations, personnalités). "
    "4. Interdiction de simplifier l'analyse par un 'biais de sécurité' (ex: rejeter une comparaison par la simple distinction religion vs. politique)."
    
    "STRUCTURE OBLIGATOIRE ET DÉTAILLÉE DE L'ANALYSE (Utiliser des listes à puces) : "
    
    "## 1. ANALYSE CRITIQUE ET CONFRONTATION D'IDÉES "
    "Cette section évalue la validité conceptuelle de l'affirmation."
    "   * **Définition du Cadre Académique :** Définir les termes clés de l'affirmation (ex: 'Totalitarisme', 'Idéologie', 'Fascisme') en citant l'auteur académique le plus pertinent (ex: Arendt, Eco, Popper, Rawls). "
    "   * **Focus Sémantique :** Distinguer le Sujet analysé (ex: la doctrine religieuse, le corpus textuel) des individus/populations. Confirmer que l'analyse porte UNIQUEMENT sur l'Idée. "
    "   * **Confrontation Doctrinale/Idéologique :** "
    "       * Identifier et comparer les points d'alignement et les points de rupture entre la doctrine/sujet et les critères académiques cités. "
    "       * **Nuance Doctrinale :** Si le sujet est un corpus textuel, vous devez reconnaître la présence d'éléments totalisants (couverture de tous les aspects de la vie) ou utopiques (retour à un âge d'or), tout en expliquant pourquoi cela ne suffit pas à conclure à une équivalence totale (manque de Chef unique, de Parti, de monopole étatique). "
    "   * **Conclusion Conceptuelle :** L'affirmation est-elle une association pertinente, un sophisme (logique), une généralisation abusive ou une confusion de catégories ? "
    
    "## 2. VÉRIFICATION FACTUELLE "
    "Cette section évalue les preuves web fournies (chiffres, événements, citations)."
    "   * Résultat de la recherche : Évaluation de la pertinence des sources fournies. "
    "   * Verdict Factuel : Les sources confirment-elles ou infirment-elles la partie factuelle de l'affirmation ? "
    
    "## 3. VERDICT FINAL ET SYNTHÈSE "
    "Le verdict doit être concis et synthétiser les conclusions (1) et (2)."
    "   * **Verdict Méthodologique :** 'Validé', 'Invalidé', ou 'Non-vérifiable' (si les preuves web manquent). "
    "   * **Synthèse Critique :** Expliquer la raison du verdict, en priorisant TOUJOURS la conclusion de l'analyse des idées (Point 1). S'il y a un sophisme conceptuel ET un manque de preuves, la synthèse doit le mentionner clairement (Ex: 'Invalidé par l'analyse conceptuelle; non-vérifiable sur les faits')."
)

# Initialiser le client Gemini
try:
    CLIENT = genai.Client(api_key=GEMINI_API_KEY)
except Exception:
    CLIENT = None

# --- FONCTION D'ANALYSE ASYNCHRONE RÉELLE ---
async def async_analyser_critiquer(resultat_fact_checker: Dict[str, Any]) -> Dict[str, str]:
    """
    Lance l'analyse critique avec Gemini 2.5 Flash de manière asynchrone.
    """
    if not CLIENT or not GEMINI_API_KEY:
        return {"affirmation": resultat_fact_checker['affirmation'], "analyse": "Erreur: Client Gemini Pro non disponible. Vérifiez GEMINI_API_KEY et l'installation du SDK."}

    affirmation = resultat_fact_checker['affirmation']
    preuves = resultat_fact_checker['preuves']
    
    # Préparation du prompt utilisateur
    preuves_formattees = "\n".join([f"- Titre: {p.get('title', 'N/A')}\n  URL: {p.get('href', 'N/A')}" for p in preuves])
    if not preuves_formattees or "N/A" in preuves_formattees:
         preuves_formattees = "AUCUNE SOURCE WEB UTILE TROUVÉE. La vérification factuelle des chiffres/événements est impossible."
    
    user_prompt = f"""
    Affirmation à vérifier: "{affirmation}"

    Résultat de la vérification factuelle (sources web):
    {preuves_formattees}

    Rédigez l'analyse en suivant strictement les étapes de la STRUCTURE OBLIGATOIRE du System Prompt.
    """

    # Concatenation du System Prompt et du User Prompt
    full_prompt = SYSTEM_PROMPT_CRITIQUE + "\n\n--- SUJET UTILISATEUR ---\n\n" + user_prompt

    messages = [
        {"role": "user", "parts": [{"text": full_prompt}]}
    ]
    
    # La fonction d'appel synchrone pour utiliser asyncio.to_thread
    def call_gemini_sync():
        start_time = time.time()
        
        response = CLIENT.models.generate_content(
            model=MODEL_NAME,
            contents=messages
        )
        end_time = time.time()
        print(f"[Analyse IA] Temps d'appel Gemini Pro : {end_time - start_time:.2f}s")
        return response

    try:
        chat_response = await asyncio.to_thread(call_gemini_sync)
        
        return {
            "affirmation": affirmation,
            "analyse": chat_response.text
        }
        
    except APIError as e:
        # Gère les erreurs courantes (Quota, Clé invalide, Nom de modèle incorrect)
        return {"affirmation": affirmation, "analyse": f"Erreur d'appel API Gemini Pro : {e}"}
    except Exception as e:
        return {"affirmation": affirmation, "analyse": f"Erreur non API lors de l'appel Gemini : {e}"}


# La fonction synchrone est conservée vide
def analyser_et_critiquer(resultats_fact_checker: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    return []

if __name__ == '__main__':
    print("Ce fichier ne doit pas être exécuté directement en mode asynchrone.")
