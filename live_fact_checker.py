import asyncio
import time
import os
import sys
from typing import List, Dict, Any

# --- Importation du module d'analyse ---
# Le script principal a besoin d'importer la fonction critique.
# Assurez-vous que Analyse_Critique_IA.py est à jour (V59)
try:
    from Analyse_Critique_IA import async_analyser_critiquer 
except ImportError:
    print("Erreur: Le module Analyse_Critique_IA.py est introuvable ou contient une erreur.")
    sys.exit(1)

# --- Constantes pour l'affichage ---
SEPARATOR = "=" * 80
LINE_SEPARATOR = "-" * 20

# --- Fonctions d'entrée/sortie ---

def get_user_input() -> List[str]:
    """Capture les affirmations de l'utilisateur."""
    print(SEPARATOR)
    print("Mode Batch : Collez plusieurs affirmations séparées par des lignes vides.")
    print("Mode Manuel : Entrez une seule phrase.")
    print("Tapez 'quit' pour sortir.")
    print(SEPARATOR)
    print("🗣️ Entrez les phrases à Fact-Checker (ou 'quit' pour sortir) : ")
    
    lines = []
    while True:
        try:
            line = input("> ")
            if line.lower() == 'quit':
                return []
            if line.strip():
                lines.append(line.strip())
            else:
                # Si l'utilisateur entre une ligne vide, cela termine la saisie
                if lines:
                    break
        except EOFError:
            # Termine la saisie si EOF (ex: Ctrl+D)
            break
        except KeyboardInterrupt:
            print("\nSortie forcée par l'utilisateur.")
            return []
            
    # Traitement des lignes : une ligne vide (séparateur) déclenche la fin de la saisie
    affirmations = []
    for line in lines:
        if line.strip():
            affirmations.append({"affirmation": line.strip()})
    
    return affirmations

def display_report(results: List[Dict[str, str]]):
    """Affiche le rapport final avec la CATÉGORIE ajoutée."""
    
    print("\n" + SEPARATOR)
    print(f"🚀 RAPPORT FINAL : ANALYSE CRITIQUE (MODE BATCH)")
    print(SEPARATOR)

    for i, resultat in enumerate(results):
        print(f"\n{LINE_SEPARATOR} AFFIRMATION {i+1} {LINE_SEPARATOR}")
        print(f"AFFIRMATION: {resultat['affirmation']}")
        
        # --- LIGNE CLÉ AJOUTÉE pour le débug ---
        print(f"CATÉGORIE: {resultat['categorie']}") 
        # --------------------------------------
        
        print(f"VERDICT: {resultat['analyse']}")
        print(LINE_SEPARATOR)

    print("\n" + "#" * 30 + " FIN DE L'ANALYSE BATCH. " + "#" * 30)


# --- Fonction principale asynchrone ---

async def main():
    affirmations_input = get_user_input()
    
    if not affirmations_input:
        print("Aucune affirmation fournie. Fin du programme.")
        return

    print(SEPARATOR)
    print(f"🚀 DÉMARRAGE DU FACT-CHECKING ASYNCHRONE POUR {len(affirmations_input)} SAISIES")
    print(SEPARATOR)

    start_time = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] 🧠 Lancement des {len(affirmations_input)} analyses IA en parallèle...")

    # Créer les tâches d'analyse en utilisant async_analyser_critiquer
    tasks = [async_analyser_critiquer(item) for item in affirmations_input]
    
    # Exécuter les tâches en parallèle
    results = await asyncio.gather(*tasks)
    
    end_time = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] ✅ Analyses terminées en {end_time - start_time:.2f} secondes.")

    # Afficher le rapport
    display_report(results)

# --- Point d'entrée ---

if __name__ == '__main__':
    # Détecter si Python 3.7+ est utilisé pour asyncio.run
    if sys.version_info >= (3, 7):
        asyncio.run(main())
    else:
        # Fallback pour les anciennes versions
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
        loop.close()
