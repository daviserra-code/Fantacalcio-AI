import re
import time
import logging
from typing import List, Dict, Optional
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

WIKI_MARKET_IT_2025 = "https://it.wikipedia.org/wiki/Calciomercato_estivo_2025_(Italia)"
WIKI_GENOA_IT = "https://it.wikipedia.org/wiki/Genoa_Cricket_and_Football_Club"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FantaCalcioAssistant/1.0; +https://example.local)"
}

class WebFallback:
    """
    Fallback minimale: prova a recuperare 'acquisti' da Wikipedia IT.
    - Prima tenta la pagina 'Calciomercato_estivo_2025_(Italia)' → sezione 'Genoa'
    - Se fallisce, tenta la pagina del club
    Ritorna: list di dict {player, role?, source, source_date?}
    """

    def __init__(self, timeout_s: float = 6.5):
        self.timeout = timeout_s

    def _fetch_html(self, url: str) -> Optional[str]:
        try:
            with httpx.Client(timeout=self.timeout, headers=HEADERS, follow_redirects=True) as client:
                resp = client.get(url)
                if resp.status_code == 200 and resp.text:
                    return resp.text
                logger.warning("[WebFallback] HTTP %s per %s", resp.status_code, url)
                return None
        except Exception as e:
            logger.warning("[WebFallback] Fetch error %s: %s", url, e)
            return None

    def _extract_players_from_market_page(self, html: str, team_name: str) -> List[str]:
        """
        Dalla pagina 'Calciomercato_estivo_2025_(Italia)' prova a trovare l'anchor 'Genoa'
        o un H2/H3 con il nome squadra e leggere la tabella/elenco immediatamente sotto.
        """
        soup = BeautifulSoup(html, "html.parser")
        players: List[str] = []

        # Cerca un heading con "Genoa" (o team_name generico)
        headings = soup.select("h2, h3")
        target_idx = -1
        for idx, h in enumerate(headings):
            text = (h.get_text(" ", strip=True) or "").lower()
            if team_name.lower() in text:
                target_idx = idx
                break

        if target_idx == -1:
            return players

        # Prendi elementi fino al prossimo heading di stesso livello o superiore
        section_nodes = []
        for node in headings[target_idx].next_siblings:
            if getattr(node, "name", None) in ("h2", "h3"):
                break
            section_nodes.append(node)

        # Cerca tabelle o liste
        # Pattern molto semplice: cerca link con testo “Acquisti” e poi lista
        section_html = BeautifulSoup("".join(str(n) for n in section_nodes), "html.parser")

        # Se c'è una tabella, prendi nomi nella prima colonna plausibile
        for table in section_html.select("table"):
            for row in table.select("tr"):
                cols = [c.get_text(" ", strip=True) for c in row.select("td, th")]
                if not cols:
                    continue
                # Heuristics: un nome ha almeno uno spazio (Nome Cognome)
                guess = cols[0]
                if guess and len(guess.split()) >= 2 and len(guess) <= 60:
                    # evita righe di header tipo "Acquisti"
                    if not re.search(r"acquisti|cessioni|rosa|totale", guess, re.IGNORECASE):
                        players.append(guess)

        # Se non ha trovato nulla, prova con liste puntate
        if not players:
            for li in section_html.select("ul li"):
                txt = li.get_text(" ", strip=True)
                # heuristics: inizia con un nome (cap letter) e non è una frase lunga
                if txt and len(txt.split()) <= 8 and re.search(r"[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ]+ [A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ]+", txt):
                    players.append(txt)

        # Dedup e pulizia rapida
        cleaned = []
        seen = set()
        for p in players:
            p = re.sub(r"\s*\(.*?\)\s*$", "", p).strip("•-—:;., ").strip()
            if p and p.lower() not in seen:
                seen.add(p.lower())
                cleaned.append(p)
        return cleaned[:12]

    def _extract_players_from_club_page(self, html: str) -> List[str]:
        """
        Dalla pagina del club prova a trovare 'rosa 2025-26' o una tabella trasferimenti recente.
        Molto best-effort.
        """
        soup = BeautifulSoup(html, "html.parser")
        players: List[str] = []

        # Cerca box "Rosa", prendi i nomi dalle liste o tabelle
        # (non sempre c'è una sezione chiara per acquisti; meglio avere un fallback generico)
        for table in soup.select("table"):
            headers = " ".join(h.get_text(" ", strip=True).lower() for h in table.select("th"))
            # Se la tabella sembra di rosa / giocatori:
            if re.search(r"giocatori|rosa|calciatori|squadra", headers):
                for row in table.select("tr"):
                    cells = [c.get_text(" ", strip=True) for c in row.select("td")]
                    if not cells:
                        continue
                    # prendi la cella con un nome plausibile
                    for c in cells[:2]:
                        if re.search(r"[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ]+ [A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ]+", c):
                            players.append(c)
                            break

        cleaned = []
        seen = set()
        for p in players:
            p = re.sub(r"\s*\(.*?\)\s*$", "", p).strip("•-—:;., ").strip()
            if p and p.lower() not in seen:
                seen.add(p.lower())
                cleaned.append(p)
        return cleaned[:12]

    def fetch_team_transfers(self, team_name: str) -> Dict[str, any]:
        """
        Ritorna un dict:
        {
          "team": "Genoa",
          "acquisti": ["Nome1", "Nome2", ...]  # best-effort
          "sources": [url1, url2]
        }
        """
        t0 = time.time()
        sources = []
        acquisti: List[str] = []

        # 1) Prova pagina mercato estivo 2025
        html = self._fetch_html(WIKI_MARKET_IT_2025)
        if html:
            sources.append(WIKI_MARKET_IT_2025)
            try:
                found = self._extract_players_from_market_page(html, team_name)
                if found:
                    acquisti.extend(found)
            except Exception as e:
                logger.warning("[WebFallback] parse market page error: %s", e)

        # 2) Se non hai trovato niente di credibile, prova pagina club
        if len(acquisti) < 2:
            html2 = self._fetch_html(WIKI_GENOA_IT if team_name.lower().startswith("genoa") else None or WIKI_GENOA_IT)
            if html2:
                sources.append(WIKI_GENOA_IT)
                try:
                    found2 = self._extract_players_from_club_page(html2)
                    # non sono acquisti, ma se incrociamo con mercato potrebbe aiutare
                    # teniamo solo i primi 3 come “possibili arrivi recenti” (best effort)
                    if found2:
                        # preferisci nomi non già in lista
                        for n in found2:
                            if n not in acquisti:
                                acquisti.append(n)
                except Exception as e:
                    logger.warning("[WebFallback] parse club page error: %s", e)

        return {
            "team": team_name,
            "acquisti": acquisti[:6],
            "sources": sources,
            "elapsed": round(time.time() - t0, 2),
        }
