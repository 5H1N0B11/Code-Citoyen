"""Empreintes vocales ECAPA-TDNN (SpeechBrain) — bien plus discriminantes que Resemblyzer.

Modèle public `speechbrain/spkrec-ecapa-voxceleb` (entraîné sur VoxCeleb, état de l'art de
la vérification du locuteur). ~80 Mo téléchargés UNE fois depuis HuggingFace (pas de token),
puis 100% local. Tourne sur CPU (rapide) — aucun conflit GPU.

Sert à : diarisation (séparer les voix) et reconnaissance vocale (base d'empreintes
inter-vidéos). Embeddings de dimension 192, comparés par similarité cosinus.
"""
import logging
import os
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

ECAPA_SAMPLE_RATE = 16000
_ENCODER = None
ECAPA_DEVICE = os.environ.get("ECAPA_DEVICE", "cpu")
_SAVEDIR = os.environ.get("ECAPA_SAVEDIR", "data/models/ecapa")


def _get_encoder():
    """Charge (lazy + singleton) le classifieur ECAPA SpeechBrain."""
    global _ENCODER
    if _ENCODER is None:
        from speechbrain.inference.speaker import EncoderClassifier
        logger.info(f"Chargement ECAPA-TDNN (SpeechBrain) sur {ECAPA_DEVICE}…")
        _ENCODER = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir=_SAVEDIR,
            run_opts={"device": ECAPA_DEVICE},
        )
    return _ENCODER


def embed_wav(chunk: np.ndarray) -> Optional[np.ndarray]:
    """Empreinte vocale (192-d) d'un extrait audio mono 16 kHz (numpy float).
    Renvoie None en cas d'échec. Chunk attendu : déjà à 16 kHz mono normalisé."""
    try:
        import torch
        enc = _get_encoder()
        sig = torch.from_numpy(np.asarray(chunk, dtype=np.float32)).unsqueeze(0)
        with torch.no_grad():
            emb = enc.encode_batch(sig)
        return emb.squeeze().detach().cpu().numpy().astype(np.float32)
    except Exception as e:
        logger.debug(f"[ECAPA] embed échec : {e}")
        return None


def is_available() -> bool:
    try:
        import speechbrain  # noqa: F401
        return True
    except Exception:
        return False
