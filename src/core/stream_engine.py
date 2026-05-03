"""
Moteur de Streaming et d'Analyse en Temps Réel.

Ce module contient la logique asynchrone pour traiter un flux de sous-titres (VTT/YouTube).
Il gère deux moteurs parallèles via une seule boucle de lecture :
1. Le "Radar" : Analyse le contexte global et met à jour le sujet roulant (toutes les 10 à 60s).
2. Le "Fact-Checker" : Sélectionne et analyse la meilleure affirmation d'une fenêtre temporelle (toutes les 15s).
"""
import asyncio
import logging
import json
import re
from typing import List, Dict, Any, Optional, Callable, Set
from datetime import datetime
from pathlib import Path

from ..utils import format_affirmation, TourDeControle, parse_llm_json, Config
from ..prompts.templates import WINDOW_SELECTION_SYSTEM_PROMPT, TOPIC_UPDATE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def _normalize_text(text: str) -> str:
    """Normalise un texte pour la comparaison : minuscules, ponctuation supprimée, espaces compressés."""
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', '', text.lower())).strip()


def _is_duplicate(candidate: str, analyzed_texts: Set[str]) -> bool:
    """
    Retourne True si candidate est trop similaire à une affirmation déjà analysée.
    Stratégie : correspondance exacte normalisée OU chevauchement de sous-chaîne
    bidirectionnel sur des textes > 20 caractères (couvre les légères variantes ASR).
    """
    norm = _normalize_text(candidate)
    if not norm:
        return False
    if norm in analyzed_texts:
        return True
    if len(norm) > 20:
        for existing in analyzed_texts:
            if len(existing) > 20 and (norm in existing or existing in norm):
                return True
    return False


def _find_best_timestamp(brute_text: str, buffer: List[Dict[str, Any]], default_ts: float) -> float:
    for cue in buffer:
        if brute_text in cue.get('affirmation', ''):
            return cue.get('video_timestamp', default_ts)
    return default_ts


async def _analyze_single_affirmation(
    selection: Dict[str, Any],
    buffer: List[Dict[str, Any]],
    last_analysis_ts: float,
    orchestrator: Any,
    global_context: str,
    current_main_topic: Optional[str],
    current_sub_topic: Optional[str],
    safe_get_history: Callable,
    safe_update_history: Callable,
    safe_get_formatted_history: Callable,
    results_list: List[Dict[str, Any]]
) -> None:
    """Analyse une affirmation sélectionnée et met à jour l'historique."""
    affirmation_text = selection["affirmation_corrigee"]
    affirmation_ts = selection.get("start")

    if affirmation_ts is None:
        affirmation_ts = _find_best_timestamp(selection["affirmation_brute"], buffer, last_analysis_ts)

    # P7 — récupérer le speaker depuis l'item du buffer le plus proche du timestamp.
    speaker: Optional[str] = None
    closest_buffer_item = None
    min_diff = float('inf')
    for item in buffer:
        item_ts = item.get('video_timestamp', item.get('start', 0.0))
        d = abs(item_ts - affirmation_ts)
        if d < min_diff:
            min_diff = d
            closest_buffer_item = item
    if closest_buffer_item:
        speaker = closest_buffer_item.get('speaker')

    history_items = safe_get_history()
    target_item_id = None
    min_ts_diff = float('inf')

    for item in reversed(history_items):
        if item.get("type") == "transcription" and item.get("status") == "pending":
            item_ts = item.get("video_timestamp", -1)
            ts_diff = abs(item_ts - affirmation_ts)
            if ts_diff < min_ts_diff:
                min_ts_diff = ts_diff
                target_item_id = item.get("id")
            if min_ts_diff < 0.5:
                break

    if target_item_id is None:
        logger.warning(f"Impossible de trouver un item de transcription à mettre à jour pour l'affirmation à {affirmation_ts}s.")
        return

    speaker_log = f" [speaker={speaker}]" if speaker else ""
    logger.info(f"Analyse de l'affirmation sélectionnée (ID: {target_item_id}){speaker_log}: '{affirmation_text}'")
    safe_update_history(target_item_id, {"status": "analyzing"})

    try:
        # P7 — historique filtré par speaker si dispo, sinon historique général.
        # Permet la détection de contradictions intra-débat par intervenant.
        history_for_analysis = safe_get_formatted_history(speaker=speaker) if speaker else safe_get_formatted_history()

        analysis_result = await orchestrator.analyze(
            affirmation=affirmation_text,
            history=history_for_analysis,
            global_context=global_context,
            main_topic=current_main_topic,
            sub_topic=current_sub_topic,
            speaker=speaker,
        )
        final_result = {
            "id": target_item_id,
            "timestamp": datetime.now().isoformat(),
            "affirmation": affirmation_text,
            "affirmation_brute": selection.get("affirmation_brute"),
            "result": analysis_result,
            "status": "done",
            "type": "analyse",
            "video_timestamp": affirmation_ts,
            "speaker": speaker,
        }
        safe_update_history(target_item_id, final_result)
        results_list.append(final_result)
    except Exception as analysis_err:
        logger.error(f"Erreur d'analyse pour l'affirmation ID {target_item_id}: {analysis_err}", exc_info=True)
        safe_update_history(target_item_id, {"status": "error", "result": {"error": str(analysis_err)}})


