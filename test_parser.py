
import sys
import os
import json

# Ajoute le répertoire src au python path pour permettre les imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from core.ingestion_pipeline import ingest_from_local_vtt

def test_vtt_parsing():
    """
    Script de test pour valider la logique de parsing VTT.
    """
    vtt_file = "data/input/Impôts, RN, Algérie... Éric Zemmour invité du Face à Face d'Apolline de Malherbe [NO8cUqaYxOM].fr.vtt"
    
    print(f"--- Lancement du test de parsing pour {vtt_file} ---")
    
    entries = ingest_from_local_vtt(vtt_file)
    
    if not entries:
        print("❌ Le parsing a échoué, aucune entrée retournée.")
        return

    print(f"✅ Parsing réussi. Total de {len(entries)} entrées extraites.")
    print("\n--- APERÇU DES 5 PREMIÈRES PHRASES RECONSTITUÉES ---")

    for entry in entries[:5]:
        spk = f"[{entry['speaker']}] " if entry.get('speaker') else ""
        print(f"  [T:{entry['start']:.2f}s] {spk}{entry['text']}")

    # Sauvegarde le résultat complet dans un fichier pour une inspection plus détaillée
    output_file = "parser_test_output.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
        
    print(f"\n✅ Résultat complet de l'analyse sauvegardé dans : {output_file}")

if __name__ == "__main__":
    test_vtt_parsing()
