#!/bin/bash
cd "$(dirname "${BASH_SOURCE[0]}")"
source .venv/bin/activate

# --- Mode LLM local (Ollama) ---
# Mistral Nemo 12B occupe ~9 GB de VRAM sur la RTX 5070 Ti, donc on force
# Whisper et la diarisation sur CPU pour ne pas se concurrencer en VRAM.
# Le Ryzen 9800X3D + 64 GB DDR5 absorbe sans problème.
export LLM_MODE="${LLM_MODE:-local}"
export WHISPER_DEVICE="${WHISPER_DEVICE:-cpu}"
export WHISPER_COMPUTE_TYPE="${WHISPER_COMPUTE_TYPE:-int8}"
export DIARIZATION_DEVICE="${DIARIZATION_DEVICE:-cpu}"

TAILSCALE_IP=$(tailscale ip -4 2>/dev/null | head -1)
echo ""
echo "  Mode LLM   : $LLM_MODE"
echo "  Whisper    : $WHISPER_DEVICE / $WHISPER_COMPUTE_TYPE"
echo "  Diarisation: $DIARIZATION_DEVICE"
echo ""
echo "  Desktop : http://localhost:5000"
echo "  Mobile  : http://${TAILSCALE_IP:-<IP-Tailscale>}:5000/app"
echo ""

python3 -m src.web.server
