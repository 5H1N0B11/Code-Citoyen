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
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime
from pathlib import Path

from src.utils import format_affirmation

logger = logging.getLogger(__name__)

# ==============================================================================
# CONSTANTES POUR LA BOUCLE D'ANALYSE
# ==============================================================================

WINDOW_SIZE_SECONDS = 15  # Taille de la fenêtre d'analyse factuelle (le buffer)
MIN_GROQ_CALL_INTERVAL = 12.0  # Délai minimum entre deux appels à l'API Groq (Anti-RateLimit 429)

# Prompt système pour la SÉLECTION INTELLIGENTE d'une affirmation.
# Inclut les règles de correction ASR (fautes d'orthographe vocales) et de résolution des pronoms.
WINDOW_SELECTION_SYSTEM_PROMPT = (
    "Tu es un assistant d'analyse de discours politique en temps réel.\n\n"
    "On te donne :\n"
    "1. L'HISTORIQUE COMPLET de la discussion depuis le début (pour le contexte).\n"
    "2. Le BUFFER ACTUEL : les phrases prononcées dans les 15 dernières secondes.\n\n"
    "Ta mission : Sélectionner UNE SEULE affirmation du BUFFER ACTUEL qui mérite d'être fact-checkée.\n\n"
    "CRITÈRES DE SÉLECTION (par ordre de priorité) :\n"
    "1. FAITS D'ACTUALITÉ ET FAITS DIVERS : Arrestations, enquêtes, décisions de justice, événements récents.\n"
    "2. Affirmation factuelle précise et vérifiable (chiffres, statistiques, lois, faits historiques datés).\n"
    "3. Règles juridiques, fiscales ou comparaisons internationales (ex: 'Aux États-Unis, ils ont un impôt universel').\n"
    "4. Accusations politiques vérifiables ou historiques de votes (ex: 'Ils ont voté ensemble tel amendement').\n"
    "5. Présentation d'invité, titre, fonction politique ou parti (ex: 'président de Reconquête').\n"
    "6. Noms propres (livres, éditeurs, entreprises, lieux) potentiellement sujets à des erreurs de transcription.\n"
    "7. Sophisme, biais rhétorique ou généralisation abusive.\n\n"
    "EXCLUSIONS ABSOLUES (ne jamais sélectionner) :\n"
    "- Fragments de phrases sans sujet ni verbe principal.\n"
    "- Le bruit oral pur et les phrases noyées sous les bégaiements (ex: 'Moi vous savez euh je monsieur monsieur...'). Mieux vaut ne rien sélectionner que d'analyser du bruit.\n"
    "- Affirmations déjà analysées dans l'historique (vérifie l'historique avant de sélectionner).\n"
    "- Phrases qui sont clairement une partie incomplète d'un raisonnement plus long.\n"
    "RÈGLE FONDAMENTALE : Si aucune phrase ne respecte les critères, il est IMPÉRATIF de ne rien sélectionner.\n\n"
    "🛠️ CORRECTION INTELLIGENTE ET CONTEXTUALISATION (CRITIQUE) :\n"
    "1. ERREURS ASR : Corrige les erreurs phonétiques évidente (ex: 'le loup' -> 'le Louvre', 'ministre du lourd' -> 'ministre de la Culture').\n"
    "2. RÉSOLUTION DES PRONOMS (Désambiguïsation) : Une affirmation doit pouvoir être comprise TOUTE SEULE par un moteur de recherche. "
    "Si la phrase contient des pronoms ('il', 'ils') ou des références vagues ('ces deux hommes', 'ce fait divers'), "
    "REMPLACE-LES obligatoirement par le sujet précis dans 'affirmation_corrigee'. "
    "Exemple : 'il a fait passer cette loi' DOIT DEVENIR 'Le Président a fait passer cette loi' (en déduisant le sujet depuis le contexte récent).\n\n"
    "3. ATTRIBUTION : Si tu analyses des sous-titres sans noms de locuteurs (comme YouTube), utilise ta déduction pour comprendre si c'est le journaliste ou l'invité qui parle, pour ne pas attribuer une phrase au mauvais interlocuteur.\n\n"
    "RETOURNE UNIQUEMENT ce JSON (sans texte autour) :\n"
    "- Si une affirmation pertinente existe :\n"
    "  {\n"
    "    \"affirmation_brute\": \"citation exacte depuis le buffer (avec l'erreur)\",\n"
    "    \"affirmation_corrigee\": \"phrase nettoyée et corrigée phonétiquement\",\n"
    "    \"start\": <timestamp_float>\n"
    "  }\n"
    "- Si aucune affirmation pertinente :\n"
    "  {\n"
    "    \"affirmation_brute\": null\n"
    "  }\n\n"
    "Le champ 'start' doit être le timestamp (en secondes) de la phrase source dans le buffer."
)

