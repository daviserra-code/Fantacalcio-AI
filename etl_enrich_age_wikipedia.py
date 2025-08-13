# etl_enrich_age_wikipedia.py
# -*- coding: utf-8 -*-
import os, re, json, time, argparse, logging
from typing import Optional, Tuple, Dict, Any, List

import requests

LOG = logging.getLogger("etl_enrich_age_wikipedia")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

WIKI_SEARCH_URL = "https://{lang}.wikipedia.org/w/api.php"
HEADERS = {
    "User-Agent": "FantacalcioAssistant/1.0 (+github.com/your-org)"
}

IT_MONTHS = ("gennaio","febbraio","marzo","aprile","maggio","giugno",
             "luglio","agosto","settembre","ottobre","novembre","dicembre")

RE_PATTERNS = [
    re.compile(r"nato(?:\s+a\s+[A-Za-zÀ-ÿ\s]+)?\s*(?:il\s*)?\d{1,2}\s+(%s)\s+(19|20)\d{2}" % "|".join(IT_MONTHS), re.I),
    re.compile(r"nato\s+nel\s+(19|20)\d{2}", re.I),
    re.compile(r"classe\s+(?:'|’)?0?(\d{2}|\d{4})", re.I),
    re.compile(r"born\s+(?:on\s+)?[A-Za-z]+\s+\d{1,2},\s+(19|20)\d{2}", re.I),
    re.compile(r"born\s+\d{1,2}\s+[A-Za-z]+\s+(19|20)\d{2}", re.I),
    re.compile(r"\((?:born\s+)?\d{1,2}\s+[A-Za-z]+\s+(19|20)\d{2}\)", re.I),
    re.compile(r"\(\d{1,2}\s+(%s)\s+(19|20)\d{2}\)" % "|".join(IT_MONTHS), re.I),
    re.compile(r"\b(19|20)\d{2}\b")  # fallback, filtrato dopo
]

def safe_int(x: Any) -> Optional[int]:
    try: return int(x)
    except: return None

def two_to_year(s: str) -> Optional[int]:
    s = s.strip("’'")
    y = safe_int(s)
    if y is None: return None
    if y < 100: y += 2000
    return y

def extract_year(text: str) -> Optional[int]:
    """Heuristica: privilegia pattern espliciti, poi fallback generico."""
    if not text: return None
    t = text.replace("–","-")
    # rimuovi pattern stagione “2025-26” che confondono
    t = re.sub(r"\b(20\d{2})\s*[-/]\s*\d{2}\b", r"", t)
    # prova pattern in ordine
    for rx in RE_PATTERNS[:-1]:
        m = rx.search(t)
        if not m: continue
        groups = [g for g in m.groups() if g]
        # ultimo gruppo è spesso l'anno
        if not groups: continue
        last = groups[-1]
        if isinstance(last, tuple): last = last[-1]
        year = None
        # caso “classe ’03”
        if rx.pattern.startswith("classe"):
            year = two_to_year(last)
        else:
            year = safe_int(last) or two_to_year(last)
        if year and 1980 <= year <= 2025:
            return year

    # fallback: primo anno plausibile vicino a “nato/born”
    m = RE_PATTERNS[-1].finditer(t)
    near_hits = []
    for mm in m:
        y = safe_int(mm.group(0))
        if not y or not (1980 <= y <= 2025): continue
        # controlla contesto
        start = max(0, mm.start()-80)
        ctx = t[start:mm.end()+10].lower()
        if ("nato" in ctx) or ("born" in ctx) or ("classe" in ctx):
            near_hits.append(y)
    if near_hits:
        return near_hits[0]
    return None

