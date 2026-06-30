"""
Module d'ingestion par audio (ASR via faster-whisper).

Transcrit un fichier audio en liste de phrases datées, dans le même format
que `vtt_parser.reconstitute_sentences` — directement consommable par
`background_analyze_task`.

Avantages vs sous-titres YouTube auto :
  - Bien moins d'erreurs phonétiques (le LLM aura moins de "correction
    phonétique" à faire)
  - Ponctuation et casing propres
  - Pas de dépendance à la latence de YouTube
  - Diarisation optionnelle (qui parle quand) — 100% local via Resemblyzer

Diarisation : on utilise Resemblyzer (modèle vendored, ~30 MB) pour extraire
un embedding vocal par segment Whisper, puis AgglomerativeClustering pour
regrouper les segments par speaker. 100% local, aucun token requis.

Configuration (env vars) :
    WHISPER_MODEL          (défaut: large-v3-turbo)  — qualité top, ~1.5 GB VRAM
    WHISPER_DEVICE         (défaut: cuda)            — "cpu" si pas de GPU
    WHISPER_COMPUTE_TYPE   (défaut: float16)         — int8 si CPU
    WHISPER_LANGUAGE       (défaut: fr)              — code langue ISO
    DIARIZATION_THRESHOLD  (défaut: 0.65)            — seuil de clustering
                                                       (plus bas = plus de
                                                       speakers détectés)
"""

import os
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

WHISPER_MODEL_NAME = os.environ.get("WHISPER_MODEL", "large-v3-turbo")
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cuda")
WHISPER_COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "float16")
WHISPER_LANGUAGE = os.environ.get("WHISPER_LANGUAGE", "fr")

_whisper_model = None


def _get_whisper_model():
    """Charge faster-whisper en lazy + singleton (le modèle pèse plusieurs GB)."""
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        logger.info(
            f"Chargement Whisper '{WHISPER_MODEL_NAME}' sur "
            f"{WHISPER_DEVICE}/{WHISPER_COMPUTE_TYPE} (premier appel uniquement)..."
        )
        _whisper_model = WhisperModel(
            WHISPER_MODEL_NAME,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
        )
        logger.info("Whisper prêt.")
    return _whisper_model


def transcribe_audio_streaming(
    audio_path: str,
    on_segment,
) -> List[Dict[str, Any]]:
    """Transcrit en streaming : appelle ``on_segment(item)`` pour chaque
    segment dès qu'il sort du modèle (pas d'attente de fin de fichier).

    Cas d'usage : alimenter en direct la queue de phrases du pipeline
    pour que le LLM commence à analyser pendant que Whisper transcrit
    encore les minutes suivantes — on évite les ~3 min d'attente.

    Args:
        audio_path: chemin du fichier audio (lisible par ffmpeg).
        on_segment: callable thread-safe ``(item: Dict) -> None``.
            ``item`` est un dict ``{start, end, text, speaker=None}``.

    Returns:
        La liste complète des segments à la fin (utile pour la
        diarisation post-process si désirée).
    """
    model = _get_whisper_model()
    logger.info(f"Transcription streaming de {audio_path} ...")
    segments, info = model.transcribe(
        audio_path,
        language=WHISPER_LANGUAGE,
        vad_filter=True,
        beam_size=5,
    )

    sentences: List[Dict[str, Any]] = []
    for seg in segments:
        item = {
            "start": float(seg.start),
            "end": float(seg.end),
            "text": seg.text.strip(),
            "speaker": None,
        }
        sentences.append(item)
        try:
            on_segment(item)
        except Exception as e:
            logger.warning(f"on_segment callback error: {e}")

    logger.info(
        f"Transcription streaming terminée : {len(sentences)} segments "
        f"sur {info.duration:.1f}s d'audio (langue détectée: {info.language})"
    )
    return sentences