# Prompt système pour le RADAR (mise à jour du sujet).
# Utilise la technique du "Résumé Roulant" pour garder la mémoire sans exploser les tokens.
TOPIC_UPDATE_SYSTEM_PROMPT = (
    "Tu es un superviseur de débat en temps réel.\n"
    "Ton objectif est de maintenir à jour le contexte de la discussion pour aider au fact-checking.\n"
    "On va te fournir :\n"
    "1. Le RÉSUMÉ PRÉCÉDENT de la discussion.\n"
    "2. Le SUJET PRINCIPAL et SOUS-SUJET actuels.\n"
    "3. La TRANSCRIPTION récente (dernières phrases échangées).\n\n"
    "TÂCHE :\n"
    "1. DÉCODE LES ERREURS ASR : La transcription est générée par une machine. Si tu vois des mots absurdes phonétiquement proches du contexte (ex: 'le loup' pour 'le Louvre', 'ministre du lourd' pour 'ministre de la Culture'), corrige-les mentalement.\n"
    "2. Lis la transcription récente. Si la discussion continue sur le même thème, affine simplement le résumé. "
    "Si la discussion a clairement changé de sujet (pas juste une parenthèse, mais un vrai changement de fond), "
    "mets à jour le sujet principal et le sous-sujet.\n\n"
    "⚠️ RÈGLE ABSOLUE SUR LE SUJET : Le Sujet Principal ne doit JAMAIS être le format de la vidéo (ex: 'Entretien', 'Face à face', 'Débat'). Il DOIT être la THÉMATIQUE DE FOND (ex: 'Économie', 'Fait divers', 'Immigration').\n\n"
    "RÉPONDS UNIQUEMENT AVEC CE FORMAT JSON :\n"
    "{\n"
    "  \"resume\": \"nouveau résumé très concis de la situation (1-2 phrases)\",\n"
    "  \"sujet_principal\": \"sujet de fond\",\n"
    "  \"sous_sujet\": \"angle spécifique actuel (ou null)\"\n"
    "}"
)

def _find_best_timestamp(affirmation: str, buf: List[Dict[str, Any]], fallback_ts: Optional[float]) -> float:
    """
    Trouve le timestamp de la phrase source dans le buffer par matching textuel.
    Utilisé comme solution de secours si l'IA oublie de retourner le timestamp exact.
    """
    if not buf:
        return fallback_ts or 0.0

    aff_lower = affirmation.lower()
    aff_words = set(aff_lower.split())

    best_score = 0
    best_ts = fallback_ts or 0.0

    for sentence in buf:
        s_text = sentence.get('text', '').lower()
        s_start = sentence.get('start')
        if s_start is None:
            continue

        if aff_lower in s_text or s_text in aff_lower:
            return float(s_start)

        s_words = set(s_text.split())
        common = len(aff_words & s_words)
        if common > best_score:
            best_score = common
            best_ts = float(s_start)

    return best_ts


# ==============================================================================
# BOUCLE D'ANALYSE EN ARRIÈRE-PLAN
# ==============================================================================

