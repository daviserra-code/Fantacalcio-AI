import os
import sys
import json
import time
import argparse
import sqlite3
from typing import List, Dict, Optional

import requests

# -------------------- Config di base --------------------
USER_AGENT = os.environ.get("USER_AGENT", "FantacalcioETL/1.0 (replit)")
SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
WIKIDATA_SEARCH = "https://www.wikidata.org/w/api.php"
DB_PATH = os.environ.get("ETL_DB", "./fantacalcio.db")

# KnowledgeManager (opzionale per Chroma)
try:
    from knowledge_manager import KnowledgeManager
except Exception:
    KnowledgeManager = None  # permette --no-chroma

# -------------------- Sanitizzazione metadati (per Chroma) --------------------
def _sanitize_meta(meta: dict) -> dict:
    """Rimuove tipi non primitivi e converte None -> '' per compatibilita' Chroma."""
    out = {}
    for k, v in (meta or {}).items():
        if v is None:
            out[k] = ""
        elif isinstance(v, (str, int, float, bool)):
            out[k] = v
        else:
            out[k] = str(v)
    return out

# -------------------- Helper HTTP/SPARQL/Wikidata --------------------
def wbsearchentities(name: str, lang: str = "it", type_hint: Optional[str] = None) -> Optional[Dict]:
    """Cerca entita' su Wikidata. Ritorna {'id','label'} o None."""
    params = {
        "action": "wbsearchentities",
        "search": name,
        "language": lang,
        "uselang": lang,
        "format": "json",
        "limit": 10,
        "type": type_hint or "item",
    }
    r = requests.get(WIKIDATA_SEARCH, params=params, headers={"User-Agent": USER_AGENT}, timeout=12)
    r.raise_for_status()
    data = r.json()
    res = data.get("search", [])
    if not res:
        return None

    def score(item):
        desc = (item.get("description") or "").lower()
        s = 0
        if "football" in desc or "calcio" in desc or "club" in desc or "societa" in desc or "società" in desc:
            s += 10
        if "club" in desc and "football" in desc:
            s += 5
        return s

    res.sort(key=score, reverse=True)
    top = res[0]
    return {"id": top.get("id"), "label": top.get("label")}

