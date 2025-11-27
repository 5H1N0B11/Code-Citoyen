import os
import time
from typing import List, Dict, Any
import asyncio
import argparse

# Pour que ce script fonctionne de manière autonome, il doit pouvoir trouver les modules dans core
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from .core.fact_checker import fact_check_affirmations
from .core.orchestrator import AnalysisOrchestrator
from .utils import extract_text_from_vtt

# --- MODULE 1 & 2 : SIMULATION DE L'EXTRACTION NLP ---
def simuler_extraction_affirmations(texte_source: str) -> List[str]:
    """
    Simule l'étape 1 (NLP) en extrayant des affirmations à vérifier.
    Normalement, un modèle NLP ferait cette extraction.
    """
    print("\n--- Module 1 & 2 : Extraction NLP (Simulation) ---")
    
    # Si le texte source est long, on prend les 3 premières phrases pour la démo
    affirmations = texte_source.split('.')[:3]
    if not affirmations or all(not a.strip() for a in affirmations):
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

async def run_code_citoyen(texte_source: str):
    """
    Orchestre l'exécution séquentielle de tous les modules du Fact-Checker.
    La fonction est maintenant asynchrone pour gérer les appels réseau.
    """
    
    print("="*70)
    print("🤖 DÉMARRAGE DU PROJET CODE CITOYEN : CHAÎNE DE VÉRIFICATION FACTUELLE")
    print("="*70)
    
    try:
        # 1. Initialisation de l'orchestrateur.
        # Pour ce script de test, nous créons l'orchestrateur ici.
        # L'application principale `live_fact_checker` a une gestion plus propre.
        print("Initialisation de l'orchestrateur...")
        orchestrator = await AnalysisOrchestrator.create()
        
        # 2. Extraction (Simulation des Modules 1 & 2)
        affirmations_a_verifier = simuler_extraction_affirmations(texte_source)
        await asyncio.sleep(1)
    
        # 3. Fact-Checking (Module 4) - Recherche Google
        # Cette fonction n'est pas asynchrone, mais pourrait l'être
        resultats_fact_checker = fact_check_affirmations(affirmations_a_verifier)
        await asyncio.sleep(1)
    
        # 4. Analyse Critique par l'IA (Module 5)
        # On passe les résultats du fact-checking (avec les preuves) à l'orchestrateur
        print("Lancement de l'analyse critique par l'IA...")
        rapports_finaux = await orchestrator.batch_analyze(resultats_fact_checker)
        await asyncio.sleep(1)
    
        # 5. Affichage du Rapport Final
        print("\n\n" + "#"*70)
        print("   RAPPORT FINAL : ANALYSE CRITIQUE DES AFFIRMATIONS (CODE CITOYEN)")
        print("#"*70)
    
        if not rapports_finaux:
            print("Échec de la génération du rapport : Vérifiez la clé API Mistral.")
            return
    
        for rapport in rapports_finaux:
            print("\n" + "="*50)
            print(f"AFFIRMATION: {rapport.get('affirmation', 'N/A')}")
            print("="*50)
            print(rapport.get('analyse', 'N/A'))
            
        print("\n" + "#"*70)
        print("FIN DE L'EXÉCUTION. Projet Code Citoyen terminé.")
        print("#"*70)
    except Exception as e:
        print(f"Une erreur est survenue dans l'orchestrateur principal: {e}")


# --- EXÉCUTION ---
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Code Citoyen - Fact-Checker")
    parser.add_argument('-f', '--file', type=str, help="Chemin vers un fichier .vtt à analyser.")
    args = parser.parse_args()

    # S'assurer que la clé API Mistral est définie
    if "MISTRAL_API_KEY" not in os.environ:
        print("ERREUR FATALE : La variable d'environnement MISTRAL_API_KEY n'est pas définie.")
        print("Veuillez exécuter : export MISTRAL_API_KEY=\"VOTRE_CLÉ\"")
    else:
        texte_a_analyser = ""
        if args.file:
            if os.path.exists(args.file) and args.file.endswith('.vtt'):
                print(f"Extraction du texte depuis le fichier VTT : {args.file}")
                texte_a_analyser = extract_text_from_vtt(args.file)
            else:
                print(f"Erreur : Le fichier '{args.file}' n'existe pas ou n'est pas un fichier .vtt.")
                sys.exit(1)
        else:
            # Le texte source que l'on veut analyser (contient les affirmations simulées)
            texte_a_analyser = """
            Un article prétend que le chômage a baissé de 10% depuis 2022. 
            Il affirme également que l'entreprise Total a investi 5 milliards d'euros en France l'année dernière. 
            De plus, il est mentionné que la dette publique française a dépassé les 120% du PIB en 2025.
            """
        
        if texte_a_analyser:
            asyncio.run(run_code_citoyen(texte_a_analyser))
