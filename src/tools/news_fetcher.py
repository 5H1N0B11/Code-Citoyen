import logging
import re
import asyncio
import json
import ast
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from ddgs import DDGS
from src.core.providers import get_provider
from src.utils import TourDeControle

logger = logging.getLogger(__name__)

def _fetch_ddgs_sync(query: str, max_results: int) -> str:
    """Récupère le texte brut de DuckDuckGo de manière synchrone."""
    raw_text = ""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            if not results:
                return ""
            for r in results:
                raw_text += f"Titre: {r.get('title', '')}\nExtrait: {r.get('body', '')}\n\n"
    except Exception as e:
        logger.warning(f"[Contexte Actu] Erreur DDGS : {e}")
    return raw_text

def _fetch_google_news_sync(query: str, start_date: str, end_date: str, max_results: int = 30) -> str:
    """Récupère l'actualité via Google News RSS avec les filtres de date stricts natifs."""
    try:
        # Utilisation des opérateurs de date Google (after: et before:)
        full_query = f"{query} after:{start_date} before:{end_date}"
        encoded_query = urllib.parse.quote(full_query)
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=fr&gl=FR&ceid=FR:fr"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
            
        root = ET.fromstring(xml_data)
        items = root.findall('.//item')
        
        raw_text = ""
        for item in items[:max_results]:
            title = item.find('title').text if item.find('title') is not None else ''
            pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ''
            raw_text += f"Date de publication: {pub_date}\nTitre: {title}\n\n"
            
        return raw_text
    except Exception as e:
        logger.warning(f"[Google News] Erreur RSS : {e}")
        return ""

