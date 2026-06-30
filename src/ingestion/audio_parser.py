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
# Backend d'empreinte vocale : "ecapa" (SpeechBrain ECAPA-TDNN, BIEN plus discriminant —
# marge ~0.5 entre voix différentes vs voix identiques) ou "resemblyzer" (ancien, fusionnait
# les voix masculines proches). Défaut ECAPA si dispo.
EMBED_BACKEND = os.environ.get("EMBED_BACKEND", "ecapa")
# Seuil de DISTANCE cosinus (= 1 - similarité) en-deçà duquel deux embeddings = même locuteur.
# ECAPA : même locuteur dist ~0.4 (sim ~0.6), différents ~0.9 (sim ~0.1) → seuil 0.55.
# Resemblyzer : calibré 0.26 (marge bien plus faible).
_DEFAULT_DIAR_THR = "0.55" if EMBED_BACKEND == "ecapa" else "0.26"
DIARIZATION_THRESHOLD = float(os.environ.get("DIARIZATION_THRESHOLD", _DEFAULT_DIAR_THR))


def _embed_chunk(chunk):
    """Empreinte vocale d'un extrait 16 kHz mono, selon le backend choisi."""
    if EMBED_BACKEND == "ecapa":
        from .ecapa import embed_wav
        return embed_wav(chunk)
    return _get_voice_encoder().embed_utterance(chunk)
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


def diarize_audio_to_lookup(audio_path: str, expected_speakers: Optional[int] = None,
                            window_s: float = 2.5, hop_s: float = 1.25):
    """Diarise l'audio COMPLET par fenêtres glissantes, indépendamment de la transcription.

    Pensé pour le mode LIVE : on diarise une fois après le téléchargement, puis le
    streaming Whisper attribue le speaker de chaque segment par lookup sur son timestamp
    (le streaming ne peut pas clusteriser à la volée). 100% local (Resemblyzer), CPU.

    expected_speakers : nombre attendu de locuteurs (déduit du titre = nb d'intervenants + 1
        journaliste). Si fourni et que la diarisation sur-segmente (fréquent sur audio long :
        une même voix se scinde), on regroupe les clusters proches vers ce nombre (2e passe
        agglomérative sur les centroïdes), avec garde-fou anti-sur-fusion de voix distinctes.

    Returns: un tuple ``(speaker_at, centroids)`` où
      - ``speaker_at(t: float) -> Optional[str]`` renvoie le "Locuteur N" au timestamp t ;
      - ``centroids`` est un dict ``{"Locuteur N": np.ndarray}`` (empreinte moyenne du locuteur),
        utilisable pour la reconnaissance vocale (VoiceprintDB).
    Renvoie ``(None, {})`` si la diarisation est indisponible (lib absente, audio trop court…).
    """
    try:
        from resemblyzer import preprocess_wav
        import numpy as np
        from sklearn.cluster import AgglomerativeClustering
    except ImportError as e:
        logger.warning(f"Diarisation live indisponible (lib manquante) : {e}")
        return None, {}

    try:
        wav = preprocess_wav(audio_path)
        dur = len(wav) / RESEMBLYZER_SAMPLE_RATE
        wins: List[tuple] = []
        embs = []
        t = 0.0
        while t < dur:
            st, en = t, min(dur, t + window_s)
            if en - st >= 0.8:
                a = int(st * RESEMBLYZER_SAMPLE_RATE)
                b = int(en * RESEMBLYZER_SAMPLE_RATE)
                chunk = wav[a:b]
                if len(chunk) >= int(0.6 * RESEMBLYZER_SAMPLE_RATE):
                    e = _embed_chunk(chunk)
                    if e is not None:
                        embs.append(e)
                        wins.append((st, en))
            t += hop_s

        if len(embs) < 2:
            return None, {}

        X = np.stack(embs)
        labels = AgglomerativeClustering(
            n_clusters=None, distance_threshold=DIARIZATION_THRESHOLD,
            linkage="average", metric="cosine",
        ).fit(X).labels_

        # Fusion des petits clusters dans le plus proche gros cluster (anti-bruit).
        # Le fenêtrage produit beaucoup de fenêtres → un vrai locuteur en a des centaines.
        # On garde les clusters significatifs (≥ ~1/80 du total, plancher 8) et on réabsorbe
        # le reste, pour éviter les "Locuteur 7/8" parasites d'1-2 fenêtres.
        sizes: Dict[int, int] = {}
        for lbl in labels:
            sizes[int(lbl)] = sizes.get(int(lbl), 0) + 1
        min_keep = max(8, len(wins) // 80)
        big = [c for c, n in sizes.items() if n >= min_keep] or [max(sizes, key=sizes.get)]
        cent = {c: X[labels == c].mean(axis=0) for c in big}
        for i in range(len(labels)):
            if int(labels[i]) not in big:
                labels[i] = min(big, key=lambda c: float(np.linalg.norm(X[i] - cent[c])))

        # 2e passe ANTI-SUR-SEGMENTATION : sur audio long, une même voix donne plusieurs
        # clusters. Si on connaît le nombre attendu de locuteurs (du titre), on fusionne
        # itérativement les centroïdes LES PLUS PROCHES (= mêmes voix) jusqu'à ce nombre.
        # Garde-fou : on ne fusionne jamais deux centroïdes trop éloignés (voix distinctes).
        if expected_speakers and expected_speakers >= 1:
            def _ncent(c):
                v = X[labels == c].mean(axis=0)
                return v / (np.linalg.norm(v) + 1e-9)
            cur = {c: _ncent(c) for c in sorted(set(int(l) for l in labels))}
            HARD_CEIL = 0.55  # distance cosinus max pour fusionner (au-delà = voix vraiment différentes)
            while len(cur) > expected_speakers:
                items = list(cur.items())
                best = None
                for a in range(len(items)):
                    for b in range(a + 1, len(items)):
                        d = 1.0 - float(items[a][1] @ items[b][1])
                        if best is None or d < best[0]:
                            best = (d, items[a][0], items[b][0])
                if best is None or best[0] > HARD_CEIL:
                    break
                _, ca, cb = best
                labels[labels == cb] = ca
                cur[ca] = _ncent(ca)
                del cur[cb]

        # Renumérotation "Locuteur N" par ordre d'apparition.
        label_to_name: Dict[int, str] = {}
        nxt = 1
        ranges: List[tuple] = []
        for i, (st, en) in enumerate(wins):
            lbl = int(labels[i])
            if lbl not in label_to_name:
                label_to_name[lbl] = f"Locuteur {nxt}"
                nxt += 1
            ranges.append((st, en, label_to_name[lbl]))

        logger.info(f"Diarisation live : {len(label_to_name)} locuteur(s), {len(ranges)} fenêtres "
                    f"(seuil={DIARIZATION_THRESHOLD}).")
        midpoints = [( (st + en) / 2.0, name) for st, en, name in ranges]

        # Centroïde (empreinte moyenne) par "Locuteur N" — pour la reconnaissance vocale.
        centroids: Dict[str, "np.ndarray"] = {}
        for int_lbl, name in label_to_name.items():
            centroids[name] = X[labels == int_lbl].mean(axis=0)

        def speaker_at(ts: float) -> Optional[str]:
            if not midpoints:
                return None
            # Fenêtre dont le milieu est le plus proche du timestamp demandé.
            return min(midpoints, key=lambda m: abs(m[0] - ts))[1]

        return speaker_at, centroids
    except Exception as e:
        logger.warning(f"Diarisation live échouée (non bloquant) : {e}")
        return None, {}


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