def transcribe_audio_to_sentences(
    audio_path: str,
    with_diarization: bool = False,
) -> List[Dict[str, Any]]:
    """Transcrit un fichier audio en phrases compatibles avec le pipeline.

    Args:
        audio_path: chemin du fichier audio (mp3, wav, mp4, m4a — tout
            format lisible par ffmpeg).
        with_diarization: si True, ajoute un champ `speaker` à chaque
            phrase via pyannote.audio. Nécessite HF_TOKEN configuré.

    Returns:
        Liste de dicts ``{start: float, text: str, speaker: Optional[str]}``.
    """
    model = _get_whisper_model()

    logger.info(f"Transcription de {audio_path} ...")
    segments, info = model.transcribe(
        audio_path,
        language=WHISPER_LANGUAGE,
        vad_filter=True,
        beam_size=5,
    )

    sentences: List[Dict[str, Any]] = []
    for seg in segments:
        sentences.append({
            "start": float(seg.start),
            "end": float(seg.end),
            "text": seg.text.strip(),
            "speaker": None,
        })

    logger.info(
        f"Transcription : {len(sentences)} segments en "
        f"{info.duration:.1f}s d'audio (langue détectée: {info.language})"
    )

    if with_diarization:
        sentences = _apply_diarization(audio_path, sentences)

    return sentences


_voice_encoder = None
# Seuil cosinus en-deçà duquel deux embeddings sont considérés "même speaker".
# Calibré sur Resemblyzer + voix françaises. À 0.30, deux voix masculines proches
# (ex. Bompard/Wauquiez) FUSIONNENT en 1 cluster. Balayage 2026-06-30 sur le débat
# Bompard/Wauquiez : 0.26 sépare correctement les 3 locuteurs (Bompard/Wauquiez/journaliste,
# clusters 304/338/118) ; 0.22 et en-dessous sur-découpent. 0.26 = meilleur compromis.
DIARIZATION_THRESHOLD = float(os.environ.get("DIARIZATION_THRESHOLD", "0.26"))
RESEMBLYZER_SAMPLE_RATE = 16000  # imposé par resemblyzer
# Resemblyzer demande des chunks ≥ 1.6s pour des embeddings stables. On
# étend les segments courts à 2.5s en piochant autour de leur centre.
MIN_CHUNK_SECONDS = 2.5
# On fusionne les micro-clusters (genre 1-2 segments isolés) dans le plus
# proche grand cluster pour éviter du bruit dans la sortie.
MIN_CLUSTER_SIZE = 3


DIARIZATION_DEVICE = os.environ.get("DIARIZATION_DEVICE", "cpu")


def _get_voice_encoder():
    """Charge Resemblyzer en lazy + singleton (modèle ~30 MB vendored, pas de download).
    Par défaut sur CPU pour ne pas concurrencer Mistral Nemo en VRAM."""
    global _voice_encoder
    if _voice_encoder is None:
        from resemblyzer import VoiceEncoder
        logger.info(f"Chargement du VoiceEncoder Resemblyzer sur {DIARIZATION_DEVICE}...")
        _voice_encoder = VoiceEncoder(device=DIARIZATION_DEVICE, verbose=False)
        logger.info("VoiceEncoder prêt.")
    return _voice_encoder


