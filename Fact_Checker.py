from googlesearch import search 
import time
import re
from typing import List, Dict, Any

# Configuration du Fact-Checker
MAX_RESULTS_PAR_RECHERCHE = 3 
DOMAINES_FACT_CHECK = [
    "lemonde.fr/les-decodeurs", 
    "afp.com/fr/factuel", 
    "liberation.fr/checknews", 
    "rts.ch/info/verification",
    "factuel.afp.com"
] 


def fact_check_affirmations(affirmations_a_verifier: List[str], langue: str = 'fr') -> List[Dict[str, Any]]:
    """
    Recherche des sources et des vérifications existantes pour chaque affirmation en utilisant Google.
    """
    
    print("\n--- Démarrage du Module 4 : Fact-Checking (V8 - Correction Finale Google) ---")
    
    resultats_bruts = []
    
    # 1. Préparation de la requête ciblée sur les sites de vérification
    requete_domaines = " OR ".join([f"site:{dom}" for dom in DOMAINES_FACT_CHECK])

    for affirmation in affirmations_a_verifier:
        affirmation_nettoyee = re.sub(r'[«»“”"]', '', affirmation).strip()
        
        print(f"\n🔍 Recherche de preuves pour : '{affirmation_nettoyee[:50]}...'")
        
        resultats_web = []

        # --- STRATÉGIE CIBLÉE (Utilisation de l'opérateur Google 'site:') ---
        requete_ciblee = f'"{affirmation_nettoyee}" {requete_domaines}'
        
        try:
            # CORRECTION FINALE : pause=2 remplacé par sleep_interval=2
            urls_ciblees = list(search(requete_ciblee, num_results=MAX_RESULTS_PAR_RECHERCHE, lang=langue, sleep_interval=2))
            
            for url in urls_ciblees:
                resultats_web.append({"title": f"CIBLÉ: {url}", "href": url})
        
        except Exception as e:
            print(f"Erreur de recherche Google (Ciblée) : {e}")
        
        # --- STRATÉGIE DE REPLI (FALLBACK) ---
        if not resultats_web:
            print("⚠️ Recherche ciblée échouée. Tentative de recherche large (sources brutes).")
            
            requete_simple = f'{affirmation_nettoyee} vérification' 
            
            try:
                # CORRECTION FINALE : pause=2 remplacé par sleep_interval=2
                urls_larges = list(search(requete_simple, num_results=MAX_RESULTS_PAR_RECHERCHE, lang=langue, sleep_interval=2))
                
                for url in urls_larges:
                    if not any(r['href'] == url for r in resultats_web):
                        resultats_web.append({"title": f"LARGE: {url}", "href": url})
                        
            except Exception as e:
                print(f"Erreur de recherche Google (Fallback) : {e}")


        # Structure du résultat pour le Module 5 (IA)
        resultat_pour_ia = {
            "affirmation": affirmation,
            "preuves": resultats_web
        }
        resultats_bruts.append(resultat_pour_ia)
        
        # 🚨 CORRECTION : Temporisation supprimée pour accélérer le batch
        # time.sleep(1) 

    print("\n--- Fin du Fact-Checking. Résultats prêts pour l'analyse IA. ---")
    return resultats_bruts

# --- Test (Simulé) ---
if __name__ == '__main__':
    affirmations_simulees = [
        "Le chômage a baissé de 10% depuis 2022.",
        "L'entreprise Total a investi 5 milliards d'euros en France l'année dernière."
    ]
    
    resultats = fact_check_affirmations(affirmations_simulees)
    
    # Affichage des résultats pour le test
    for item in resultats:
        print(f"\n[Affirmation] : {item['affirmation']}")
        if item['preuves']:
            source_type = 'Ciblée' if 'CIBLÉ:' in item['preuves'][0].get('title', '') else 'Large'
            print(f"[Preuves trouvées] : {len(item['preuves'])} (Source: {source_type})")
            for preuve in item['preuves']:
                print(f"  - {preuve.get('title', 'Titre non disponible')} ({preuve.get('href', 'URL non disponible')})")
        else:
            print("  - Aucune preuve donnée.")
