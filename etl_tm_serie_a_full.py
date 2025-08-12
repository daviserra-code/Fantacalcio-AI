#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
etl_tm_serie_a_full.py — One-shot ETL Transfermarkt per tutta la Serie A

Esempi:
  # Run standard (arrivi+cessioni) su mapping built-in, stagione 2025-26, con merge roster e ingest KB
  python etl_tm_serie_a_full.py --season 2025-26 --write-roster --ingest

  # Solo arrivi, 2s di delay tra club, output in ./data/etl_2025_serie_a/
  python etl_tm_serie_a_full.py --season 2025-26 --arrivals-only --delay 2 --out-dir ./data/etl_2025_serie_a --write-roster

  # Override mapping da file JSON (team->Transfermarkt URL)
  python etl_tm_serie_a_full.py --season 2025-26 --urls-json ./config/serie_a_transfermarkt_urls.json --write-roster

Formato JSON override (esempio):
{
  "Juventus": "https://www.transfermarkt.it/juventus-fc/transfers/verein/506",
  "Inter": "https://www.transfermarkt.it/inter-mailand/transfers/verein/46"
}
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
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

import requests
from bs4 import BeautifulSoup

# KnowledgeManager opzionale: usato solo se disponibile e si passa --ingest
try:
    from knowledge_manager import KnowledgeManager
    KM_AVAILABLE = True
except Exception:
    KM_AVAILABLE = False

LOG = logging.getLogger("etl_tm_serie_a_full")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

