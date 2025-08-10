# live_sources.py
# Fallback web live: Wikipedia + Wikidata per "club attuale" di un calciatore
import re
import time
import json
import os
from typing import Optional, Dict
import requests

USER_AGENT = os.environ.get("USER_AGENT", "FantacalcioBot/1.0 (replit)")
CACHE_PATH = "./.cache/live_sources_cache.json"
os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)

def _load_cache():
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_cache(data):
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

_CACHE = _load_cache()

def _get(url: str, params: dict | None = None, lang: str = "it", timeout: float = 6.0):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if lang:
        # usa host localizzato per wikipedia
        if "wikipedia.org" in url and not url.startswith(("http://", "https://")):
            url = f"https://{lang}.wikipedia.org{url}"
    r = requests.get(url, params=params, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r

def fetch_wikipedia_summary(name: str, lang: str = "it") -> Optional[Dict]:
    """
    Usa Wikipedia REST summary per ottenere descrizione e titolo normalizzato.
    """
    key = f"wp:{lang}:{name.lower()}"
    if key in _CACHE:
        return _CACHE[key]
    try:
        # /page/summary fa anche redirect verso la pagina corretta
        r = _get(f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{name}")
        data = r.json()
        # struttura attesa: {title, description, extract, content_urls: {desktop:{page}}}
        if "title" in data and "extract" in data:
            _CACHE[key] = data
            _save_cache(_CACHE)
            return data
    except Exception:
        return None
    return None

def fetch_wikidata_id_from_page(title: str, lang: str = "it") -> Optional[str]:
    """
    Dalla pagina Wikipedia prendi l'item Wikidata (via action=query&prop=pageprops).
    """
    key = f"wdid:{lang}:{title}"
    if key in _CACHE:
        return _CACHE[key]
    try:
        r = _get(f"https://{lang}.wikipedia.org/w/api.php", params={
            "action": "query",
            "prop": "pageprops",
            "titles": title,
            "format": "json"
        }, lang=lang)
        q = r.json()
        pages = q.get("query", {}).get("pages", {})
        for _, v in pages.items():
            wdid = v.get("pageprops", {}).get("wikibase_item")
            if wdid:
                _CACHE[key] = wdid
                _save_cache(_CACHE)
                return wdid
    except Exception:
        return None
    return None

def fetch_current_club_from_wikidata(wdid: str, lang: str = "it") -> Optional[str]:
    """
    Prova a leggere il club attuale.
    Metodo semplice: proprietà P54 (member of sports team) con qualifier 'end time' mancante.
    """
    key = f"wdclub:{wdid}"
    if key in _CACHE:
        return _CACHE[key]
    try:
        r = requests.get(
            f"https://www.wikidata.org/wiki/Special:EntityData/{wdid}.json",
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=8.0
        )
        r.raise_for_status()
        data = r.json()
        ent = data.get("entities", {}).get(wdid, {})
        claims = ent.get("claims", {})
        p54 = claims.get("P54", [])
        # prendi le membership senza P582 (end time)
        for cl in p54:
            mainsnak = cl.get("mainsnak", {})
            if mainsnak.get("snaktype") != "value":
                continue
            quals = cl.get("qualifiers", {})
            # se NON c'è end time (P582), assumiamo che sia attuale
            if "P582" in quals:
                continue
            val = mainsnak.get("datavalue", {}).get("value", {})
            club_id = val.get("id")
            if club_id:
                # risolvi etichetta in lingua
                club_label = resolve_wikidata_label(club_id, lang=lang)
                if club_label:
                    _CACHE[key] = club_label
                    _save_cache(_CACHE)
                    return club_label
        return None
    except Exception:
        return None

def resolve_wikidata_label(wdid: str, lang: str = "it") -> Optional[str]:
    k = f"wdlabel:{lang}:{wdid}"
    if k in _CACHE:
        return _CACHE[k]
    try:
        r = requests.get(
            f"https://www.wikidata.org/wiki/Special:EntityData/{wdid}.json",
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=6.0
        )
        r.raise_for_status()
        data = r.json()
        ent = data.get("entities", {}).get(wdid, {})
        lbl = ent.get("labels", {}).get(lang, {}).get("value")
        if not lbl:
            lbl = ent.get("labels", {}).get("en", {}).get("value")
        if lbl:
            _CACHE[k] = lbl
            _save_cache(_CACHE)
            return lbl
    except Exception:
        return None
    return None

def extract_team_from_summary_text(extract: str) -> Optional[str]:
    """
    Heuristica: prova a estrarre '... e' un calciatore ... che gioca nel/nel/la <TEAM> ...'
    Funziona bene per Wikipedia IT.
    """
    if not extract:
        return None
    patterns = [
        r"gioca (?:nel|nella|nei|nelle) ([A-Z][\w .'\-]+)",
        r"milita (?:nel|nella|nei|nelle) ([A-Z][\w .'\-]+)",
        r"centrocampista (?:del|della|dei|delle) ([A-Z][\w .'\-]+)",
        r"portiere (?:del|della|dei|delle) ([A-Z][\w .'\-]+)",
        r"attaccante (?:del|della|dei|delle) ([A-Z][\w .'\-]+)",
    ]
    for pat in patterns:
        m = re.search(pat, extract, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None

def fetch_player_current_team(player_name: str, lang: str = "it") -> Optional[Dict]:
    """
    Ritorna dict: {team, source_title, source_url, date} oppure None.
    """
    # 1) summary wikipedia
    summary = fetch_wikipedia_summary(player_name, lang=lang)
    team = None
    url = None
    title = None
    if summary:
        url = summary.get("content_urls", {}).get("desktop", {}).get("page")
        title = summary.get("title")
        team = extract_team_from_summary_text(summary.get("extract", "") or "")
        if team:
            return {"team": team, "source_title": title or player_name, "source_url": url, "date": time.strftime("%Y-%m-%d")}
        # 2) wikidata fallback
        wdid = fetch_wikidata_id_from_page(summary.get("title") or player_name, lang=lang)
        if wdid:
            club = fetch_current_club_from_wikidata(wdid, lang=lang)
            if club:
                return {"team": club, "source_title": title or player_name, "source_url": url or f"https://www.wikidata.org/wiki/{wdid}", "date": time.strftime("%Y-%m-%d")}
    return None