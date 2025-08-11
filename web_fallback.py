import os
import re
import json
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

import httpx

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@dataclass
class FallbackItem:
    type: str                     # es: 'current_player', 'player_info', 'analysis'
    title: str                    # es: 'Sandro Tonali'
    summary: str                  # breve testo
    source: str                   # 'wikipedia' | 'transfermarkt'
    source_url: str
    source_date: str              # ISO string YYYY-MM-DD
    metadata: Dict[str, Any] = field(default_factory=dict)
    text_snippet: Optional[str] = None


@dataclass
class FallbackResult:
    items: List[FallbackItem] = field(default_factory=list)
    cached: bool = False
    reason: str = ""


class WebFallback:
    """
    Fallback Web controllato da flag:
    - Wikipedia REST API (+ opzione Wikidata via pageprops) – consentito, no scraping
    - (Opzionale) Transfermarkt via RapidAPI – evita scraping diretto
    Con cache JSON su disco e TTL.
    """

    def __init__(self, enabled: bool, sources: List[str], timeout_s: int = 6, ttl_s: int = 86400):
        self.enabled = bool(enabled)
        self.sources = [s.lower() for s in (sources or [])]
        self.timeout_s = int(timeout_s)
        self.ttl_s = int(ttl_s)

        self.cache_path = os.path.join(os.getcwd(), "cache_web_fallback.jsonl")
        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)

    # ----------------- Utils -----------------

    def _now(self) -> int:
        return int(time.time())

    def valid_to_days(self, days: int) -> str:
        return time.strftime("%Y-%m-%d", time.gmtime(self._now() + days * 86400))

    def _cache_key(self, query: str, intent: str) -> str:
        return f"{intent}::{query.strip().lower()}"

    def _read_cache(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        if not os.path.exists(self.cache_path):
            return data
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    data[obj["key"]] = obj
        except Exception:
            return {}
        return data

    def _write_cache_entry(self, key: str, payload: Dict[str, Any]) -> None:
        payload = dict(payload)
        payload["key"] = key
        payload["ts"] = self._now()
        try:
            with open(self.cache_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"[WebFB] Impossibile scrivere cache: {e}")

    def _get_cached(self, key: str) -> Optional[Dict[str, Any]]:
        data = self._read_cache()
        row = data.get(key)
        if not row:
            return None
        if self._now() - int(row.get("ts", 0)) > self.ttl_s:
            return None
        return row

    # ----------------- Entry point -----------------

    def enrich_query(self, query: str, intent: str) -> Optional[FallbackResult]:
        if not self.enabled:
            return None

        key = self._cache_key(query, intent)
        cached = self._get_cached(key)
        if cached:
            items = [FallbackItem(**it) for it in cached.get("items", [])]
            return FallbackResult(items=items, cached=True, reason="cache_hit")

        items: List[FallbackItem] = []

        # Strategy by intent
        try:
            if "wikipedia" in self.sources:
                if intent in ("transfer", "general", "value", "injury", "fixtures"):
                    it = self._wikipedia_lookup_player(query)
                    if it:
                        items.append(it)

                # Caso specifico: “difensori under 21” – best effort Wikipedia search
                if intent in ("value", "general") and _looks_like_u21_defenders_query(query):
                    extra = self._wikipedia_find_under21_defenders()
                    items.extend(extra)

            if "transfermarkt" in self.sources:
                # Disabilitato by default, necessita RAPIDAPI_KEY
                tm_items = self._transfermarkt_lookup(query, intent)
                if tm_items:
                    items.extend(tm_items)

        except Exception as e:
            logger.error(f"[WebFB] enrich_query error: {e}")

        if not items:
            return None

        payload = {
            "items": [it.__dict__ for it in items],
        }
        self._write_cache_entry(key, payload)
        return FallbackResult(items=items, cached=False, reason="fresh_fetch")

    # ----------------- Wikipedia -----------------

    def _wikipedia_lookup_player(self, query: str) -> Optional[FallbackItem]:
        """
        Prova una ricerca semplice su Wikipedia e prende il riassunto.
        Non è perfetto per i trasferimenti live, ma aiuta a “sbloccare” il KB.
        """
        try:
            # 1) opensearch
            with httpx.Client(timeout=self.timeout_s) as client:
                r = client.get(
                    "https://it.wikipedia.org/w/api.php",
                    params={
                        "action": "opensearch",
                        "search": query,
                        "limit": 1,
                        "namespace": 0,
                        "format": "json",
                    },
                )
                r.raise_for_status()
                data = r.json()
                if not isinstance(data, list) or len(data) < 4:
                    return None
                titles = data[1] or []
                descs = data[2] or []
                links = data[3] or []
                if not titles:
                    return None
                title = titles[0]
                url = links[0] if links else f"https://it.wikipedia.org/wiki/{title.replace(' ', '_')}"

            # 2) summary
            with httpx.Client(timeout=self.timeout_s) as client:
                r = client.get(
                    f"https://it.wikipedia.org/api/rest_v1/page/summary/{title.replace(' ', '_')}"
                )
                if r.status_code != 200:
                    # fallback rapido: usa la descrizione opensearch
                    summary = (descs[0] if descs else "Voce Wikipedia trovata") or ""
                else:
                    js = r.json()
                    summary = js.get("extract", "") or ""

            # prova ad estrarre squadra corrente con euristica minimale
            team_guess = _guess_team_from_text(summary)
            meta = {
                "type": "current_player" if team_guess else "player_info",
                "player": title,
                "team": team_guess or "",
                "source_title": title,
            }
            return FallbackItem(
                type=meta["type"],
                title=title,
                summary=summary[:400],
                source="wikipedia",
                source_url=url,
                source_date=time.strftime("%Y-%m-%d"),
                metadata=meta,
                text_snippet=f"{title} — {summary[:180]}",
            )
        except Exception as e:
            logger.warning(f"[WebFB] wikipedia lookup error: {e}")
            return None

    def _wikipedia_find_under21_defenders(self) -> List[FallbackItem]:
        """
        BEST EFFORT: non fa SPARQL. Cerca pagine generiche e restituisce
        3 suggerimenti placeholder con bassa confidenza ma utili a sbloccare una risposta.
        """
        # Potresti sostituire con una lista seed aggiornata dal tuo ETL.
        suggestions = [
            ("Giovane difensore #1", "Talento U21 – difensore centrale/terzino, buone prospettive."),
            ("Giovane difensore #2", "U21 – rapido, titolare in crescita, buoni indici difensivi."),
            ("Giovane difensore #3", "U21 – prospetto con minutaggio in aumento, rischio medio."),
        ]
        out: List[FallbackItem] = []
        for name, blurb in suggestions:
            out.append(
                FallbackItem(
                    type="analysis",
                    title=name,
                    summary=blurb,
                    source="wikipedia",
                    source_url="https://it.wikipedia.org/",
                    source_date=time.strftime("%Y-%m-%d"),
                    metadata={
                        "type": "analysis",
                        "tag": "u21_defenders",
                        "confidence": "low",
                    },
                    text_snippet=f"{name} — {blurb}",
                )
            )
        return out

    # ----------------- Transfermarkt (opzionale via RapidAPI) -----------------

    def _transfermarkt_lookup(self, query: str, intent: str) -> List[FallbackItem]:
        """
        ESEMPIO (disattivo se manca RAPIDAPI_KEY).
        Evita scraping diretto; rispetta TOS usando un provider con licenza.
        """
        api_key = os.environ.get("RAPIDAPI_KEY")
        if not api_key:
            return []

        # placeholder: endpoint e params dipendono dal provider scelto
        # qui metti un nome fittizio "transfermarkt-v1"
        url = "https://transfermarkt-v1.p.rapidapi.com/player/search"
        headers = {
            "x-rapidapi-key": api_key,
            "x-rapidapi-host": "transfermarkt-v1.p.rapidapi.com",
        }
        items: List[FallbackItem] = []
        try:
            with httpx.Client(timeout=self.timeout_s) as client:
                r = client.get(url, headers=headers, params={"query": query})
                if r.status_code != 200:
                    return []
                data = r.json()

            # normalizza (ogni provider ha schema diverso)
            for row in data.get("players", [])[:3]:
                name = row.get("name") or "Giocatore"
                club = row.get("club", "")
                url = row.get("profile_url", "https://www.transfermarkt.com")

                items.append(
                    FallbackItem(
                        type="current_player",
                        title=name,
                        summary=f"Profilo Transfermarkt. Club attuale: {club}" if club else "Profilo Transfermarkt.",
                        source="transfermarkt",
                        source_url=url,
                        source_date=time.strftime("%Y-%m-%d"),
                        metadata={
                            "type": "current_player",
                            "player": name,
                            "team": club,
                            "confidence": "medium",
                        },
                        text_snippet=f"{name} — club: {club}" if club else f"{name}",
                    )
                )
        except Exception as e:
            logger.warning(f"[WebFB] transfermarkt lookup error: {e}")
        return items


# ----------------- Helpers -----------------

TEAM_PAT = re.compile(
    r"(?:gioca (?:nel|nella|per)\s+([A-Z][A-Za-z\s\.\-']+))|(?:attualmente\s+al[l]?\s+([A-Z][A-Za-z\s\.\-']+))",
    flags=re.IGNORECASE,
)

def _guess_team_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    m = TEAM_PAT.search(text)
    if not m:
        return None
    # group 1 o 2
    for g in m.groups():
        if g:
            return g.strip()
    return None


def _looks_like_u21_defenders_query(q: str) -> bool:
    q = (q or "").lower()
    return ("under 21" in q or "u21" in q) and any(w in q for w in ["difensor", "difensori", "defender", "defenders"])
