# web_fallback.py
# -*- coding: utf-8 -*-
import logging
from typing import List, Dict, Any
import os

import re
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("web_fallback_wiki")
logger.setLevel(logging.INFO)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FantaCalcio-AI Bot/1.0; +https://example.local)"
}

class WebFallbackWikipedia:
    def __init__(self, enabled: bool = False, lang: str = "it"):
        self.enabled = enabled
        self.lang = lang

    def fetch_recent_transfers(self, team: str) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []
        try:
            # Semplice euristica per pagina trasferimenti (IT Wikipedia)
            # Esempio: https://it.wikipedia.org/wiki/Calciomercato_2025
            # Pagine varie: preferiamo pagina squadra -> sezione "Rosa" o "Trasferimenti"
            url = f"https://{self.lang}.wikipedia.org/wiki/{team.replace(' ', '_')}"
            html = requests.get(url, headers=HEADERS, timeout=10).text
            soup = BeautifulSoup(html, "html.parser")

            # Cerca tabelle con testo "Acquisti" o "Trasferimenti" (questa parte è fragile per natura)
            transfers: List[Dict[str, Any]] = []
            tables = soup.find_all("table", {"class": "wikitable"})
            for tbl in tables:
                caption = tbl.find("caption")
                cap_text = (caption.get_text(strip=True).lower() if caption else "")
                if any(k in cap_text for k in ["acquisti", "trasferimenti in", "acquisti 20", "arrivi"]):
                    for tr in tbl.find_all("tr"):
                        cols = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
                        if len(cols) < 2:
                            continue
                        # euristica: [Data?, Giocatore, Ruolo?, Da, ...]
                        player = None
                        pos = None
                        from_team = None
                        date = None
                        for c in cols:
                            # estrai una data semplice
                            if re.search(r"\b20\d{2}\b", c):
                                date = re.search(r"\b20\d{2}\b", c).group(0)
                        # prova giocatore come prima cella “non data”
                        player = cols[0]
                        # heuristics
                        if not player or len(player) < 3:
                            continue
                        if len(cols) >= 3:
                            pos = cols[2]
                        if len(cols) >= 4:
                            from_team = cols[3]
                        transfers.append({
                            "player": player,
                            "position": pos,
                            "from": from_team,
                            "date": date
                        })
            return transfers
        except Exception as e:
            logger.warning(f"[Wiki] fallback error: {e}")
            return []
