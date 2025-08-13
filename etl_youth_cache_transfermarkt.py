# etl_youth_cache_transfermarkt.py
# -*- coding: utf-8 -*-

import os
import re
import json
import time
import httpx
import logging
from datetime import datetime
from typing import Dict, List, Optional

LOG = logging.getLogger("etl_youth_cache")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

WIKI_API = "https://it.wikipedia.org/w/api.php"
OUT_PATH = os.getenv("EXTERNAL_YOUTH_CACHE", "./cache/under21_cache.json")
REF_DATE = datetime(2025, 8, 1)

SERIE_A_TEAMS = [
    "Atalanta", "Bologna", "Cagliari", "Como", "Empoli", "Fiorentina",
    "Genoa", "Inter", "Juventus", "Lazio", "Lecce", "Milan",
    "Monza", "Napoli", "Parma", "Roma", "Torino", "Udinese"
]

HEADERS = {
    "User-Agent": "FantacalcioAssistant/1.1 (ETL cache U21; mailto:example@example.com)"
}

ITALIAN_MONTHS = {
    "gennaio","febbraio","marzo","aprile","maggio","giugno",
    "luglio","agosto","settembre","ottobre","novembre","dicembre"
}

try:
    from bs4 import BeautifulSoup  # type: ignore
    HAVE_BS4 = True
except Exception:
    HAVE_BS4 = False


def _age_from_text_date(s: str) -> Optional[int]:
    s = s.strip()
    # YYYY-MM-DD
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        y = int(m.group(1))
        if 1900 < y <= REF_DATE.year:
            return REF_DATE.year - y
    # DD/MM/YYYY
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        y = int(m.group(3))
        if 1900 < y <= REF_DATE.year:
            return REF_DATE.year - y
    # YYYY
    m = re.search(r"\b(19\d{2}|20\d{2})\b", s)
    if m:
        y = int(m.group(1))
        if 1900 < y <= REF_DATE.year:
            return REF_DATE.year - y
    return None


def _looks_like_calendar_row(text: str) -> bool:
    low = text.lower()
    if "giornata" in low or "classifica" in low or "calendario" in low:
        return True
    if "ore" in low or "cet" in low or "cest" in low:
        return True
    if any(m in low for m in ITALIAN_MONTHS):
        return True
    # tante cifre spesso indicano data/orari/punteggi
    if sum(ch.isdigit() for ch in low) >= 4:
        return True
    return False


def wiki_search_team_page(client: httpx.Client, team: str) -> Optional[str]:
    for season in ("2025-2026", "2024-2025"):
        q = f"{team} {season}"
        try:
            r = client.get(WIKI_API, params={
                "action": "query", "list": "search", "srsearch": q,
                "format": "json", "srlimit": 5
            }, headers=HEADERS, timeout=30.0)
            r.raise_for_status()
            js = r.json()
            hits = js.get("query", {}).get("search", [])
            for h in hits:
                title = h.get("title")
                # preferisci pagina che contiene il team e la stagione
                if title and team.lower() in title.lower():
                    return title
        except Exception as e:
            LOG.warning("[WIKI] search error for %s: %s", q, e)
            time.sleep(1.0)
    return None


def wiki_parse_players_with_bs4(html: str, team_title: str) -> List[Dict]:
    out: List[Dict] = []
    soup = BeautifulSoup(html, "html.parser")

    # prendi solo tabelle con classe wikitable (tipico per rosa)
    tables = soup.find_all("table", class_="wikitable")
    for tbl in tables:
        # skip se la tabella sembra calendario/risultati
        header_text = " ".join(th.get_text(" ", strip=True) for th in tbl.find_all("th"))
        if _looks_like_calendar_row(header_text):
            continue

        # cerco header che abbiano 'Nome'/'Giocatore'/'Calciatore' o 'Ruolo'
        header_ok = any(
            k in header_text.lower()
            for k in ["nome", "giocatore", "calciatore", "ruolo", "posizione", "nascita", "data di nascita"]
        )
        if not header_ok:
            continue

        for tr in tbl.find_all("tr"):
            tds = tr.find_all(["td"])
            ths = tr.find_all(["th"])
            if not tds or ths and not tds:
                continue
            row_text = tr.get_text(" ", strip=True)
            if _looks_like_calendar_row(row_text):
                continue

            # euristica: prima cella = nome
            name = tds[0].get_text(" ", strip=True) if tds else ""
            # pulizia nome: via parentesi finali
            name = re.sub(r"\s*\(.*?\)\s*$", "", name).strip()

            if not name or any(ch.isdigit() for ch in name):
                continue
            if any(m in name.lower() for m in ITALIAN_MONTHS):
                continue
            if len(name) < 2:
                continue

            # ruolo: prova cella successiva o cerca nel resto
            role = ""
            if len(tds) >= 2:
                role = tds[1].get_text(" ", strip=True).upper()

            # data di nascita in riga
            age = _age_from_text_date(row_text)
            if age is None or age < 15 or age > 22:
                continue

            # mapping ruolo
            rb = "A"
            R = role.upper()
            if R.startswith(("P", "POR", "GK")):
                rb = "P"
            elif any(x in R for x in ["D", "DEF", "CB", "RB", "LB", "TD", "TS"]):
                rb = "D"
            elif any(x in R for x in ["C", "CM", "MED", "MEZ", "AM", "TQ", "M "]):
                rb = "C"

            out.append({
                "name": name,
                "team": team_title.split(" 20")[0],
                "role": rb,
                "age": age
            })
    return out