def _apply_diarization(audio_path: str, sentences: List[Dict]) -> List[Dict]:
    """Ajoute le champ 'speaker' à chaque phrase. 100% local via Resemblyzer.

    Stratégie :
      1. preprocess_wav charge l'audio en mono 16kHz normalisé
      2. Pour chaque segment Whisper, on extrait l'audio sur [start, end]
         (étendu à ≥ 1s pour la robustesse de l'embedding)
      3. VoiceEncoder produit un embedding vocal de dim 256
      4. AgglomerativeClustering avec un seuil cosinus regroupe les
         embeddings par speaker — pas besoin de connaître le nombre de
         speakers à l'avance.
    """
    if not sentences:
        return sentences

    try:
        from resemblyzer import preprocess_wav
        import numpy as np
        from sklearn.cluster import AgglomerativeClustering
    except ImportError as e:
        logger.warning(f"Diarisation indisponible (lib manquante) : {e}")
        return sentences

    encoder = _get_voice_encoder()

    logger.info(f"Diarisation Resemblyzer sur {len(sentences)} segments...")
    wav = preprocess_wav(audio_path)
    duration = len(wav) / RESEMBLYZER_SAMPLE_RATE

    valid_indices: List[int] = []
    embeddings: List[np.ndarray] = []
    for i, seg in enumerate(sentences):
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", start + 0.5))
        # Étendre les segments très courts (< MIN_CHUNK_SECONDS) en élargissant
        # l'intervalle, toujours en restant dans les bornes du wav
        if end - start < MIN_CHUNK_SECONDS:
            mid = (start + end) / 2
            half = MIN_CHUNK_SECONDS / 2
            start = max(0.0, mid - half)
            end = min(duration, mid + half)
        s_idx = int(start * RESEMBLYZER_SAMPLE_RATE)
        e_idx = int(end * RESEMBLYZER_SAMPLE_RATE)
        chunk = wav[s_idx:e_idx]
        if len(chunk) < int(0.4 * RESEMBLYZER_SAMPLE_RATE):
            continue  # vraiment trop court, on saute
        try:
            emb = encoder.embed_utterance(chunk)
            embeddings.append(emb)
            valid_indices.append(i)
        except Exception as e:
            logger.debug(f"[Diar] Embed échec sur segment {i} : {e}")
            continue

    if len(embeddings) < 2:
        logger.warning("Diarisation : moins de 2 embeddings valides — skip.")
        return sentences

    embeddings_np = np.stack(embeddings)

    clustering = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=DIARIZATION_THRESHOLD,
        linkage="average",
        metric="cosine",
    ).fit(embeddings_np)

    labels = clustering.labels_

    # Fusionner les micro-clusters (< MIN_CLUSTER_SIZE) dans le plus proche
    # grand cluster (par moyenne d'embedding).
    sizes: Dict[int, int] = {}
    for lbl in labels:
        sizes[int(lbl)] = sizes.get(int(lbl), 0) + 1
    big_clusters = [c for c, n in sizes.items() if n >= MIN_CLUSTER_SIZE]
    if len(big_clusters) >= 1:
        # Calculer le centroïde de chaque gros cluster
        centroids = {}
        for c in big_clusters:
            centroids[c] = embeddings_np[labels == c].mean(axis=0)
        for i in range(len(labels)):
            lbl = int(labels[i])
            if lbl not in big_clusters:
                # Réassigner au plus proche gros cluster
                best_c = min(
                    big_clusters,
                    key=lambda c: float(np.linalg.norm(embeddings_np[i] - centroids[c]))
                )
                labels[i] = best_c

    distinct = sorted(set(int(l) for l in labels))
    logger.info(
        f"Diarisation : {len(distinct)} speaker(s) détecté(s) "
        f"(seuil={DIARIZATION_THRESHOLD}, {len(embeddings)} segments embeddés)"
    )

    # Renumérotation par ordre d'apparition (speaker_0 = premier qui parle)
    label_to_speaker: Dict[int, str] = {}
    next_id = 0
    for idx_in_valid, original_idx in enumerate(valid_indices):
        lbl = int(labels[idx_in_valid])
        if lbl not in label_to_speaker:
            label_to_speaker[lbl] = f"speaker_{next_id}"
            next_id += 1
        sentences[original_idx]["speaker"] = label_to_speaker[lbl]

    # Pour les segments trop courts qui n'ont pas eu d'embedding : on hérite
    # du speaker du segment précédent (heuristique simple).
    last_speaker: Optional[str] = None
    for seg in sentences:
        if seg.get("speaker"):
            last_speaker = seg["speaker"]
        elif last_speaker:
            seg["speaker"] = last_speaker

    return sentences


# ---------------------------------------------------------------------------
# CLI rapide pour tester depuis la ligne de commande
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    import json

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="Transcrit un fichier audio via faster-whisper.")
    parser.add_argument("audio_path", help="Chemin vers le fichier audio")
    parser.add_argument("--diarize", action="store_true", help="Activer la diarisation (pyannote)")
    parser.add_argument("--output", "-o", help="Fichier de sortie JSON (sinon stdout)")
    args = parser.parse_args()

    sentences = transcribe_audio_to_sentences(args.audio_path, with_diarization=args.diarize)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(sentences, f, ensure_ascii=False, indent=2)
        print(f"{len(sentences)} segments → {args.output}")
    else:
        for s in sentences[:20]:
            spk = f"[{s['speaker']}] " if s.get("speaker") else ""
            print(f"[{s['start']:6.1f}s] {spk}{s['text']}")
        print(f"\n... ({len(sentences)} segments au total)")
