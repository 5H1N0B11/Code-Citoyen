import os
import time
from typing import List, Dict, Any

# Importation des fonctions des modules 
# Note : Nous importons directement les fonctions des fichiers que vous avez créés
from Fact_Checker import fact_check_affirmations
from Analyse_Critique_IA import analyser_et_critiquer

# --- MODULE 1 & 2 : SIMULATION DE L'EXTRACTION NLP ---
def simuler_extraction_affirmations(texte_source: str) -> List[str]:
    """
    Simule l'étape 1 (NLP) en extrayant des affirmations à vérifier.
    Normalement, un modèle NLP ferait cette extraction.
    """
    print("\n--- Module 1 & 2 : Extraction NLP (Simulation) ---")
    
    # Affirmations extraites du texte (simulées)
    affirmations = [
        "Le chômage a baissé de 10% depuis 2022.",
        "L'entreprise Total a investi 5 milliards d'euros en France l'année dernière.",
        "La dette publique française a dépassé les 120% du PIB en 2025."
    ]
    
    print(f"✅ {len(affirmations)} affirmations extraites et prêtes pour le Fact-Checking.")
    return affirmations

# ----------------------------------------------------------------------
# --- FONCTION PRINCIPALE D'ORCHESTRATION ---
# ----------------------------------------------------------------------

def run_code_citoyen(texte_source: str):
    """
    Orchestre l'exécution séquentielle de tous les modules du Fact-Checker.
    """
    
    print("="*70)
    print("🤖 DÉMARRAGE DU PROJET CODE CITOYEN : CHAÎNE DE VÉRIFICATION FACTUELLE")
    print("="*70)
    
    # 1. Extraction (Simulation des Modules 1 & 2)
    affirmations_a_verifier = simuler_extraction_affirmations(texte_source)
    time.sleep(1)

    # 2. Fact-Checking (Module 4)
    # Les résultats sont des liens trouvés (ou une liste vide en cas de blocage)
    resultats_fact_checker = fact_check_affirmations(affirmations_a_verifier)
    time.sleep(1)

    # 3. Analyse Critique par l'IA (Module 5)
    # L'IA utilise les résultats pour générer le rapport final critique
    rapports_finaux = analyser_et_critiquer(resultats_fact_checker)
    time.sleep(1)

    # 4. Affichage du Rapport Final
    print("\n\n" + "#"*70)
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
    print("FIN DE L'EXÉCUTION. Projet Code Citoyen terminé.")
    print("#"*70)


# --- EXÉCUTION ---
if __name__ == '__main__':
    # Le texte source que l'on veut analyser (contient les affirmations simulées)
    TEXTE_ARTICLE_SIMULE = """
    Un article prétend que le chômage a baissé de 10% depuis 2022. 
    Il affirme également que l'entreprise Total a investi 5 milliards d'euros en France l'année dernière. 
    De plus, il est mentionné que la dette publique française a dépassé les 120% du PIB en 2025.
    """
    
    # S'assurer que la clé API Mistral est définie
    if "MISTRAL_API_KEY" not in os.environ:
        print("ERREUR FATALE : La variable d'environnement MISTRAL_API_KEY n'est pas définie.")
        print("Veuillez exécuter : export MISTRAL_API_KEY=\"VOTRE_CLÉ\"")
    else:
        run_code_citoyen(TEXTE_ARTICLE_SIMULE)
