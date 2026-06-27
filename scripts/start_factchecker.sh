#!/bin/bash
# Lance le fact-checker CodeCitoyen en config de PRODUCTION figée (ship 2026-06-27).
# Modèle local mistral-nemo-citoyen-v4 + reroute déterministe + web search.
# Perf held-out : cat 73.7 / verd 67.8 / biais 59.2 (8 vidéos, golds audités).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR" || exit 1

# Config de prod (.env) — modèle, contexte, levier reroute, mode local
if [ -f ".env" ]; then set -a; source .env; set +a; fi

# Python du venv (le `python` système n'est pas garanti dans le PATH)
PY=".venv/bin/python"
[ -x "$PY" ] || PY="python"

# Vérifier qu'Ollama tourne et que le modèle est présent
if ! ollama list 2>/dev/null | grep -q "mistral-nemo-citoyen-v4"; then
    echo "⚠️  Modèle 'mistral-nemo-citoyen-v4' absent d'Ollama. Vérifie 'ollama list'."
fi

echo "============================================================"
echo "  CodeCitoyen — Fact-checker (PROD : v4 + reroute, web ON)"
LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
TAILSCALE_IP=$(tailscale ip -4 2>/dev/null | head -1)
[ -n "$LOCAL_IP" ] && echo "  Local  : http://${LOCAL_IP}:5000/app"
[ -n "$TAILSCALE_IP" ] && echo "  Mobile : http://${TAILSCALE_IP}:5000/app"
echo "============================================================"

exec "$PY" -m src.web.server