async def background_analyze_task(
    sentences: List[Dict[str, Any]],
    video_id: str,
    global_context: str,
    orchestrator: Any,
    result_dir: Path,
    safe_add_history: Callable[[Dict[str, Any]], None],
    safe_get_history: Callable[[], List[Dict[str, Any]]],
    safe_get_formatted_history: Callable[..., List[Dict[str, str]]]
):
    """
    Tâche asynchrone principale qui orchestre le flux audio/texte.
    
    - Reçoit toutes les phrases (sentences).
    - Initialise le contexte global (Phase 0).
    - Simule un flux continu en gérant des buffers temporels.
    """
    if not orchestrator:
        logger.error("Orchestrator not ready.")
        return

    results_list = []
    logger.info(f"[Analyse] Démarrage Live Streaming pour {len(sentences)} phrases (buffer {WINDOW_SIZE_SECONDS}s).")

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = result_dir / f"web_youtube_{video_id}_{timestamp_str}.json"

    # --- Phase 0 : Initialisation du sujet à partir du titre ---
    main_topic = None
    sub_topic = None
    if global_context:
        try:
            topic_result = await orchestrator.extract_topic(global_context=global_context)
            main_topic = topic_result.get("main_topic")
            sub_topic = topic_result.get("sub_topic")
            logger.info(f"[Phase 0] Sujet extrait : main_topic={main_topic!r}, sub_topic={sub_topic!r}")
            
            # Injection initiale du sujet pour l'interface
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

    # --- Injection des transcriptions brutes pour le frontend ---
    logger.info(f"[Transcription] Injection immédiate de {len(sentences)} phrases dans l'historique.")
    for sentence in sentences:
        ts = sentence.get('start')
        text = sentence.get('text', '').strip()
        if not text:
            continue
        transcription_item = {
            "timestamp": datetime.now().isoformat(),
            "affirmation": text,
            "result": None,
            "video_timestamp": float(ts) if ts is not None else 0.0,
            "type": "transcription"
        }
        safe_add_history(transcription_item)
    logger.info("[Transcription] Toutes les phrases injectées.")

    # =========================================================================
    # VARIABLES D'ÉTAT : RÉSUMÉ ROULANT (State Tracker)
    # =========================================================================
    current_main_topic = main_topic
    current_sub_topic = sub_topic
    current_summary = "Le débat commence. Présentation initiale."
    
    topic_buffer: List[Dict[str, Any]] = []
    last_topic_update_ts: Optional[float] = None

    async def update_rolling_topic(text_to_analyze: str, current_ts: float) -> None:
        """
        Le 'Radar' : Analyse la fenêtre de texte récente pour détecter un changement
        de sujet ou mettre à jour le résumé de l'état du débat.
        Partage le 'last_groq_call_time' avec l'Analyseur pour éviter les Rate Limits.
        """
        nonlocal current_main_topic, current_sub_topic, current_summary, last_groq_call_time

        now = asyncio.get_event_loop().time()
        elapsed_since_last = now - last_groq_call_time
        if elapsed_since_last < MIN_GROQ_CALL_INTERVAL:
            wait_needed = MIN_GROQ_CALL_INTERVAL - elapsed_since_last
            logger.debug(f"[Radar] Anti-burst : attente {wait_needed:.2f}s avant prochain appel.")
            await asyncio.sleep(wait_needed)

        user_content = (
            f"RÉSUMÉ PRÉCÉDENT : {current_summary}\n"
            f"SUJET ACTUEL : {current_main_topic} (Sous-sujet: {current_sub_topic})\n"
            f"TRANSCRIPTION (récente) :\n{text_to_analyze}"
        )
        
        try:
            groq_messages = [
                {"role": "system", "content": TOPIC_UPDATE_SYSTEM_PROMPT},
                {"role": "user", "content": user_content}
            ]
            from src.core.providers.groq_provider import GROQ_DEFAULT_MODEL
            raw_response = await orchestrator.classification_provider.complete_chat_async(
                messages=groq_messages,
                model=GROQ_DEFAULT_MODEL,
                temperature=0.0
            )
            last_groq_call_time = asyncio.get_event_loop().time()
            
            parsed = orchestrator._parse_llm_json(raw_response)
            if isinstance(parsed, dict):
                new_main = parsed.get("sujet_principal") or current_main_topic
                new_sub = parsed.get("sous_sujet")
                new_sum = parsed.get("resume") or current_summary
                
                changed = (new_main != current_main_topic) or (new_sub != current_sub_topic)
                
                current_main_topic = new_main
                current_sub_topic = new_sub
                current_summary = new_sum
                
                logger.info(f"[Radar] Sujet mis à jour : {current_main_topic} / {current_sub_topic}")
                
                # Notification au frontend que le sujet a changé
                if changed:
                    topic_event = {
                        "timestamp": datetime.now().isoformat(),
                        "type": "topic_update",
                        "main_topic": current_main_topic,
                        "sub_topic": current_sub_topic,
                        "video_timestamp": current_ts
                    }
                    safe_add_history(topic_event)
                    
        except Exception as e:
            last_groq_call_time = asyncio.get_event_loop().time()
            logger.warning(f"[Radar] Échec mise à jour sujet (non bloquant) : {e}")

    # =========================================================================
    # VARIABLES D'ÉTAT : MOTEUR D'ANALYSE (Fact-Checker)
    # =========================================================================
    buffer: List[Dict[str, Any]] = []
    buffer_start_ts: Optional[float] = None
    last_groq_call_time: float = 0.0

    async def flush_buffer(buf: List[Dict[str, Any]], buf_start_ts: Optional[float]) -> None:
        """
        Le 'Fact-Checker' : Sélectionne la meilleure phrase du buffer de 15s,
        la corrige, et l'envoie à Mistral pour le fact-checking complet.
        """
        nonlocal last_groq_call_time

        if not buf:
            return

        buffer_lines = []
        for s in buf:
            if len(s.get('text', '')) >= 3:
                # Récupère le speaker s'il existe et n'est pas "null"
                spk_val = s.get('speaker')
                has_spk = bool(spk_val) and str(spk_val).lower() not in ["none", "null"]
                speaker_prefix = f"[{spk_val}] " if has_spk else ""
                buffer_lines.append(f"[{s.get('start', 0):.2f}s] {speaker_prefix}{s['text']}")
        buffer_text = "\n".join(buffer_lines)

        if not buffer_text.strip():
            return

        logger.info(f"[Buffer] Flush — ts_début={buf_start_ts:.1f}s — {len(buf)} phrases")

        now = asyncio.get_event_loop().time()
        elapsed_since_last = now - last_groq_call_time
        if elapsed_since_last < MIN_GROQ_CALL_INTERVAL:
            wait_needed = MIN_GROQ_CALL_INTERVAL - elapsed_since_last
            logger.debug(f"[Groq] Anti-burst : attente {wait_needed:.2f}s avant prochain appel.")
            await asyncio.sleep(wait_needed)

        # --- Construction de la mémoire anti-doublon ---
        history_snapshot = safe_get_history()
        already_analyzed = [
            item.get("affirmation", "")
            for item in history_snapshot
            if item.get("type") == "analyse"
        ]
        history_summary = ""
        if already_analyzed:
            history_summary = "AFFIRMATIONS DÉJÀ ANALYSÉES (ne pas re-sélectionner) :\n"
            history_summary += "\n".join(f"- {a}" for a in already_analyzed[-20:])
            history_summary += "\n\n"

        selected_affirmation: Optional[str] = None
        selected_ts: float = buf_start_ts or 0.0

        # --- Phase de SÉLECTION (Groq) ---
        try:
            groq_messages = [
                {"role": "system", "content": WINDOW_SELECTION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"CONTEXTE ACTUEL:\n"
                        f"- Sujet: {current_main_topic}\n"
                        f"- Sous-sujet: {current_sub_topic}\n"
                        f"- Résumé récent: {current_summary}\n\n"
                        f"{history_summary}"
                        f"BUFFER ACTUEL (15 dernières secondes) :\n{buffer_text}"
                    )
                }
            ]
            from src.core.providers.groq_provider import GROQ_DEFAULT_MODEL
            raw_groq = await orchestrator.classification_provider.complete_chat_async(
                messages=groq_messages,
                model=GROQ_DEFAULT_MODEL,
                temperature=0.0
            )
            last_groq_call_time = asyncio.get_event_loop().time()

            parsed = orchestrator._parse_llm_json(raw_groq)
            if isinstance(parsed, dict):
                # Gestion de la phrase corrigée vs la phrase brute (pour retrouver le timestamp)
                raw_aff = parsed.get("affirmation_brute")
                corr_aff = parsed.get("affirmation_corrigee")
                old_aff = parsed.get("affirmation") # Fallback au cas où il utilise l'ancien format
                
                if corr_aff and corr_aff.strip():
                    selected_affirmation = corr_aff.strip()
                    search_aff = raw_aff.strip() if raw_aff else selected_affirmation
                elif old_aff and old_aff.strip():
                    selected_affirmation = old_aff.strip()
                    search_aff = selected_affirmation
                else:
                    selected_affirmation = None
                    search_aff = None

                if selected_affirmation:
                    groq_ts = parsed.get("start")
                    if groq_ts is not None:
                        try:
                            selected_ts = float(groq_ts)
                        except (ValueError, TypeError):
                            selected_ts = buf_start_ts or 0.0
                    else:
                        selected_ts = _find_best_timestamp(search_aff, buf, buf_start_ts)

                    logger.info(f"[Groq] Affirmation sélectionnée à {selected_ts:.2f}s : '{selected_affirmation[:60]}...'")
                else:
                    logger.info("[Groq] Aucune affirmation pertinente dans ce buffer.")
                    return
            else:
                logger.info("[Groq] Aucune affirmation pertinente dans ce buffer.")
                return

        except Exception as e:
            last_groq_call_time = asyncio.get_event_loop().time()
            logger.warning(f"[Groq] Échec sélection (non bloquant) : {e}. Buffer ignoré.")
            return

        if not selected_affirmation or len(selected_affirmation.strip()) < 10:
            logger.info("[Groq] Affirmation trop courte ou vide. Buffer ignoré.")
            return

        # --- Phase d'ANALYSE (Mistral) ---
        try:
            hist = safe_get_formatted_history(limit=1000)
            hist = [msg for msg in hist if msg is not None]

            window_text_plain = " ".join(s['text'] for s in buf if len(s.get('text', '')) >= 3)
            
            previous_context_str = f"RÉSUMÉ DU DÉBAT JUSQU'ICI : {current_summary}"
            if window_text_plain != selected_affirmation:
                previous_context_str += f"\n\nDERNIÈRES PHRASES PRONONCÉES : {window_text_plain}"

            current_result = await orchestrator.analyze(
                affirmation=selected_affirmation,
                history=hist,
                global_context=global_context,
                future_context=None,
                previous_context=previous_context_str,
                main_topic=current_main_topic,
                sub_topic=current_sub_topic
            )

            if current_result is None:
                logger.error(f"[Mistral] orchestrator.analyze() a retourné None pour '{selected_affirmation[:40]}'. Ignoré.")
                return

            processed_result = {
                "timestamp": datetime.now().isoformat(),
                "affirmation": format_affirmation(selected_affirmation),
                "result": current_result,
                "video_timestamp": selected_ts,
                "main_topic": current_main_topic,
                "sub_topic": current_sub_topic,
                "type": "analyse"
            }

            safe_add_history(processed_result)
            results_list.append(processed_result)

            try:
                with open(output_filename, 'w', encoding='utf-8') as f:
                    json.dump(results_list, f, indent=2, ensure_ascii=False)
            except Exception as save_err:
                logger.error(f"[Sauvegarde] Erreur incrémentale : {save_err}")

        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate_limit" in err_str.lower() or "rate limit" in err_str.lower():
                logger.warning(f"[429] Rate limit pour '{selected_affirmation[:40]}', passage au suivant.")
                return
            logger.error(f"[Pipeline] Erreur analyse : {e}")

    # =========================================================================
    # BOUCLE PRINCIPALE DE LECTURE DU FLUX
    # =========================================================================
    for sentence in sentences:
        ts = sentence.get('start')
        text = sentence.get('text', '').strip()

        if not text:
            continue

        topic_buffer.append(sentence)

        if ts is not None:
            ts = float(ts)
            if buffer_start_ts is None:
                buffer_start_ts = ts
            if last_topic_update_ts is None:
                last_topic_update_ts = ts

            # --- 1. Déclenchement du Moteur Radar (Contexte) ---
            # Intervalle court (10s) au début pour vite capter le sujet, puis croisière (60s)
            current_radar_interval = 10.0 if ts <= 120.0 else 60.0
            if ts - last_topic_update_ts >= current_radar_interval:
                topic_lines = []
                for topic_sent in topic_buffer:
                    if len(topic_sent.get('text', '')) >= 3:
                        spk_val = topic_sent.get('speaker')
                        has_spk = bool(spk_val) and str(spk_val).lower() not in ["none", "null"]
                        spk_prefix = f"[{spk_val}] " if has_spk else ""
                        topic_lines.append(f"[{topic_sent.get('start', 0):.2f}s] {spk_prefix}{topic_sent['text']}")
                topic_text = "\n".join(topic_lines)
                if topic_text.strip():
                    await update_rolling_topic(topic_text, ts)
                topic_buffer = []
                last_topic_update_ts = ts

            # --- 2. Déclenchement du Moteur d'Analyse (Fact-Checking) ---
            if ts - buffer_start_ts >= WINDOW_SIZE_SECONDS:
                await flush_buffer(list(buffer), buffer_start_ts)
                buffer = [sentence]
                buffer_start_ts = ts
            else:
                buffer.append(sentence)
        else:
            buffer.append(sentence)

    if buffer:
        logger.info(f"[Buffer] Flush final — {len(buffer)} phrase(s) restante(s).")
        await flush_buffer(buffer, buffer_start_ts)

    logger.info(f"[Analyse] Terminée. Résultats sauvegardés dans {output_filename}")