def wiki_parse_players_regex(html: str, team_title: str) -> List[Dict]:
    out: List[Dict] = []
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S | re.I)
    for row in rows:
        # scarta righe da calendario
        row_text = re.sub(r"<[^>]+>", " ", row)
        row_text = re.sub(r"\s+", " ", row_text).strip()
        if _looks_like_calendar_row(row_text):
            continue

        cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, flags=re.S | re.I)
        if len(cells) < 2:
            continue

        def strip_html(s: str) -> str:
            s = re.sub(r"<[^>]+>", " ", s)
            s = re.sub(r"\s+", " ", s)
            return s.strip()

        name = strip_html(cells[0])
        name = re.sub(r"\s*\(.*?\)\s*$", "", name).strip()
        if not name or any(ch.isdigit() for ch in name):
            continue
        if any(m in name.lower() for m in ITALIAN_MONTHS):
            continue

        role = strip_html(cells[1]).upper() if len(cells) >= 2 else ""
        age = _age_from_text_date(row_text)
        if age is None or age < 15 or age > 22:
            continue

        rb = "A"
        R = role.upper()
        if R.startswith(("P", "POR", "GK")):
            rb = "P"
        elif any(x in R for x in ["D", "DEF", "CB", "RB", "LB", "TD", "TS"]):
            rb = "D"
        elif any(x in R for x in ["C", "CM", "MED", "MEZ", "AM", "TQ", "M "]):
            rb = "C"

        out.append({
            "name": name,
            "team": team_title.split(" 20")[0],
            "role": rb,
            "age": age
        })
    return out


def main():
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    results: List[Dict] = []

    with httpx.Client(follow_redirects=True, headers=HEADERS, timeout=30.0) as client:
        for team in SERIE_A_TEAMS:
            LOG.info("[ETL-YOUTH] Cerco pagina Wiki per %s", team)
            title = wiki_search_team_page(client, team)
            if not title:
                LOG.warning("[ETL-YOUTH] Nessuna pagina trovata per %s", team)
                continue

            # Carica HTML
            try:
                r = client.get(WIKI_API, params={
                    "action": "parse", "page": title, "prop": "text", "format": "json"
                })
                r.raise_for_status()
                html = r.json().get("parse", {}).get("text", {}).get("*", "")
            except Exception as e:
                LOG.warning("[WIKI] parse error for %s: %s", title, e)
                continue

            if not html:
                continue

            players = wiki_parse_players_with_bs4(html, title) if HAVE_BS4 else wiki_parse_players_regex(html, title)
            LOG.info("[ETL-YOUTH] %s: estratti %d", team, len(players))
            results.extend(players)
            time.sleep(0.6)

    # dedup per nome+team, tieni età minore (più “giovane”)
    dedup: Dict[str, Dict] = {}
    for r in results:
        key = (r["name"].lower() + "|" + r["team"].lower())
        if key in dedup:
            if r["age"] < dedup[key]["age"]:
                dedup[key] = r
        else:
            dedup[key] = r

    final = list(dedup.values())

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)

    LOG.info("[ETL-YOUTH] Salvato %s con %d record", OUT_PATH, len(final))


if __name__ == "__main__":
    main()