def wiki_search(name: str, team: str, lang: str="it", session: Optional[requests.Session]=None) -> Optional[int]:
    """Cerca pagina e prova a estrarre anno di nascita."""
    S = session or requests.Session()
    q = f"{name} calciatore {team}".strip()
    params = {
        "action":"query","list":"search","srsearch": q, "srlimit":5,
        "format":"json","origin":"*"
    }
    try:
        r = S.get(WIKI_SEARCH_URL.format(lang=lang), params=params, headers=HEADERS, timeout=15)
        if r.status_code == 429:
            time.sleep(1.5)
            r = S.get(WIKI_SEARCH_URL.format(lang=lang), params=params, headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        LOG.warning("[WIKI] search fail %s: %s", lang, e); return None

    hits = data.get("query",{}).get("search",[]) or []
    if not hits:
        # prova senza team
        params["srsearch"] = f"{name} calciatore".strip()
        try:
            r = S.get(WIKI_SEARCH_URL.format(lang=lang), params=params, headers=HEADERS, timeout=15)
            r.raise_for_status()
            data = r.json()
            hits = data.get("query",{}).get("search",[]) or []
        except: hits = []

    if not hits:
        return None

    # prendi la pagina più promettente e scarica estratto
    pageid = hits[0].get("pageid")
    if not pageid: return None

    params2 = {
        "action":"query","prop":"extracts","explaintext":1,"pageids":pageid,"format":"json","origin":"*"
    }
    try:
        r2 = S.get(WIKI_SEARCH_URL.format(lang=lang), params=params2, headers=HEADERS, timeout=15)
        if r2.status_code == 429:
            time.sleep(1.5)
            r2 = S.get(WIKI_SEARCH_URL.format(lang=lang), params=params2, headers=HEADERS, timeout=15)
        r2.raise_for_status()
        d2 = r2.json()
        pages = d2.get("query",{}).get("pages",{}) or {}
        page = pages.get(str(pageid)) or {}
        text = page.get("extract","")
        return extract_year(text)
    except Exception as e:
        LOG.warning("[WIKI] extract fail %s: %s", lang, e)
        return None

def resolve_birth_year(name: str, team: str, session: requests.Session) -> Optional[int]:
    # IT first, then EN
    y = wiki_search(name, team, "it", session=session)
    if y: return y
    return wiki_search(name, team, "en", session=session)

def load_age_cache(path: str) -> Dict[str, Any]:
    if os.path.exists(path):
        try:
            return json.load(open(path,"r",encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_age_cache(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    json.dump(data, open(path,"w",encoding="utf-8"), ensure_ascii=False, indent=2)

def key_for(name: str, team: str) -> str:
    return f"{name.strip().lower()}|{team.strip().lower()}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="./season_roster.json", help="roster di partenza")
    ap.add_argument("--out", default="./cache/age_index.json", help="output cache età")
    ap.add_argument("--limit", type=int, default=400, help="limite giocatori da processare")
    ap.add_argument("--sleep", type=float, default=0.6, help="sleep tra richieste")
    ap.add_argument("--force", action="store_true", help="ricalcola anche se già in cache")
    args = ap.parse_args()

    try:
        roster = json.load(open(args.input,"r",encoding="utf-8"))
        if not isinstance(roster, list):
            LOG.error("Roster non è una lista"); return
    except Exception as e:
        LOG.error("Errore apertura roster: %s", e); return

    cache = load_age_cache(args.out)
    S = requests.Session()

    processed = 0
    hits = 0
    for item in roster:
        if processed >= args.limit: break
        if not isinstance(item, dict): continue
        name = (item.get("name") or item.get("player") or "").strip()
        team = (item.get("team") or item.get("club") or "").strip()
        if not name: continue

        # se già ho birth_year nel roster, salvalo in cache e salta
        by = item.get("birth_year") or item.get("year_of_birth")
        if by:
            k = key_for(name, team)
            cache.setdefault(k, {})["birth_year"] = int(by)
            continue

        k = key_for(name, team)
        if not args.force and k in cache and cache[k].get("birth_year"):
            continue

        processed += 1
        y = resolve_birth_year(name, team, session=S)
        if y:
            hits += 1
            cache.setdefault(k, {})["birth_year"] = int(y)
            LOG.info("[AGE] %s (%s) -> %s", name, team, y)
        else:
            LOG.info("[AGE] %s (%s) -> nd", name, team)

        save_age_cache(args.out, cache)
        time.sleep(args.sleep)

    LOG.info("Fatto. Processati=%d, trovati=%d. Cache: %s", processed, hits, args.out)

if __name__ == "__main__":
    main()
