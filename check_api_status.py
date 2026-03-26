#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import os
import json
import sys
from mistralai import Mistral
from groq import AsyncGroq

async def check_mistral():
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        return "error", "MISTRAL_API_KEY non trouvée dans l'environnement."
        
    client = Mistral(api_key=api_key)
    try:
        # Appel minimaliste avec la syntaxe v1.x stricte
        response = await client.chat.complete_async(
            model="mistral-small-latest",
            messages=[{"role": "user", "content": "Réponds uniquement par 'OK'."}],
            max_tokens=5
        )
        return "ok", f"Réponse : {response.choices[0].message.content.strip()}"
    except Exception as e:
        err_msg = str(e)
        if "429" in err_msg:
            return "error", f"Rate Limit (429) atteint ! Ton quota est probablement épuisé. Détail : {err_msg}"
        return "error", f"Erreur inattendue. Détail : {err_msg}"
        
async def check_groq():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return "error", "GROQ_API_KEY non trouvée dans l'environnement."
        
    client = AsyncGroq(api_key=api_key)
    try:
        # Appel minimaliste
        response = await client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": "Réponds uniquement par 'OK'."}],
            max_tokens=5
        )
        return "ok", f"Réponse : {response.choices[0].message.content.strip()}"
    except Exception as e:
        err_msg = str(e)
        if "429" in err_msg:
            return "error", f"Rate Limit (429) atteint ! Détail : {err_msg}"
        return "error", f"Erreur inattendue. Détail : {err_msg}"
        
async def main():
    # Les print() sont redirigés vers stderr pour ne pas polluer la sortie JSON sur stdout
    sys.stderr.write("="*60 + "\n")
    sys.stderr.write("🚦 VÉRIFICATION DES QUOTAS API (RATE LIMITS) 🚦\n")
    sys.stderr.write("="*60 + "\n")
    
    mistral_status, mistral_msg = await check_mistral()
    sys.stderr.write(f"  - Mistral: {'✅ OK' if mistral_status == 'ok' else '❌ ERREUR'}\n")
    
    groq_status, groq_msg = await check_groq()
    sys.stderr.write(f"  - Groq: {'✅ OK' if groq_status == 'ok' else '❌ ERREUR'}\n")
    sys.stderr.write("="*60 + "\n")
    
    # Sortie JSON sur stdout pour être parsée par le serveur web
    final_status = {
        "mistral": {"status": mistral_status, "message": mistral_msg},
        "groq": {"status": groq_status, "message": groq_msg}
    }
    print(json.dumps(final_status))
    
    if mistral_status == "ok" and groq_status == "ok":
        sys.stderr.write("🚀 CONCLUSION : FEU VERT. Tu peux lancer l'analyse complète sereinement.\n")
        sys.exit(0)
    else:
        sys.stderr.write("🛑 CONCLUSION : FEU ROUGE. Une ou plusieurs API sont indisponibles.\n")
        sys.exit(1)
        
if __name__ == "__main__":
    asyncio.run(main())