async def fetch_context_news(date_or_text: str, specific_subject: str = None, max_results: int = 25) -> str:
    """
    Recherche les actualités majeures exactes pour les 7 jours précédant la vidéo.
    """
    # Tentative d'extraction d'une date (ex: YYYY-MM-DD). 
    # Suppression du \b final qui cassait l'extraction à cause du 'T' dans les dates ISO (ex: 2026-02-17T23:54)
    match_date = re.search(r'(20\d{2})(?:[-/](0[1-9]|1[0-2])(?:[-/]([0-3]\d))?)?', date_or_text)
    
    query_general = "actualités France AFP"
    year = str(datetime.now().year)
    mois_fr = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
    date_limit = None
    past_limit = None
    has_exact_day = False
    
    if match_date:
        year = match_date.group(1)
        y = int(year)
        month = match_date.group(2)
        if month:
            m = int(month)
            month_str = mois_fr[int(month) - 1]
            day = match_date.group(3)
            if day:
                d = int(day)
                try:
                    date_limit = datetime(y, m, d).date()
                    has_exact_day = True
                    # On recule à 15 jours pour avoir tout le contexte des affaires
                    past_limit = date_limit - timedelta(days=15)
                except ValueError:
                    date_limit = datetime(y, m, 28).date() # Fallback sécurisé
                    past_limit = datetime(y, m, 1).date()
            else:
                d = 28 if m == 2 else (30 if m in [4, 6, 9, 11] else 31)
                date_limit = datetime(y, m, d).date()
                past_limit = datetime(y, m, 1).date()
        else:
            date_limit = datetime(y, 12, 31).date()
            past_limit = datetime(y, 1, 1).date()
    else:
        date_limit = datetime.now().date()
        past_limit = date_limit - timedelta(days=15)

    logger.info(f"[Contexte Actu] Date limite stricte reconnue : {date_limit}")
    
    # 1. Récupération propre via Google News RSS (qui respecte nativement les dates)
    start_date_str = past_limit.strftime("%Y-%m-%d")
    end_date_str = (date_limit + timedelta(days=1)).strftime("%Y-%m-%d") # +1 jour car before: est exclusif
    
    logger.info(f"[Contexte Actu] Recherche Google News de {start_date_str} à {end_date_str}")
    raw_news = await asyncio.to_thread(
        _fetch_google_news_sync, 
        "France", 
        start_date_str, 
        end_date_str, 
        30
    )
    
    # 1.5 Recherche CIBLÉE sur les noms des invités (spécifique au direct)
    if specific_subject:
        clean_subject = re.sub(r'[^\w\s-]', '', specific_subject).strip()
        if clean_subject:
            if match_date and match_date.group(2):
                month_str = mois_fr[int(match_date.group(2)) - 1]
                query_specific = f'{clean_subject} actualité {month_str} {year}'.strip()
            else:
                query_specific = f'{clean_subject} actualité {year}'
            logger.info(f"[Contexte Actu] Recherche ciblée sur le sujet/invité : '{query_specific}'")
            raw_news += "\n" + await asyncio.to_thread(_fetch_ddgs_sync, query_specific, 10)

    if not raw_news.strip():
        return "Aucune actualité historique trouvée pour cette période."

    # 2. Nettoyage, Résumé et Scoring par l'IA (Groq)
    try:
        route = TourDeControle.get("resume_actus")
        provider = get_provider(route["provider"])
        await provider.initialize()
        
        if has_exact_day:
            time_rule = f"1. FENÊTRE TEMPORELLE STRICTE : Ne conserve QUE les événements survenus entre le {past_limit.strftime('%Y-%m-%d')} et le {date_limit.strftime('%Y-%m-%d')}. IGNORE INTÉGRALEMENT tout événement hors de cette période (15 jours).\n"
        else:
            time_rule = f"1. FENÊTRE TEMPORELLE : Ne conserve QUE les événements survenus entre le {past_limit.strftime('%Y-%m-%d')} et le {date_limit.strftime('%Y-%m-%d')}.\n"

        prompt = (
            "Tu es un journaliste d'agence de presse (type AFP), neutre et factuel.\n"
            "TA MISSION : Extraire TOUS les événements factuels pertinents (politique, faits divers, justice, crises, économie) de ce texte brut. Sois exhaustif et extrais un maximum d'informations distinctes.\n"
            "RÈGLES ABSOLUES :\n"
            + time_rule +
            "2. IGNORE TOTALEMENT les titres génériques ou les index de sites (ex: 'La matinale du...', 'Actualité du jour', 'Page 2'). Ne garde QUE des événements factuels précis et identifiables.\n"
            "3. IGNORE TOTALEMENT le gossip et la télé-réalité. CONSERVE toute l'actualité de Une : politique nationale, crises sociales, économie, et les faits divers judiciaires majeurs.\n"
            "4. ÉCHELLE D'IMPORTANCE (1 à 10) : 10 = Événement faisant la Une nationale (homicide, drame, affaire judiciaire, élection). 8 = Politique nationale, fait divers très médiatisé. 5 = Actualité courante. 2 = Anecdote.\n"
            "5. La date DOIT être au format strict YYYY-MM-DD (ex: 2026-02-14). Si le jour exact est inconnu, mets le premier du mois (ex: 2026-02-01).\n"
            "6. Tu DOIS répondre UNIQUEMENT avec un tableau JSON valide. Pas de texte avant ni après.\n\n"
            "FORMAT JSON EXIGÉ :\n"
            "[\n"
            "  {\n"
            "    \"date\": \"YYYY-MM-DD\",\n"
            "    \"importance\": 8,\n"
            "    \"titre\": \"Titre court\",\n"
            "    \"resume\": \"1 à 2 phrases max factuelles\"\n"
            "  }\n"
            "]\n\n"
            f"RÉSULTATS BRUTS À NETTOYER :\n{raw_news}"
        )
        
        raw_response = await provider.complete_chat_async(
            messages=[{"role": "user", "content": prompt}],
            model=route["model"],
            temperature=0.0
        )
        
        # Extraction robuste du tableau JSON (ignore le texte bavard avant/après)
        start_idx = raw_response.find('[')
        end_idx = raw_response.rfind(']')
        if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
            clean_json = raw_response[start_idx:end_idx+1]
        else:
            clean_json = raw_response
        
        try:
            news_items = json.loads(clean_json)
        except json.JSONDecodeError:
            news_items = ast.literal_eval(clean_json)
            
        if not isinstance(news_items, list):
            raise ValueError("Le résultat n'est pas une liste JSON valide.")
            
        valid_news = []
        
        for item in news_items:
            if not isinstance(item, dict): continue
            item_date_str = str(item.get("date", ""))
            keep = True
            
            # LE FILTRE PROGRAMMATIQUE MATHÉMATIQUE (AVEC MARGE DE TOLÉRANCE)
            date_match = re.search(r'(\d{4})[-/.](\d{2})[-/.](\d{2})', item_date_str)
            if date_match:
                try:
                    y, m, d = map(int, date_match.groups())
                    item_date = datetime(y, m, d).date()
                    
                    if has_exact_day:
                        # On tolère +2 jours car une émission à 23h génère des articles le lendemain
                        margin_limit = date_limit + timedelta(days=2)
                        past_filter_limit = past_limit - timedelta(days=1)
                    else:
                        margin_limit = date_limit
                        past_filter_limit = past_limit
                    
                    if item_date > margin_limit:
                        logger.info(f"[Filtre Temporel] CENSURE (Événement Futur) : {item.get('titre')} ({item_date}) > {margin_limit}")
                        keep = False
                    elif item_date < past_filter_limit:
                        logger.info(f"[Filtre Temporel] CENSURE (Trop Ancien) : {item.get('titre')} ({item_date}) < {past_filter_limit}")
                        keep = False
                except ValueError:
                    logger.warning(f"[Filtre Temporel] Date invalide censurée : {item_date_str}")
                    keep = False
            else:
                # Guillotine absolue : Format non conforme
                logger.warning(f"[Filtre Temporel] Format date non conforme (CENSURÉ) : {item_date_str}")
                keep = False

            # Filtrage du gossip (importance < 4)
            try:
                importance = int(item.get("importance", 0))
            except (ValueError, TypeError):
                importance = 0
                
            if keep and importance >= 2:
                valid_news.append(item)
                
        if not valid_news:
            return "Aucun événement factuel majeur trouvé dans la période autorisée avant la vidéo."
            
        # Tri par importance décroissante
        valid_news.sort(key=lambda x: int(x.get("importance", 0)), reverse=True)
        
        # ÉCONOMIE DE TOKENS MISTRAL : On limite au TOP 12
        valid_news = valid_news[:12]
        
        # Reformatage en texte clair
        final_output = ""
        for item in valid_news:
            final_output += f"- [{item.get('date')}] (Importance: {item.get('importance')}/10) {item.get('titre')} : {item.get('resume')}\n"
            
        return final_output.strip()
        
    except (json.JSONDecodeError, SyntaxError, ValueError) as e:
        logger.error(f"[Contexte Actu] Erreur parsing JSON Groq: {e}\nRaw: {raw_response}")
        return "Impossible de formater les actualités (Erreur JSON)."
    except Exception as e:
        logger.error(f"[Contexte Actu] Erreur lors du nettoyage par IA : {e}")
        return "Impossible de résumer les actualités."