DATA_DIR = Path("./data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# -----------------------------------------------------------------------------
# Built-in mapping (ragionevole per molte installazioni; puoi override via JSON/env)
# NB: gli slug/ID Transfermarkt possono cambiare: se qualche URL 404a, override via file JSON.
# -----------------------------------------------------------------------------
DEFAULT_TM_URLS: Dict[str, str] = {
    "Atalanta":  "https://www.transfermarkt.it/atalanta-bergamo/transfers/verein/800",
    "Bologna":   "https://www.transfermarkt.it/bologna-fc-1909/transfers/verein/1025",
    "Cagliari":  "https://www.transfermarkt.it/cagliari-calcio/transfers/verein/1390",
    "Como":      "https://www.transfermarkt.it/como-1907/transfers/verein/280",
    "Empoli":    "https://www.transfermarkt.it/empoli-fc/transfers/verein/749",
    "Fiorentina":"https://www.transfermarkt.it/acf-fiorentina/transfers/verein/430",
    "Genoa":     "https://www.transfermarkt.it/genoa-cfc/transfers/verein/252",
    "Inter":     "https://www.transfermarkt.it/inter-mailand/transfers/verein/46",
    "Juventus":  "https://www.transfermarkt.it/juventus-fc/transfers/verein/506",
    "Lazio":     "https://www.transfermarkt.it/ss-lazio/transfers/verein/398",
    "Lecce":     "https://www.transfermarkt.it/us-lecce/transfers/verein/1020",
    "Milan":     "https://www.transfermarkt.it/ac-mailand/transfers/verein/5",
    "Monza":     "https://www.transfermarkt.it/ac-monza/transfers/verein/2919",
    "Napoli":    "https://www.transfermarkt.it/ssc-neapel/transfers/verein/6195",
    "Parma":     "https://www.transfermarkt.it/parma-calcio-1913/transfers/verein/130",
    "Roma":      "https://www.transfermarkt.it/as-roma/transfers/verein/12",
    "Torino":    "https://www.transfermarkt.it/torino-fc/transfers/verein/416",
    "Udinese":   "https://www.transfermarkt.it/udinese-calcio/transfers/verein/410",
    "Verona":    "https://www.transfermarkt.it/hellas-verona/transfers/verein/276",
    "Venezia":   "https://www.transfermarkt.it/venezia-fc/transfers/verein/907",
}

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def now_iso_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def safe_text(s: Optional[str]) -> str:
    return " ".join((s or "").split())

def jsonl_path(out_dir: Path, team: str, season: str) -> Path:
    slug = team.lower().replace(" ", "_")
    return out_dir / f"tm_transfers_{slug}_{season.replace('/','-').replace(' ','_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"

def load_json(p: Path) -> Optional[Any]:
    if not p.exists(): return None
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def save_json(p: Path, obj: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def append_jsonl(p: Path, items: List[Dict[str, Any]]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

# -----------------------------------------------------------------------------
# Scrape Transfermarkt HTML: Arrivi/Cessioni
# -----------------------------------------------------------------------------
ARRIVALS_KEYS = {"arrivi", "acquisti", "zugänge", "arrivals", "incoming"}
DEPARTURES_KEYS = {"cessioni", "abgänge", "departures", "outgoing", "uscite"}

def infer_direction_from_context(table: BeautifulSoup) -> str:
    """
    Prova a inferire 'in' o 'out' guardando heading/caption attorno alla table.items
    """
    # caption
    cap = table.find("caption")
    cap_txt = safe_text(cap.get_text(" ", strip=True).lower()) if cap else ""
    if any(k in cap_txt for k in ARRIVALS_KEYS):
        return "in"
    if any(k in cap_txt for k in DEPARTURES_KEYS):
        return "out"

    # heading immediatamente precedente (h2/h3/h4)
    prev = table.find_previous(["h2","h3","h4"])
    if prev:
        pt = safe_text(prev.get_text(" ", strip=True).lower())
        if any(k in pt for k in ARRIVALS_KEYS):
            return "in"
        if any(k in pt for k in DEPARTURES_KEYS):
            return "out"

    # fallback: se il titolo pagina contiene “arrivals” ecc. (poco affidabile, ma meglio di nulla)
    return "in"

def parse_tm_table(table: BeautifulSoup, team: str, season: str, direction_hint: Optional[str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    direction = direction_hint or infer_direction_from_context(table)
    for tr in table.select("tbody > tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue

        # giocatore: spesso nel td con un <a> su /profil/spieler/ o simile
        a_player = tr.select_one("a[href*='/profil/spieler/'], a[href*='/player/'], a[href*='spieler']")
        player = safe_text(a_player.get_text()) if a_player else safe_text(tds[0].get_text())

        if len(player) < 2:
            continue

        # club from/to (c'è un link /verein/)
        a_club = tr.select_one("td a[href*='/verein/']")
        club_txt = safe_text(a_club.get_text()) if a_club else ""

        # fee: tipicamente un td "rechts" o "rechts hauptlink"
        fee_td = tr.find("td", class_="rechts") or tr.find("td", class_="rechts hauptlink")
        fee = safe_text(fee_td.get_text()) if fee_td else ""

        rec = {
            "id": f"tr_{uuid.uuid4().hex[:10]}",
            "type": "transfer",
            "season": season,
            "team": team,
            "player": player,
            "direction": direction,
            "from_team": club_txt if direction == "in" else team,   # semantica: da dove arriva / dove va
            "to_team":   team if direction == "in" else club_txt,
            "fee": fee,
            "source": "transfermarkt_html",
            "source_date": now_iso_date(),
            "valid_from": now_iso_date(),
            "valid_to": "2099-12-31",
        }
        rows.append(rec)
    return rows

def scrape_tm_team(url: str, team: str, season: str, arrivals_only: bool = False, departures_only: bool = False) -> List[Dict[str, Any]]:
    headers = {
        "User-Agent": os.environ.get("TM_USER_AGENT",
                                     "Mozilla/5.0 (compatible; FantaETL/1.0; +https://example.local)")
    }
    LOG.info("[TM] GET %s", url)
    r = requests.get(url, headers=headers, timeout=30)
    if r.status_code != 200:
        LOG.error("[TM] HTTP %s su %s", r.status_code, url)
        return []
    soup = BeautifulSoup(r.text, "html.parser")

    all_rows: List[Dict[str, Any]] = []
    for table in soup.select("table.items"):
        direction = infer_direction_from_context(table)
        if arrivals_only and direction != "in":
            continue
        if departures_only and direction != "out":
            continue
        chunk = parse_tm_table(table, team, season, direction_hint=direction)
        all_rows.extend(chunk)

    LOG.info("[TM] %s: %d trasferimenti estratti (%s)", team, len(all_rows),
             "solo arrivi" if arrivals_only else ("solo cessioni" if departures_only else "totale"))
    return all_rows

# -----------------------------------------------------------------------------
# Roster merge & ingest
# -----------------------------------------------------------------------------
def merge_into_roster(transfers: List[Dict[str, Any]], roster_path: Path) -> int:
    roster = load_json(roster_path) or []
    # indicizzazione: (name, team)
    def key(p: Dict[str, Any]) -> Tuple[str, str]:
        return (p.get("name","").lower(), p.get("team","").lower())

    idx = { key(p): p for p in roster }
    updates = 0
    for tr in transfers:
        if tr.get("direction") != "in":
            continue  # il roster locale rappresenta i giocatori ATTUALI della squadra
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
                "type": "current_player",
                "source": tr.get("source"),
                "source_date": tr.get("source_date"),
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
    save_json(roster_path, roster)
    LOG.info("[ROSTER] upsert=%d; totale=%d", updates, len(roster))
    return updates

def ingest_into_kb(transfers: List[Dict[str, Any]]) -> int:
    if not KM_AVAILABLE:
        LOG.warning("[INGEST] KnowledgeManager non disponibile")
        return 0
    try:
        km = KnowledgeManager()
        docs, metas, ids = [], [], []
        for tr in transfers:
            direction_str = "IN" if tr.get("direction") == "in" else "OUT"
            docs.append(
                f"Transfer {direction_str}: {tr.get('player')} "
                f"{'->' if direction_str=='IN' else '<-'} {tr.get('team')} ({tr.get('season')}). "
                f"From: {tr.get('from_team','n/a')} To: {tr.get('to_team','n/a')}. Fee: {tr.get('fee','n/a')}."
            )
            metas.append({
                "type": "transfer",
                "player": tr.get("player"),
                "team": tr.get("team"),
                "season": tr.get("season"),
                "direction": tr.get("direction"),
                "from_team": tr.get("from_team",""),
                "to_team": tr.get("to_team",""),
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

# -----------------------------------------------------------------------------
# Mapping loader (override da JSON o ENV)
# -----------------------------------------------------------------------------
def load_urls_mapping(urls_json: Optional[str]) -> Dict[str, str]:
    mapping = DEFAULT_TM_URLS.copy()
    # override via JSON file
    if urls_json:
        p = Path(urls_json)
        if p.exists():
            try:
                with p.open("r", encoding="utf-8") as f:
                    user_map = json.load(f)
                for k, v in (user_map or {}).items():
                    if isinstance(v, str) and v.startswith("http"):
                        mapping[k] = v
                LOG.info("[CONF] Loaded URLs from %s (n=%d)", p, len(user_map))
            except Exception as e:
                LOG.warning("[CONF] Impossibile leggere %s: %s", p, e)

    # override per singola squadra via env TRANSFERMARKT_URL_<TEAM_UPPER>
    for team in list(mapping.keys()):
        env_key = f"TRANSFERMARKT_URL_{team.upper().replace(' ','_')}"
        if os.environ.get(env_key):
            mapping[team] = os.environ[env_key]

    # filtro opzionale via SERIE_A_TEAMS (lista separata da virgole)
    teams_env = os.environ.get("SERIE_A_TEAMS")
    if teams_env:
        requested = [t.strip() for t in teams_env.split(",") if t.strip()]
        mapping = { t: mapping[t] for t in requested if t in mapping }
        LOG.info("[CONF] Filtrate squadre da SERIE_A_TEAMS: %s", ", ".join(mapping.keys()))

    return mapping

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="One-shot ETL Transfermarkt Serie A")
    ap.add_argument("--season", default="2025-26", help="Stagione (es. 2025-26)")
    ap.add_argument("--urls-json", help="JSON mapping team->Transfermarkt URL per override")
    ap.add_argument("--arrivals-only", action="store_true", help="Solo Arrivi")
    ap.add_argument("--departures-only", action="store_true", help="Solo Cessioni")
    ap.add_argument("--out-dir", default="./data", help="Cartella output JSONL")
    ap.add_argument("--delay", type=float, default=1.0, help="Delay tra squadre (secondi)")
    ap.add_argument("--write-roster", action="store_true", help="Aggiorna season_roster.json con gli Arrivi")
    ap.add_argument("--ingest", action="store_true", help="Ingerisci in Knowledge Base (Chroma) se disponibile")
    args = ap.parse_args()

    if args.arrivals_only and args.departures_only:
        LOG.error("Non puoi usare --arrivals-only e --departures-only insieme.")
        sys.exit(2)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    mapping = load_urls_mapping(args.urls_json)
    if not mapping:
        LOG.error("Nessuna squadra configurata (mapping vuoto).")
        sys.exit(2)

    LOG.info("[ETL] Serie A — squadre=%d — stagione=%s", len(mapping), args.season)

    combined: List[Dict[str, Any]] = []
    for i, (team, url) in enumerate(mapping.items(), start=1):
        LOG.info("(%d/%d) %s", i, len(mapping), team)
        try:
            items = scrape_tm_team(
                url=url,
                team=team,
                season=args.season,
                arrivals_only=args.arrivals_only,
                departures_only=args.departures_only
            )
        except Exception as e:
            LOG.error("[ETL] Errore scraping %s: %s", team, e)
            items = []

        if not items:
            LOG.warning("[ETL] Nessun trasferimento trovato per %s", team)
        else:
            path = jsonl_path(out_dir, team, args.season)
            append_jsonl(path, items)
            LOG.info("[OUT] %s (righe=%d)", path, len(items))
            combined.extend(items)

        # delay tra richieste per non stressare TM
        time.sleep(max(0.2, args.delay))

    # Combined file (utile per audit)
    if combined:
        combo_path = out_dir / f"tm_transfers_SERIE_A_{args.season.replace('/','-')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        append_jsonl(combo_path, combined)
        LOG.info("[OUT] combined: %s (righe=%d)", combo_path, len(combined))

    # Aggiorna roster solo con ARRIVI
    if args.write_roster and combined:
        only_in = [x for x in combined if x.get("direction") == "in"]
        merge_into_roster(only_in, Path("./season_roster.json"))

    # Ingest in KB
    if args.ingest and combined:
        ingest_into_kb(combined)

    LOG.info("[ETL] Done. Squadre processate: %d — Trasferimenti totali: %d",
             len(mapping), len(combined))

if __name__ == "__main__":
    main()