async def _run_fact_checker_window(
    buffer: List[Dict[str, Any]],
    last_analysis_ts: float,
    orchestrator: Any,
    global_context: str,
    current_main_topic: Optional[str],
    current_sub_topic: Optional[str],
    safe_get_history: Callable,
    safe_update_history: Callable,
    safe_get_formatted_history: Callable,
    results_list: List[Dict[str, Any]],
    output_filename: Path
) -> None:
    """Sélectionne et analyse les affirmations d'une fenêtre temporelle."""
    formatted_history = safe_get_formatted_history()
    selected_affirmations = await orchestrator.select_affirmation(
        buffer, formatted_history,
        main_topic=current_main_topic,
        sub_topic=current_sub_topic,
    )

    if not selected_affirmations:
        return

    # ── Déduplication Python — évite de reanalyser des affirmations déjà traitées ──
    # Le LLM (select_affirmation) est censé l'éviter via l'historique, mais rate parfois
    # les doublons inter-fenêtres. Ce filtre est O(n) et ne coûte aucun token.
    already_analyzed: Set[str] = {
        _normalize_text(item.get("affirmation", ""))
        for item in safe_get_history()
        if item.get("type") == "analyse" and item.get("status") == "done"
        and item.get("affirmation")
    }
    unique_selections = []
    for sel in selected_affirmations:
        text = sel.get("affirmation_corrigee", "")
        if _is_duplicate(text, already_analyzed):
            logger.info(f"[Dédup] Affirmation déjà analysée, ignorée : '{text[:60]}'")
        else:
            unique_selections.append(sel)
            # Ajouter immédiatement au set pour bloquer les doublons dans la même fenêtre
            already_analyzed.add(_normalize_text(text))

    if not unique_selections:
        logger.info("[Dédup] Toutes les affirmations de cette fenêtre sont des doublons — fenêtre ignorée.")
        return

    analysis_tasks = [
        _analyze_single_affirmation(
            sel, buffer, last_analysis_ts, orchestrator, global_context,
            current_main_topic, current_sub_topic,
            safe_get_history, safe_update_history, safe_get_formatted_history, results_list
        )
        for sel in unique_selections
    ]
    await asyncio.gather(*analysis_tasks)

    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(results_list, f, indent=2, ensure_ascii=False)


# ==============================================================================
# BOUCLE D'ANALYSE EN ARRIÈRE-PLAN
# ==============================================================================

