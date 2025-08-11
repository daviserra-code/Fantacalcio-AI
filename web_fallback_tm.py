# -*- coding: utf-8 -*-
"""
web_fallback_tm.py
Fallback (OPZIONALE) per Transfermarkt — BEST EFFORT.

⚠️ IMPORTANTISSIMO
- Transfermarkt può vietare lo scraping automatizzato; questo modulo è DISABILITATO di default.
- Abilitalo SOLO impostando TRANSFERMARKT_FALLBACK=1 (env) e con frequenze/rate limit bassi.
- Rispetta robots.txt e le loro ToS. Usa preferibilmente fonti ufficiali/RSS o API legittime.

Funzione principale: TransfermarktFallback.fetch_team_transfers(team_name, season)
Ritorna: {"team":..., "acquisti":[...], "sources":[...], "elapsed": seconds}
"""

import re
import time
import logging
from typing import Dict, Any, List, Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FantaCalcioAssistant/1.0; +https://example.local)"
}

# Mapping (parziale) Serie A → slug + id Transfermarkt
# Puoi completarlo/aggiornarlo. L'ID ufficiale è più stabile dello slug.
TEAM_TM = {
    "Genoa": {"slug": "genoa-cfc", "id": 252},
    "Inter": {"slug": "inter-mailand", "id": 46},
    "Milan": {"slug": "ac-mailand", "id": 5},
    "Juventus": {"slug": "juventus-turin", "id": 506},
    "Napoli": {"slug": "ssc-neapel", "id": 6195},
    "Roma": {"slug": "as-rom", "id": 12},
    "Lazio": {"slug": "lazio-rom", "id": 398},
    "Atalanta": {"slug": "atalanta-bergamo", "id": 800},
    "Fiorentina": {"slug": "ac-florenz", "id": 430},
    "Bologna": {"slug": "bologna-fc-1909", "id": 1025},
    "Udinese": {"slug": "udinese-calcio", "id": 410},
    "Torino": {"slug": "fc-turin", "id": 416},
    "Lecce": {"slug": "us-lecce", "id": 8005},
    "Monza": {"slug": "ac-monza", "id": 2917},
    "Empoli": {"slug": "fc-empoli", "id": 749},
    "Cagliari": {"slug": "cagliari-calcio", "id": 1390},
    "Parma": {"slug": "parma-calcio-1913", "id": 130},
    "Venezia": {"slug": "fc-venedig", "id": 3439},
    "Hellas Verona": {"slug": "hellas-verona", "id": 276},
    "Como": {"slug": "como-1907", "id": 183},
}

def _build_url(team_name: str, season: str) -> Optional[str]:
    """
    Esempio URL (estate 2025):
    https://www.transfermarkt.it/genoa-cfc/transfers/verein/252/saison_id/2025/transferfenster/sommer/plus/0
    """
    info = TEAM_TM.get(team_name)
    if not info:
        return None
    # Estrai anno iniziale da "2025-26" → 2025
    m = re.search(r"(\d{4})", season)
    year = m.group(1) if m else "2025"
    return f"https://www.transfermarkt.it/{info['slug']}/transfers/verein/{info['id']}/saison_id/{year}/transferfenster/sommer/plus/0"

def _fetch_html(url: str, timeout_s: float = 7.5) -> Optional[str]:
    try:
        with httpx.Client(timeout=timeout_s, headers=HEADERS, follow_redirects=True) as client:
            r = client.get(url)
            if r.status_code == 200 and r.text:
                return r.text
            logger.warning("[TM] HTTP %s per %s", r.status_code, url)
            return None
    except Exception as e:
        logger.warning("[TM] Fetch error %s: %s", url, e)
        return None

def _extract_arrivals(html: str) -> List[str]:
    """
    Best-effort parsing: la pagina ha sezioni 'Arrivi' (estate) con tabelle.
    Cerchiamo righe con nomi plausibili nella prima o seconda colonna.
    """
    soup = BeautifulSoup(html, "html.parser")
    players: List[str] = []

    # Heuristics: trova heading 'Arrivi' (IT) o 'Zugänge' (DE) o 'Arrivals' (EN)
    headings = soup.find_all(["h2", "h3"])
    start = None
    for h in headings:
        t = (h.get_text(" ", strip=True) or "").lower()
        if any(k in t for k in ["arrivi", "zugänge", "arrivals"]):
            start = h
            break

    section_nodes = []
    if start is not None:
        for node in start.next_siblings:
            if getattr(node, "name", None) in ("h2", "h3"):
                break
            section_nodes.append(node)
    else:
        # fallback: prendi tutte le tabelle e prova
        section_nodes = soup.find_all("table")

    section = BeautifulSoup("".join(str(n) for n in section_nodes), "html.parser")

    for row in section.select("table tr"):
        cols = row.find_all("td")
        if not cols:
            continue
        # prova a prendere un <a> con link al profilo giocatore
        name = None
        for a in row.select("a"):
            txt = (a.get_text(" ", strip=True) or "").strip()
            if txt and len(txt.split()) >= 2 and len(txt) < 60:
                # filtra rumor tipo "Prestito", "Costo", ecc.
                if not re.search(r"(prezzo|costo|prestito|fine)", txt, re.IGNORECASE):
                    # Salta link a club/flag
                    href = a.get("href", "")
                    if "/profil/" in href or "/spieler/" in href or "/player/" in href:
                        name = txt
                        break
        if name:
            players.append(name)

    # Pulizia e dedup
    clean = []
    seen = set()
    for p in players:
        p = re.sub(r"\s*\(.*?\)\s*$", "", p).strip("•-—:;., ").strip()
        if p and p.lower() not in seen:
            seen.add(p.lower())
            clean.append(p)
    return clean[:12]

class TransfermarktFallback:
    def __init__(self, timeout_s: float = 7.5):
        self.timeout = timeout_s

    def fetch_team_transfers(self, team_name: str, season: str) -> Dict[str, Any]:
        t0 = time.time()
        url = _build_url(team_name, season)
        if not url:
            return {"team": team_name, "acquisti": [], "sources": [], "elapsed": 0.0}

        html = _fetch_html(url, timeout_s=self.timeout)
        if not html:
            return {"team": team_name, "acquisti": [], "sources": [url], "elapsed": round(time.time() - t0, 2)}

        players = _extract_arrivals(html)
        return {
            "team": team_name,
            "acquisti": players,
            "sources": [url],
            "elapsed": round(time.time() - t0, 2),
        }
