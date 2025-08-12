#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
etl_web_transfermarkt.py — robusto (Transfermarkt HTML first, Wikipedia fallback)

Uso tipico (Transfermarkt HTML, consigliato):
  ENABLE_TF_SCRAPE=1 TRANSFERMARKT_URL="https://www.transfermarkt.it/juventus-fc/transfers/verein/506" \
    python etl_web_transfermarkt.py --mode html --team "Juventus" --season 2025-26 --ingest --write-roster

Wikipedia (fallback) con titolo noto (evita 429 e ricerche large):
  python etl_web_transfermarkt.py --mode wikipedia --team "Juventus" --season 2025-26 \
    --wiki-title "Juventus Football Club 2025-2026" --ingest --write-roster

Se non sai il titolo, puoi provare la ricerca robusta (lenta, con backoff 429):
  python etl_web_transfermarkt.py --mode wikipedia --team "Genoa" --season 2025-26 --robust-search --ingest --write-roster
"""

import os
import sys
import csv
import json
import time
import uuid
import argparse
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# KnowledgeManager è opzionale (per --ingest / --write-roster)
try:
    from knowledge_manager import KnowledgeManager
    KM_AVAILABLE = True
except Exception:
    KM_AVAILABLE = False

LOG = logging.getLogger("etl_web_transfermarkt")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

DATA_DIR = Path("./data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# -----------------------------
# Helpers comuni
# -----------------------------
def _now_date_tag() -> str:
    return datetime.now().strftime("%Y%m%d")

def _norm(s: Optional[str]) -> str:
    return " ".join(str(s or "").split())

def _mk_jsonl_path(team: str) -> Path:
    safe = team.lower().replace(" ", "_")
    return DATA_DIR / f"transfers_{safe}_{_now_date_tag()}.jsonl"

def _load_json(path: Path) -> Optional[Any]:
    if not path.exists(): return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def _save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def _append_jsonl(path: Path, items: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

# -----------------------------
# Transfermarkt HTML (prioritario)
# -----------------------------
def tm_run_html(team: str, season: str, url: str) -> List[Dict[str, Any]]:
    if os.environ.get("ENABLE_TF_SCRAPE", "0") not in ("1","true","True"):
        LOG.warning("[TM] Scrape disabilitato. Set ENABLE_TF_SCRAPE=1")
        return []
    if not url:
        LOG.error("[TM] TRANSFERMARKT_URL mancante.")
        return []

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; FantaETL/1.0; +https://example.local)"
        }
        LOG.info("[TM] GET %s", url)
        r = requests.get(url, headers=headers, timeout=25)
        if r.status_code != 200:
            LOG.error("[TM] HTTP %s su %s", r.status_code, url)
            return []
        soup = BeautifulSoup(r.text, "html.parser")

        # pagina "Transfers" di solito ha tabelle con class "items"
        rows: List[Dict[str, Any]] = []
        for tb in soup.select("table.items"):
            for tr in tb.select("tbody > tr"):
                tds = tr.find_all("td")
                if len(tds) < 3: 
                    continue
                # giocatore: link profilo /spieler/
                a_player = tr.select_one("a[href*='/profil/spieler/'], a[href*='/player/'], a[href*='spieler']")
                name = _norm(a_player.get_text()) if a_player else ""
                if not name: 
                    continue

                # club precedente (colonna con link /verein/)
                a_from = tr.select_one("td a[href*='/verein/']")
                from_team = _norm(a_from.get_text()) if a_from else ""

                # fee (ultima/penultima colonna destra spesso class 'rechts'/'hauptlink')
                fee_td = tr.find("td", class_="rechts") or tr.find("td", class_="rechts hauptlink")
                fee = _norm(fee_td.get_text()) if fee_td else ""

                rows.append({
                    "id": f"tr_{uuid.uuid4().hex[:10]}",
                    "type": "transfer",
                    "team": team,
                    "season": season,
                    "player": name,
                    "direction": "in",  # pagina "arrivi" tipicamente
                    "from_team": from_team,
                    "fee": fee,
                    "source": "transfermarkt_html",
                    "source_date": datetime.now().strftime("%Y-%m-%d"),
                    "valid_from": datetime.now().strftime("%Y-%m-%d"),
                    "valid_to": "2099-12-31",
                })

        LOG.info("[TM] %d record estratti", len(rows))
        return rows

    except Exception as e:
        LOG.error("[TM] Errore: %s", e)
        return []

# -----------------------------
# Wikipedia fallback (robusto con backoff 429)
# -----------------------------
WIKI_API = {
    "it": "https://it.wikipedia.org/w/api.php",
    "en": "https://en.wikipedia.org/w/api.php",
}

# Mappa titoli per pagine Serie A (riduce ricerche aggressive)
WIKI_TITLE_HINTS = {
    # team -> season -> title
    "juventus": {
        "2025-26": "Juventus Football Club 2025-2026",
        "2024-25": "Juventus Football Club 2024-2025",
    },
    "genoa": {
        "2025-26": "Genoa Cricket and Football Club 2025-2026",
        "2024-25": "Genoa Cricket and Football Club 2024-2025",
    },
    # aggiungi qui altri club se vuoi
}

def _wiki_get(api_url: str, params: Dict[str, Any], retries: int = 4, base_sleep: float = 1.2) -> Optional[dict]:
    for i in range(retries):
        try:
            r = requests.get(api_url, params=params, timeout=25)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                ra = r.headers.get("Retry-After")
                wait = float(ra) if ra else (base_sleep * (2 ** i))
                LOG.warning("[WIKI] 429: backoff %.1fs", wait)
                time.sleep(wait)
                continue
            LOG.warning("[WIKI] HTTP %s su %s", r.status_code, params.get("action"))
        except Exception as e:
            LOG.warning("[WIKI] errore %s", e)
        time.sleep(base_sleep * (2 ** i))
    return None

def wiki_fetch_wikitext(title: str, lang: str) -> Optional[str]:
    api = WIKI_API.get(lang, WIKI_API["it"])
    resp = _wiki_get(api, {"action":"parse","page":title,"prop":"wikitext","format":"json"})
    if not resp: 
        return None
    return ((resp.get("parse") or {}).get("wikitext") or {}).get("*")

def wiki_fetch_html(title: str, lang: str) -> Optional[str]:
    api = WIKI_API.get(lang, WIKI_API["it"])
    resp = _wiki_get(api, {"action":"parse","page":title,"prop":"text","format":"json"})
    if not resp: 
        return None
    return ((resp.get("parse") or {}).get("text") or {}).get("*")

def wiki_search_titles(team: str, season: str, lang: str) -> List[str]:
    api = WIKI_API.get(lang, WIKI_API["it"])
    queries = [
        f"{team} {season} trasferimenti",
        f"{team} {season} calciomercato",
        f"{team} stagione {season}",
        f"{team} {season} rosa",
        f"{team} {season} season",
        f"{team} transfers {season}",
    ]
    out: List[str] = []
    for q in queries:
        resp = _wiki_get(api, {"action":"query","list":"search","srsearch":q,"format":"json","srlimit":6})
        if not resp: 
            continue
        for hit in (resp.get("query") or {}).get("search", []):
            t = hit.get("title")
            if t and t not in out:
                out.append(t)
        if out:
            break  # basta il primo set valido per ridurre call
    LOG.info("[WIKI] candidati(%s): %s", lang, out)
    return out

def _parse_transfers_from_wikitext(wikitext: str, team: str, season: str) -> List[Dict[str, Any]]:
    res: List[Dict[str, Any]] = []
    if not wikitext:
        return res
    lines = wikitext.splitlines()
    grab = False
    keys = ["trasferimenti", "acquisti", "arrivi", "transfers", "arrivals"]
    buff: List[str] = []
    for ln in lines:
        low = ln.lower()
        if any(("==" in low) and (k in low) for k in keys):
            grab = True
            continue
        if grab and ln.strip().startswith("=="):
            break
        if grab:
            buff.append(ln)

    for ln in buff:
        raw = ln.strip().lstrip("*").strip()
        if not raw or len(raw) < 2:
            continue
        raw = raw.replace("'''","").replace("''","").replace("[[","").replace("]]","")
        parts = [p.strip() for p in raw.replace("—","-").split("-")]
        name = parts[0] if parts else ""
        if len(name) < 2:
            continue
        details = " - ".join(parts[1:]) if len(parts) > 1 else ""
        res.append({
            "id": f"tr_{uuid.uuid4().hex[:10]}",
            "type": "transfer",
            "team": team,
            "season": season,
            "player": name,
            "direction": "in",
            "details": details,
            "source": "wikipedia",
            "source_date": datetime.now().strftime("%Y-%m-%d"),
            "valid_from": datetime.now().strftime("%Y-%m-%d"),
            "valid_to": "2099-12-31",
        })
    return res

def _parse_transfers_from_html(html: str, team: str, season: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not html:
        return out
    soup = BeautifulSoup(html, "html.parser")
    headers_kw = {"trasferimenti","acquisti","arrivi","transfers","arrivals"}

    # tabelle con caption/thead che contengono keyword
    for table in soup.select("table"):
        cap = table.find("caption")
        cap_text = _norm(cap.get_text(" ", strip=True).lower()) if cap else ""
        head_text = " ".join(th.get_text(" ", strip=True).lower() for th in table.select("thead th"))
        if not any(k in (cap_text + " " + head_text) for k in headers_kw):
            continue
        for tr in table.select("tbody tr"):
            tds = tr.find_all(["td","th"])
            if not tds:
                continue
            a = tds[0].find("a")
            name = _norm(a.get_text()) if a else _norm(tds[0].get_text())
            if len(name) < 2:
                continue
            details = _norm(tds[1].get_text()) if len(tds) > 1 else ""
            out.append({
                "id": f"tr_{uuid.uuid4().hex[:10]}",
                "type": "transfer",
                "team": team,
                "season": season,
                "player": name,
                "direction": "in",
                "details": details,
                "source": "wikipedia",
                "source_date": datetime.now().strftime("%Y-%m-%d"),
                "valid_from": datetime.now().strftime("%Y-%m-%d"),
                "valid_to": "2099-12-31",
            })

    # liste puntate sotto h2/h3 con keyword
    for h in soup.select("h2, h3"):
        txt = _norm(h.get_text(" ", strip=True).lower())
        if not any(k in txt for k in headers_kw):
            continue
        sib = h.find_next_sibling()
        while sib and sib.name not in ("h2","h3"):
            if sib.name in ("ul","ol"):
                for li in sib.select("li"):
                    t = _norm(li.get_text(" ", strip=True))
                    if not t:
                        continue
                    parts = [p.strip() for p in t.replace("—","-").split("-")]
                    nm = parts[0] if parts else ""
                    if len(nm) >= 2:
                        meta = " - ".join(parts[1:]) if len(parts) > 1 else ""
                        out.append({
                            "id": f"tr_{uuid.uuid4().hex[:10]}",
                            "type": "transfer",
                            "team": team,
                            "season": season,
                            "player": nm,
                            "direction": "in",
                            "details": meta,
                            "source": "wikipedia",
                            "source_date": datetime.now().strftime("%Y-%m-%d"),
                            "valid_from": datetime.now().strftime("%Y-%m-%d"),
                            "valid_to": "2099-12-31",
                        })
            sib = sib.find_next_sibling()
    return out

def wiki_run(team: str, season: str, lang: str, title: Optional[str], robust_search: bool) -> List[Dict[str, Any]]:
    # 1) prova mapping titolo “hint” (evita query search massive → meno 429)
    tkey = team.lower()
    title_candidates: List[str] = []
    if title:
        title_candidates = [title]
        LOG.info("[WIKI] titolo forzato: %s", title)
    elif tkey in WIKI_TITLE_HINTS and season in WIKI_TITLE_HINTS[tkey]:
        title_candidates = [WIKI_TITLE_HINTS[tkey][season]]
        LOG.info("[WIKI] titolo da hints: %s", title_candidates[0])
    elif robust_search:
        title_candidates = wiki_search_titles(team, season, lang)
        if not title_candidates and lang == "it":
            LOG.info("[WIKI] fallback en")
            title_candidates = wiki_search_titles(team, season, "en")
    else:
        LOG.warning("[WIKI] nessun titolo noto. Usa --wiki-title o --robust-search per cercare.")

    if not title_candidates:
        return []

    # 2) prova in ordine: wikitext → HTML, con backoff automatico
    for t in title_candidates:
        LOG.info("[WIKI] prova pagina: %s", t)
        wt = wiki_fetch_wikitext(t, lang)
        items = _parse_transfers_from_wikitext(wt or "", team, season)
        if items:
            LOG.info("[WIKI] estratti %d (wikitext)", len(items))
            return items

        html = wiki_fetch_html(t, lang)
        items2 = _parse_transfers_from_html(html or "", team, season)
        if items2:
            LOG.info("[WIKI] estratti %d (html)", len(items2))
            return items2

        LOG.info("[WIKI] nessun dato utile in '%s'", t)

    LOG.warning("[WIKI] nessun trasferimento trovato per %s %s", team, season)
    return []

# -----------------------------
# CSV (export Transfermarkt)
# -----------------------------
def run_csv(csv_path: Path, team: str, season: str) -> List[Dict[str, Any]]:
    if not csv_path.exists():
        LOG.error("[CSV] file non trovato: %s", csv_path)
        return []
    rows: List[Dict[str, Any]] = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            name = _norm(r.get("Player") or r.get("Giocatore") or r.get("Nome"))
            if not name:
                continue
            rows.append({
                "id": f"tr_{uuid.uuid4().hex[:10]}",
                "type": "transfer",
                "team": team,
                "season": season,
                "player": name,
                "direction": "in",
                "from_team": _norm(r.get("From") or r.get("Da") or r.get("Provenienza")),
                "fee": _norm(r.get("Fee") or r.get("Costo") or r.get("Prezzo")),
                "role": _norm(r.get("Position") or r.get("Ruolo")),
                "source": "transfermarkt_csv",
                "source_date": datetime.now().strftime("%Y-%m-%d"),
                "valid_from": datetime.now().strftime("%Y-%m-%d"),
                "valid_to": "2099-12-31",
            })
    LOG.info("[CSV] %d record normalizzati", len(rows))
    return rows

# -----------------------------
# Merge & Ingest
# -----------------------------
def merge_into_roster(transfers: List[Dict[str, Any]], roster_path: Path) -> int:
    roster = _load_json(roster_path) or []
    key = lambda p: (p.get("name","").lower(), p.get("team","").lower())
    idx = { key(p): p for p in roster }
    updates = 0
    for tr in transfers:
        nm = tr.get("player","")
        tm = tr.get("team","")
        if not nm or not tm: 
            continue
        k = (nm.lower(), tm.lower())
        if k not in idx:
            rec = {
                "name": nm,
                "team": tm,
                "role": tr.get("role") or "NA",
                "season": tr.get("season"),
                "source": tr.get("source"),
                "source_date": tr.get("source_date"),
                "type": "current_player"
            }
            roster.append(rec)
            idx[k] = rec
            updates += 1
        else:
            rec = idx[k]
            rec["season"] = tr.get("season")
            rec["source"] = tr.get("source")
            rec["source_date"] = tr.get("source_date")
            updates += 1
    _save_json(roster_path, roster)
    LOG.info("[ROSTER] %d upsert; totale=%d", updates, len(roster))
    return updates

def ingest_into_kb(transfers: List[Dict[str, Any]]) -> int:
    if not KM_AVAILABLE:
        LOG.warning("[INGEST] KnowledgeManager non disponibile")
        return 0
    try:
        km = KnowledgeManager()
        docs, metas, ids = [], [], []
        for tr in transfers:
            docs.append(f"Transfer IN: {tr.get('player')} -> {tr.get('team')} ({tr.get('season')}). Fee: {tr.get('fee','n/a')}.")
            metas.append({
                "type": "transfer",
                "player": tr.get("player"),
                "team": tr.get("team"),
                "season": tr.get("season"),
                "from_team": tr.get("from_team",""),
                "fee": tr.get("fee",""),
                "source": tr.get("source"),
                "source_date": tr.get("source_date"),
                "valid_from": tr.get("valid_from"),
                "valid_to": tr.get("valid_to"),
            })
            ids.append(tr.get("id") or f"tr_{uuid.uuid4().hex[:10]}")
        n = km.upsert(docs=docs, metadatas=metas, ids=ids)
        LOG.info("[INGEST] upsert KB: %s", n)
        return int(n or 0)
    except Exception as e:
        LOG.error("[INGEST] errore: %s", e)
        return 0

# -----------------------------
# main
# -----------------------------
def main():
    ap = argparse.ArgumentParser(description="ETL Transfermarkt/Wikipedia")
    ap.add_argument("--mode", choices=["html","wikipedia","csv"], default="html")
    ap.add_argument("--team", required=True)
    ap.add_argument("--season", default="2025-26")
    ap.add_argument("--csv-path", help="CSV Transfermarkt export")
    # Wikipedia
    ap.add_argument("--wiki-lang", default="it")
    ap.add_argument("--wiki-title", help="Titolo pagina Wikipedia da usare direttamente")
    ap.add_argument("--robust-search", action="store_true", help="Usa ricerca API (lenta) se non c'è titolo")
    # Azioni
    ap.add_argument("--write-roster", action="store_true")
    ap.add_argument("--ingest", action="store_true")
    args = ap.parse_args()

    team = _norm(args.team)
    season = _norm(args.season)

    LOG.info("[ETL] start mode=%s team=%s season=%s", args.mode, team, season)

    items: List[Dict[str, Any]] = []
    if args.mode == "html":
        url = os.environ.get("TRANSFERMARKT_URL", "")
        items = tm_run_html(team, season, url)
    elif args.mode == "wikipedia":
        items = wiki_run(team, season, args.wiki_lang, args.wiki_title, args.robust_search)
    elif args.mode == "csv":
        if not args.csv_path:
            LOG.error("[CSV] --csv-path richiesto")
            sys.exit(2)
        items = run_csv(Path(args.csv_path), team, season)

    if not items:
        LOG.warning("[ETL] Nessun dato estratto.")
        sys.exit(0)

    out = _mk_jsonl_path(team)
    _append_jsonl(out, items)
    LOG.info("[ETL] scritto %s (%d righe)", out, len(items))

    if args.write_roster:
        merge_into_roster(items, Path("./season_roster.json"))

    if args.ingest:
        ingest_into_kb(items)

    LOG.info("[ETL] done.")

if __name__ == "__main__":
    main()
