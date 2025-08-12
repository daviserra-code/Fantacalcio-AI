# web_fallback_tm.py
# -*- coding: utf-8 -*-
import logging
from typing import List, Dict, Any
import requests
from bs4 import BeautifulSoup
import re

logger = logging.getLogger("web_fallback_tm")
logger.setLevel(logging.INFO)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FantaCalcio-AI Bot/1.0; +https://example.local)"
}

TEAM_PAGES = {
    # Aggiungi mapping quando serve (nome → slug TM)
    "Genoa": "https://www.transfermarkt.it/genoa-cfc/transfers/verein/252/saison_id/2025",
    "Inter": "https://www.transfermarkt.it/fc-internazionale/transfers/verein/46/saison_id/2025",
    "Juventus": "https://www.transfermarkt.it/juventus-fc/transfers/verein/506/saison_id/2025",
    "Milan": "https://www.transfermarkt.it/ac-milan/transfers/verein/5/saison_id/2025",
    # ...
}

class WebFallbackTransfermarkt:
    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    def fetch_recent_transfers(self, team: str) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []
        url = TEAM_PAGES.get(team)
        if not url:
            # tentativo euristico minimo: costruisci URL base (potrebbe non funzionare per tutti i club)
            url = f"https://www.transfermarkt.it/schnellsuche/ergebnis/schnellsuche?query={team}"
        try:
            html = requests.get(url, headers=HEADERS, timeout=10).text
            soup = BeautifulSoup(html, "html.parser")
            # Cerca box “Acquisti” (entrate)
            transfers: List[Dict[str, Any]] = []
            tables = soup.find_all("table")
            for tbl in tables:
                # Heuristica: righe tabellari con nome, da squadra, data…
                for tr in tbl.find_all("tr"):
                    tds = tr.find_all("td")
                    if len(tds) < 5:
                        continue
                    text_cells = [td.get_text(" ", strip=True) for td in tds]
                    joined = " | ".join(text_cells).lower()
                    if any(k in joined for k in ["arrivo", "entrata", "in:", "acquisto"]):
                        # prova a estrarre giocatore nella prima/seconda colonna
                        player = text_cells[0] if len(text_cells[0]) > 2 else text_cells[1]
                        # da
                        from_team = None
                        for cell in text_cells:
                            if "da:" in cell.lower():
                                from_team = cell.split(":", 1)[-1].strip()
                                break
                        date = None
                        for cell in text_cells:
                            m = re.search(r"\b\d{1,2}\.\d{1,2}\.\d{4}\b", cell)
                            if m:
                                date = m.group(0)
                                break
                        transfers.append({
                            "player": player,
                            "position": None,
                            "from": from_team,
                            "date": date
                        })
            return transfers
        except Exception as e:
            logger.warning(f"[TM] fallback error: {e}")
            return []