async def background_analyze_task(
    sentence_producer: asyncio.Queue,
    video_id: str,
    global_context: str,
    orchestrator: Any,
    result_dir: Path,
    safe_add_history: Callable[[Dict[str, Any]], None],
    safe_update_history: Callable[[int, Dict[str, Any]], None],
    safe_get_history: Callable[[], List[Dict[str, Any]]],
    safe_get_formatted_history: Callable[..., List[Dict[str, str]]]
):
    """Tâche asynchrone principale qui orchestre le flux audio/texte."""
    if not orchestrator:
        logger.error("Orchestrator not ready.")
        return
    logger.info("[background_analyze_task] Début de l'analyse en mode streaming.")

    results_list = []
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = result_dir / f"web_youtube_{video_id}_{timestamp_str}.json"

    if global_context:
        context_metadata = {
            "timestamp": datetime.now().isoformat(),
            "type": "global_context",
            "video_id": video_id,
            "content": global_context
        }
        results_list.append(context_metadata)
        try:
            with open(output_filename, 'w', encoding='utf-8') as f:
                json.dump(results_list, f, indent=2, ensure_ascii=False)
        except Exception as save_err:
            logger.error(f"[Sauvegarde] Erreur initiale : {save_err}")

    # --- Phase 0 : Initialisation du sujet ---
    main_topic = None
    sub_topic = None
    if global_context:
        try:
            topic_result = await orchestrator.extract_topic(global_context=global_context)
            main_topic = topic_result.get("main_topic")
            sub_topic = topic_result.get("sub_topic")
            logger.info(f"[Phase 0] Sujet extrait : main_topic={main_topic!r}, sub_topic={sub_topic!r}")
            if main_topic or sub_topic:
                safe_add_history({
                    "timestamp": datetime.now().isoformat(),
                    "type": "topic_update",
                    "main_topic": main_topic,
                    "sub_topic": sub_topic,
                    "video_timestamp": 0.0
                })
        except Exception as e:
            logger.warning(f"[Phase 0] Échec extraction sujet (non bloquant) : {e}")

    current_main_topic = main_topic
    current_sub_topic = sub_topic
    current_summary = "Le débat commence. Présentation initiale."
    topic_buffer: List[Dict[str, Any]] = []
    last_topic_update_ts: float = 0.0

    async def update_rolling_topic(text_to_analyze: str, current_ts: float) -> None:
        nonlocal current_main_topic, current_sub_topic, current_summary
        user_content = (
            f"RÉSUMÉ PRÉCÉDENT : {current_summary}\n"
            f"SUJET ACTUEL : {current_main_topic} (Sous-sujet: {current_sub_topic})\n"
            f"TRANSCRIPTION (récente) :\n{text_to_analyze}"
        )
        try:
            topic_result = await orchestrator.update_topic_context(user_content)
            if not topic_result:
                return
            new_main = topic_result.get("sujet_principal")
            new_sub = topic_result.get("sous_sujet")
            new_summary = topic_result.get("resume")
            if new_summary:
                current_summary = new_summary
            topic_changed = False
            if new_main and new_main != current_main_topic:
                logger.info(f"[Radar] CHANGEMENT DE SUJET : '{current_main_topic}' -> '{new_main}'")
                current_main_topic = new_main
                current_sub_topic = new_sub
                topic_changed = True
            elif new_sub != current_sub_topic:
                logger.info(f"[Radar] CHANGEMENT DE SOUS-SUJET : '{current_sub_topic}' -> '{new_sub}'")
                current_sub_topic = new_sub
                topic_changed = True
            if topic_changed:
                safe_add_history({
                    "timestamp": datetime.now().isoformat(),
                    "type": "topic_update",
                    "main_topic": current_main_topic,
                    "sub_topic": current_sub_topic,
                    "video_timestamp": current_ts
                })
        except Exception as e:
            logger.error(f"[Radar] Erreur lors de la mise à jour du sujet : {e}", exc_info=True)

    # =========================================================================
    # BOUCLE PRINCIPALE DE STREAMING
    # =========================================================================
    buffer: List[Dict[str, Any]] = []
    last_analysis_ts: float = 0.0

    while True:
        try:
            sentence = await asyncio.wait_for(sentence_producer.get(), timeout=Config.WINDOW_SIZE_SECONDS * 2)
        except asyncio.TimeoutError:
            logger.info("[Stream] Timeout. Fin de l'analyse.")
            break

        if sentence is None:
            logger.info("[Stream] Signal de fin de flux reçu.")
            break

        current_ts = sentence.get('video_timestamp', 0.0)
        if last_topic_update_ts == 0.0:
            last_topic_update_ts = current_ts

        safe_add_history(sentence)

        # Moteur Radar
        topic_buffer.append(sentence)
        if current_ts - last_topic_update_ts >= Config.RADAR_INTERVAL_SECONDS:
            text_to_analyze = " ".join([s.get('affirmation', '') for s in topic_buffer])
            if text_to_analyze.strip():
                await update_rolling_topic(text_to_analyze, current_ts)
            topic_buffer = []
            last_topic_update_ts = current_ts

        # Moteur Fact-Checker — P6: filtre pré-analyse des phrases trop courtes
        affirmation_text = sentence.get('affirmation', sentence.get('text', ''))
        if len(affirmation_text) >= 25 and len(affirmation_text.split()) >= 5:
            buffer.append(sentence)
        else:
            logger.debug(f"[P6] Phrase ignorée du buffer (trop courte): '{affirmation_text[:50]}'")

        if current_ts - last_analysis_ts >= Config.WINDOW_SIZE_SECONDS and buffer:
            try:
                await _run_fact_checker_window(
                    buffer, last_analysis_ts, orchestrator, global_context,
                    current_main_topic, current_sub_topic,
                    safe_get_history, safe_update_history, safe_get_formatted_history,
                    results_list, output_filename
                )
            except Exception as e:
                logger.error(f"Erreur dans la boucle d'analyse principale : {e}", exc_info=True)
            finally:
                buffer = []
                last_analysis_ts = current_ts

    # --- Traitement du dernier buffer ---
    if buffer:
        logger.info("[Stream] Traitement du buffer final.")
        try:
            await _run_fact_checker_window(
                buffer, last_analysis_ts, orchestrator, global_context,
                current_main_topic, current_sub_topic,
                safe_get_history, safe_update_history, safe_get_formatted_history,
                results_list, output_filename
            )
        except Exception as e:
            logger.error(f"Erreur dans le traitement du buffer final : {e}", exc_info=True)

    logger.info(f"[background_analyze_task] Analyse terminée pour {video_id}.")
