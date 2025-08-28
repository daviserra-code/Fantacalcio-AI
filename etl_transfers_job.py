#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
etl_transfers_job.py
Job ETL per aggiornare automaticamente gli "acquisti" delle squadre nel KB.

Fonti:
- Wikipedia (calciomercato estivo 2025 IT) via WebFallback
- RSS/Ufficiali (se configurati)
- Transfermarkt (OPZIONALE) via web_fallback_tm.TransfermarktFallback
  => Abilita con env TRANSFERMARKT_FALLBACK=1 (rispetta ToS/robots, rate limit basso)

Esecuzione:
- Manuale: python etl_transfers_job.py
- Periodica (Replit): usa replit "Secrets" per env e un cron semplice (p. es. UptimeRobot/cron esterno)
- Loop interno: setta JOB_INTERVAL_MIN>0 per un loop (non consigliato in Replit free)

Scrive in Chroma tramite KnowledgeManager.add_knowledge(...)
"""

import os
import re
import time
import json
import logging
import datetime as dt
from typing import List, Dict, Any, Optional

from knowledge_manager import KnowledgeManager
from web_fallback import WebFallbackWikipedia  # Wikipedia fallback (il tuo file precedente)
# Transfermarkt fallback è opzionale
try:
    from web_fallback_tm import TransfermarktFallback
except Exception:
    TransfermarktFallback = None

# Apify fallback (opzionale ma raccomandato per produzione)
try:
    from apify_transfermarkt_scraper import ApifyTransfermarktScraper
    APIFY_AVAILABLE = bool(os.environ.get("APIFY_API_TOKEN"))
except Exception:
    ApifyTransfermarktScraper = None
    APIFY_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("etl_transfers_job")

# Config
CHROMA_DIR = os.environ.get("CHROMA_DIR", "./chroma_db")
CHROMA_COLLECTION = os.environ.get("CHROMA_COLLECTION", "fantacalcio_knowledge")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "all-MiniLM-L6-v2")

SEASON = os.environ.get("SEASON", "2025-26")
USE_TM = os.environ.get("TRANSFERMARKT_FALLBACK", "0") == "1"
USE_APIFY = os.environ.get("USE_APIFY_TRANSFERMARKT", "0") == "1" and APIFY_AVAILABLE
REQUEST_DELAY = float(os.environ.get("REQUEST_DELAY", "2.0"))  # delay tra chiamate per educazione
JOB_INTERVAL_MIN = int(os.environ.get("JOB_INTERVAL_MIN", "0"))  # se >0, loop periodico

SERIE_A_TEAMS = [
    "Atalanta", "Bologna", "Cagliari", "Como", "Empoli", "Fiorentina", "Genoa",
    "Inter", "Juventus", "Lazio", "Lecce", "Milan", "Monza", "Napoli", "Parma",
    "Roma", "Torino", "Udinese", "Venezia", "Hellas Verona",
]

# Opzionale: RSS/ufficiali (metti qui feed del club se li hai)
TEAM_RSS: Dict[str, List[str]] = {
    # "Genoa": ["https://www.genoacfc.it/feed/"],  # esempio se esistesse un feed compatibile
}

def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")

def _unique(seq: List[str]) -> List[str]:
    out = []
    seen = set()
    for x in seq:
        k = x.lower().strip()
        if k and k not in seen:
            out.append(x.strip())
            seen.add(k)
    return out

def upsert_transfer(km: KnowledgeManager, team: str, player: str, sources: List[str], season: str, source_label: str):
    """Scrive/aggiorna un documento di tipo 'transfer' (direction=in) nel KB."""
    today = dt.date.today().isoformat()
    doc_id = f"transfer:{season}:{slugify(team)}:{slugify(player)}"
    text = f"{player} è stato acquistato dal {team} per la stagione {season}."

    try:
        km.add_knowledge(
            text=text,
            metadata={
                "id": doc_id,
                "type": "transfer",
                "direction": "in",
                "team": team,
                "player": player,
                "season": season,
                "source": source_label,
                "source_url": ", ".join(sources) if sources else source_label,
                "source_date": today,
                "updated_at": today,
            }
        )
        logger.info("Upsert transfer OK: %s", doc_id)
    except Exception as e:
        logger.warning("Upsert transfer FAIL %s: %s", doc_id, e)

def _merge_sources(*args: List[str]) -> List[str]:
    merged = []
    for group in args:
        if not group:
            continue
        for s in group:
            if s not in merged:
                merged.append(s)
    return merged

def fetch_from_wikipedia(team: str) -> Dict[str, Any]:
    wf = WebFallbackWikipedia(enabled=True, lang="it")
    res = wf.fetch_recent_transfers(team)
    return {
        "players": res,
        "sources": [f"https://it.wikipedia.org/wiki/{team.replace(' ', '_')}"]
    }

def fetch_from_tm(team: str) -> Dict[str, Any]:
    if not USE_TM or TransfermarktFallback is None:
        return {"players": [], "sources": [], "elapsed": 0.0, "label": "TM (disabled)"}
    tm = TransfermarktFallback(timeout_s=float(os.environ.get("WEB_TIMEOUT", "7.5")))
    res = tm.fetch_team_transfers(team_name=team, season=SEASON)
    return {
        "players": res.get("acquisti", []) or [],
        "sources": res.get("sources", []) or [],
        "elapsed": res.get("elapsed", 0.0),
        "label": "Transfermarkt",
    }

def fetch_from_apify(team: str) -> Dict[str, Any]:
    """Fetch tramite Apify (più affidabile per Transfermarkt)"""
    if not USE_APIFY or ApifyTransfermarktScraper is None:
        return {"players": [], "sources": [], "elapsed": 0.0, "label": "Apify (disabled)"}

    try:
        scraper = ApifyTransfermarktScraper()
        start_time = time.time()

        transfers = scraper.scrape_team_transfers(team=team, season=SEASON, arrivals_only=True)
        players = [t.get("player") for t in transfers if t.get("direction") == "in" and t.get("player")]

        elapsed = time.time() - start_time
        sources = [f"https://apify.com/transfermarkt-scraper"]

        return {
            "players": players,
            "sources": sources,
            "elapsed": elapsed,
            "label": "Apify Transfermarkt",
        }
    except Exception as e:
        logger.warning("Errore Apify per %s: %s", team, e)
        return {"players": [], "sources": [], "elapsed": 0.0, "label": "Apify (error)"}

def fetch_from_rss(team: str) -> Dict[str, Any]:
    """Placeholder semplice: se configuri feed RSS ufficiali, qui puoi parsare 'nuovo giocatore'."""
    # Non implementato in dettaglio perché i feed variano. Fornisco struttura compatibile.
    # Se aggiungi feed, estrai i titoli tipo "UFFICIALE: Nome Cognome al TEAM".
    feeds = TEAM_RSS.get(team, [])
    if not feeds:
        return {"players": [], "sources": [], "elapsed": 0.0, "label": "RSS (none)"}
    # TODO: implementare parsing feed con 'feedparser' se lo aggiungi ai requirements.
    return {"players": [], "sources": feeds, "elapsed": 0.0, "label": "RSS"}

def run_once():
    logger.info("[ETL] Avvio job transfers — season=%s", SEASON)

    km = KnowledgeManager()

    total_upserts = 0
    for i, team in enumerate(SERIE_A_TEAMS, start=1):
        logger.info("[ETL] (%d/%d) %s", i, len(SERIE_A_TEAMS), team)

        # 1) Wikipedia
        wiki = fetch_from_wikipedia(team)
        time.sleep(REQUEST_DELAY)

        # 2) Transfermarkt standard (opzionale)
        tm = fetch_from_tm(team)
        if USE_TM:
            time.sleep(REQUEST_DELAY)

        # 3) Apify Transfermarkt (raccomandato per produzione)
        apify = fetch_from_apify(team)
        if USE_APIFY:
            time.sleep(REQUEST_DELAY)

        # 4) RSS/ufficiali (se configurati)
        rss = fetch_from_rss(team)

        # Merge dedup
        merged_players = _unique(wiki["players"] + tm["players"] + apify["players"] + rss["players"])
        merged_sources = _merge_sources(wiki["sources"], tm["sources"], apify["sources"], rss["sources"])

        if not merged_players:
            logger.info("[ETL] Nessun acquisto trovato per %s (fonti: %s, %s, %s, %s)",
                        team, wiki["label"], tm["label"], apify["label"], rss["label"])
            continue

        for name in merged_players:
            upsert_transfer(km, team, name, merged_sources, SEASON, source_label=";".join(
                [lbl for lbl in [
                    wiki["label"],
                    tm["label"] if USE_TM else None,
                    apify["label"] if USE_APIFY else None,
                    rss["label"] if rss["sources"] else None
                ] if lbl]
            ))
            total_upserts += 1

        logger.info("[ETL] %s: %d acquisti aggiornati", team, len(merged_players))

    logger.info("[ETL] Completato. Upsert totali: %d", total_upserts)

def main():
    if JOB_INTERVAL_MIN > 0:
        logger.info("[ETL] Loop periodico attivo: ogni %d minuti", JOB_INTERVAL_MIN)
        while True:
            try:
                run_once()
            except Exception as e:
                logger.error("[ETL] Errore run_once: %s", e)
            time.sleep(JOB_INTERVAL_MIN * 60)
    else:
        run_once()

if __name__ == "__main__":
    main()