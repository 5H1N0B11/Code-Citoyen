#!/bin/bash
# Lance CodeCitoyen accessible sur Tailscale (et réseau local)
# Accès téléphone : http://<IP-Tailscale>:5000/app

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR" || exit 1

# Charger le .env si présent
if [ -f ".env" ]; then
    set -a; source .env; set +a
fi

echo ""
echo "============================================================"
echo "  Code Citoyen — Accès Mobile via Tailscale"
echo "============================================================"

# Récupérer l'IP Tailscale
TAILSCALE_IP=$(tailscale ip -4 2>/dev/null | head -1)
if [ -n "$TAILSCALE_IP" ]; then
    echo ""
    echo "  URL mobile : http://${TAILSCALE_IP}:5000/app"
    echo ""
else
    echo ""
    echo "  Tailscale non détecté — utilise l'IP locale :"
    LOCAL_IP=$(hostname -I | awk '{print $1}')
    echo "  URL mobile : http://${LOCAL_IP}:5000/app"
    echo ""
fi

echo "============================================================"
echo ""

python -m src.web.server