def sparql_select(query: str) -> List[Dict]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/sparql-results+json",
    }
    r = requests.get(SPARQL_ENDPOINT, params={"query": query, "format": "json"}, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data.get("results", {}).get("bindings", [])

def fetch_current_roster(club_qid: str, lang: str = "it") -> List[Dict]:
    """
    Rosa attuale: giocatori con P54 = club e SENZA qualifier P582 (end time).
    Ritorna dict con player_qid, player_label, wiki_page (it se disponibile), position.
    """
    query = f"""
    SELECT ?player ?playerLabel ?wpPage ?positionLabel WHERE {{
      BIND(wd:{club_qid} AS ?club)
      ?player p:P54 ?st .
      ?st ps:P54 ?club .
      FILTER NOT EXISTS {{ ?st pq:P582 ?end . }}

      OPTIONAL {{ ?player wdt:P413 ?position . }}

      OPTIONAL {{
        ?wpPage schema:about ?player ;
                schema:isPartOf <https://{lang}.wikipedia.org/> .
      }}

      SERVICE wikibase:label {{
        bd:serviceParam wikibase:language "{lang},en" .
        ?player rdfs:label ?playerLabel .
      }}
    }}
    """
    rows = sparql_select(query)
    out = []
    for b in rows:
        def val(x): return b.get(x, {}).get("value")
        out.append({
            "player_qid": (val("player").split("/")[-1]) if val("player") else None,
            "player_label": val("playerLabel"),
            "wiki_page": val("wpPage"),
            "position": val("positionLabel"),
        })
    # dedup per player_qid/label
    seen, uniq = set(), []
    for r in out:
        key = r.get("player_qid") or r.get("player_label")
        if key and key not in seen:
            seen.add(key)
            uniq.append(r)
    return uniq

# -------------------- SQLite schema & upsert --------------------
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS clubs (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  wikidata_id TEXT,
  country TEXT
);

CREATE TABLE IF NOT EXISTS players (
  id TEXT PRIMARY KEY,
  full_name TEXT NOT NULL,
  wikidata_id TEXT,
  position TEXT
);

CREATE TABLE IF NOT EXISTS memberships (
  player_id TEXT NOT NULL,
  club_id TEXT NOT NULL,
  start_date TEXT,
  end_date TEXT,
  source_url TEXT,
  source_date TEXT,
  PRIMARY KEY (player_id, club_id, start_date),
  FOREIGN KEY (player_id) REFERENCES players(id),
  FOREIGN KEY (club_id) REFERENCES clubs(id)
);
"""

def ensure_db(conn: sqlite3.Connection):
    conn.executescript(SCHEMA_SQL)
    conn.commit()

def upsert_club(conn: sqlite3.Connection, club_id: str, name: str, wikidata_id: Optional[str]):
    conn.execute(
        "INSERT INTO clubs(id, name, wikidata_id) VALUES(?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET name=excluded.name, wikidata_id=excluded.wikidata_id",
        (club_id, name, wikidata_id)
    )
    conn.commit()

def upsert_player(conn: sqlite3.Connection, pid: str, full_name: str, wikidata_id: Optional[str], position: Optional[str]):
    conn.execute(
        "INSERT INTO players(id, full_name, wikidata_id, position) VALUES(?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET full_name=excluded.full_name, wikidata_id=excluded.wikidata_id, position=excluded.position",
        (pid, full_name, wikidata_id, position)
    )

def upsert_membership(conn: sqlite3.Connection, pid: str, cid: str, start_date: Optional[str], source_url: Optional[str], source_date: Optional[str]):
    conn.execute(
        "INSERT OR REPLACE INTO memberships(player_id, club_id, start_date, end_date, source_url, source_date) VALUES(?,?,?,?,?,?)",
        (pid, cid, start_date or "0000-00-00", None, source_url, source_date)
    )

# -------------------- Helpers vari --------------------
def normalize_id(label: str) -> str:
    return (
        label.lower()
        .replace(" ", "_")
        .replace("'", "")
        .replace(".", "")
        .replace("-", "_")
        .replace("/", "_")
    )

# -------------------- ETL per SQUADRA (inline) --------------------
def ingest_team(team_name: str, season: str, valid_to: str, lang: str = "it", no_chroma: bool = False) -> Dict:
    # 1) risolvi club su Wikidata
    club = wbsearchentities(team_name, lang=lang, type_hint="item")
    if not club:
        raise RuntimeError(f"Club non trovato su Wikidata: {team_name}")

    club_qid = club["id"]
    club_label = club["label"] or team_name
    club_row_id = f"club_{normalize_id(club_label)}"

    # 2) roster attuale
    roster = fetch_current_roster(club_qid, lang=lang)

    # 3) scrivi su SQLite
    conn = sqlite3.connect(DB_PATH)
    ensure_db(conn)
    upsert_club(conn, club_row_id, club_label, club_qid)

    now = time.strftime("%Y-%m-%d")
    for r in roster:
        name = r.get("player_label") or "Giocatore"
        pid = f"pl_{normalize_id(name)}"
        upsert_player(conn, pid, name, r.get("player_qid"), r.get("position"))
        upsert_membership(conn, pid, club_row_id, start_date=now, source_url=r.get("wiki_page"), source_date=now)
    conn.commit()

    # 4) indicizza in Chroma (facoltativo)
    added_docs = 0
    if not no_chroma and KnowledgeManager is not None:
        km = KnowledgeManager()
        items = []
        for r in roster:
            name = r.get("player_label") or "Giocatore"
            pid = f"pl_{normalize_id(name)}"
            text = f"{name} e' un calciatore del {club_label}."
            md = {
                "type": "player_info",
                "player": name or "",
                "player_id": pid,
                "team": club_label or "",
                "position": r.get("position") or "",
                "title": f"Profilo {name or ''}",
                "source": r.get("wiki_page") or (f"https://www.wikidata.org/wiki/{r.get('player_qid')}" if r.get("player_qid") else "internal://wikidata"),
                "date": now or "",
                "valid_to": valid_to or "2099-01-01",
                "season": season or "",
            }
            md = _sanitize_meta(md)
            items.append({"id": pid, "text": text, "metadata": md})

        stats = km.add_many(items)
        added_docs = stats.get("added", 0)

    return {
        "club_qid": club_qid,
        "club": club_label,
        "players": len(roster),
        "db_path": DB_PATH,
        "chroma_indexed": added_docs,
    }

# -------------------- Resolve LEAGUE & clubs --------------------
def resolve_league(league_name: str, lang: str = "it") -> Optional[Dict]:
    """Trova l'item Wikidata della lega (es. Serie A, Premier League)."""
    return wbsearchentities(league_name, lang=lang, type_hint="item")

def fetch_league_clubs(league_qid: str, lang: str = "it", country_hint: Optional[str] = None, limit: Optional[int] = None) -> List[Dict]:
    """
    Trova i club che militano nella lega: team con proprieta' wdt:P118 = wd:<league_qid>.
    Se country_hint e' valorizzato, prova a filtrare per P17 (paese).
    """
    country_filter = ""
    if country_hint:
        country_filter = f"""
        OPTIONAL {{ ?club wdt:P17 ?country . }}
        ?country rdfs:label ?countryLabel FILTER(LANG(?countryLabel)='{lang}' || LANG(?countryLabel)='en').
        FILTER(CONTAINS(LCASE(?countryLabel), LCASE("{country_hint}")))
        """

    limit_clause = f"LIMIT {int(limit)}" if limit and int(limit) > 0 else ""

    query = f"""
    SELECT DISTINCT ?club ?clubLabel WHERE {{
      ?club wdt:P118 wd:{league_qid} .
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{lang},en". }}
      {country_filter}
    }}
    {limit_clause}
    """
    rows = sparql_select(query)
    out = []
    for b in rows:
        uri = b.get("club", {}).get("value")
        label = b.get("clubLabel", {}).get("value")
        if not uri or not label:
            continue
        qid = uri.split("/")[-1]
        out.append({"id": qid, "label": label})
    return out

# -------------------- MAIN --------------------
def main():
    ap = argparse.ArgumentParser(description="ETL batch per LEGA: risolve la lega su Wikidata e ingesta tutti i club della lega (SQLite + Chroma).")
    ap.add_argument("--league", required=True, help='Nome lega (es. "Serie A", "Premier League")')
    ap.add_argument("--season", default=os.environ.get("SEASON_DEFAULT", "2025-26"), help='Stagione nei metadati (es. "2025-26")')
    ap.add_argument("--valid-to", default="2099-01-01", help="Data validita' dei documenti (YYYY-MM-DD)")
    ap.add_argument("--lang", default="it", help="Lingua preferita (default: it)")
    ap.add_argument("--country", default=None, help='Hint paese per filtrare i club (es. "Italy", "England")')
    ap.add_argument("--limit", type=int, default=None, help="Limita il numero di club da processare (per test)")
    ap.add_argument("--no-chroma", action="store_true", help="Non indicizzare in Chroma (solo DB locale)")
    ap.add_argument("--sleep", type=float, default=1.0, help="Sleep tra club (secondi) per essere gentili con gli endpoint)")
    args = ap.parse_args()

    # 1) Risolvi la LEGA
    league = resolve_league(args.league, lang=args.lang)
    if not league:
        print(json.dumps({"ok": False, "error": f"Lega non trovata: {args.league}"}))
        sys.exit(1)

    league_qid = league["id"]
    league_label = league["label"]
    print(json.dumps({"ok": True, "league_qid": league_qid, "league": league_label}, ensure_ascii=False))

    # 2) Trova i club che militano nella lega
    try:
        clubs = fetch_league_clubs(league_qid, lang=args.lang, country_hint=args.country, limit=args.limit)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"Errore SPARQL club: {e}"}))
        sys.exit(2)

    if not clubs:
        print(json.dumps({"ok": False, "error": f"Nessun club trovato per la lega {league_label}"}))
        sys.exit(3)

    print(f"[ETL-LEAGUE] Club trovati: {len(clubs)}")

    results = []
    for i, c in enumerate(clubs, 1):
        name = c["label"]
        print(f"[{i}/{len(clubs)}] Ingest team: {name} ...")
        try:
            res = ingest_team(
                team_name=name,
                season=args.season,
                valid_to=args.valid_to,
                lang=args.lang,
                no_chroma=args.no_chroma,
            )
            results.append({"team": name, **res})
        except Exception as e:
            print(f"[ETL-LEAGUE] Errore ingest '{name}': {e}", file=sys.stderr)
        time.sleep(max(0.0, args.sleep))

    # 3) Report finale
    total_players = sum(r.get("players", 0) for r in results)
    total_indexed = sum(r.get("chroma_indexed", 0) for r in results)
    out = {
        "ok": True,
        "league": league_label,
        "teams_processed": len(results),
        "players_total": total_players,
        "chroma_indexed_total": total_indexed,
        "season": args.season,
        "valid_to": args.valid_to,
        "details": results[-5:],  # ultimi 5 per quick check
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()