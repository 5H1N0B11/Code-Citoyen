from duckduckgo_search import DDGS
import time

# Configuration du moteur DuckDuckGo
# DDGS utilise souvent des requêtes non authentifiées, ce qui est parfait pour le Code Citoyen.
# Note: Nous allons limiter le nombre de résultats pour ne pas surcharger l'ordinateur
MAX_RESULTS_PAR_RECHERCHE = 3 

def fact_check_affirmations(affirmations_a_verifier, langue='fr'):
    """
    Recherche des sources et des vérifications existantes pour chaque affirmation.
    
    Args:
        affirmations_a_verifier (list[str]): Liste des phrases extraites par le Module 3.
        langue (str): Code de langue pour la recherche (par défaut: français).
        
    Returns:
        list[dict]: Liste des résultats de recherche pour chaque affirmation.
    """
    
    print("\n--- Démarrage du Module 4 : Fact-Checking (DuckDuckGo) ---")
    
    resultats_bruts = []
    
    # Initialisation du moteur de recherche DDGS
    with DDGS() as ddgs:
        
        for affirmation in affirmations_a_verifier:
            print(f"\n🔍 Recherche de preuves pour : '{affirmation[:50]}...'")
            
            # Formuler la requête (on ajoute "fact check" ou "vérification" implicitement en ciblant le contenu)
            # Pour plus de pertinence, on pourrait ajouter "vrai ou faux" ou "fact check" à la requête
            requete = f"{affirmation} vérification"
            
            # Lancement de la recherche web
            try:
                resultats_web = ddgs.text(
                    keywords=requete,
                    region=langue,
                    max_results=MAX_RESULTS_PAR_RECHERCHE
                )
            except Exception as e:
                print(f"Erreur de connexion à DuckDuckGo pour '{requete}' : {e}")
                resultats_web = []
            
            # Structure du résultat
            resultat_pour_ia = {
                "affirmation": affirmation,
                "preuves": list(resultats_web) # Conversion en liste pour le stockage
            }
            resultats_bruts.append(resultat_pour_ia)
            
            # Temporisation pour ne pas surcharger le serveur de recherche
            time.sleep(1) 

    print("\n--- Fin du Fact-Checking. Résultats prêts pour l'analyse IA. ---")
    return resultats_bruts

# --- Test (Simulé) ---
if __name__ == '__main__':
    # Exemple de sortie du Module 3
    affirmations_simulees = [
        "Le chômage a baissé de 10% depuis 2022.",
        "L'entreprise Total a investi 5 milliards d'euros en France l'année dernière."
    ]
    
    resultats = fact_check_affirmations(affirmations_simulees)
    
    # Affichage des résultats pour le test
    for item in resultats:
        print(f"\n[Affirmation] : {item['affirmation']}")
        if item['preuves']:
            print(f"[Preuves trouvées] : {len(item['preuves'])}")
            for preuve in item['preuves']:
                print(f"  - {preuve['title']} ({preuve['href']})")
        else:
            print("  - Aucune preuve trouvée.")
