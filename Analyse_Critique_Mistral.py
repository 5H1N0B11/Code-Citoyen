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

# --- LE PROMPT SYSTÈME DÉFINITIF ET UNIVERSEL (V2.0) ---
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

# Initialiser le client Mistral
try:
    CLIENT = MistralClient(api_key=MISTRAL_API_KEY)
except Exception:
    CLIENT = None

# --- FONCTION D'ANALYSE ASYNCHRONE RÉELLE ---
async def async_analyser_critiquer(resultat_fact_checker: Dict[str, Any]) -> Dict[str, str]:
    """
    Lance l'analyse critique avec Mistral de manière asynchrone.
    """
    if not CLIENT or not MISTRAL_API_KEY:
        return {"affirmation": resultat_fact_checker['affirmation'], "analyse": "Erreur: Client Mistral non disponible. Vérifiez MISTRAL_API_KEY."}

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

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_CRITIQUE},
        {"role": "user", "content": user_prompt}
    ]
    
    def call_mistral_sync():
        start_time = time.time()
        response = CLIENT.chat(
            model=MODEL_NAME,
            messages=messages
        )
        end_time = time.time()
        print(f"[Analyse IA] Temps d'appel Mistral : {end_time - start_time:.2f}s")
        return response

    try:
        chat_response = await asyncio.to_thread(call_mistral_sync)
        
        return {
            "affirmation": affirmation,
            "analyse": chat_response.choices[0].message.content
        }
        
    except Exception as e:
        return {"affirmation": affirmation, "analyse": f"Erreur d'appel API Mistral : {e}"}


# La fonction synchrone est conservée vide pour l'instant
def analyser_et_critiquer(resultats_fact_checker: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    return []

if __name__ == '__main__':
    print("Ce fichier ne doit pas être exécuté directement en mode asynchrone.")
