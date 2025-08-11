import os
import re
import json
import time
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple

# OpenAI SDK v1+
try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # gestito più sotto

# Fallback HTTP client per web-scraping opzionale
import contextlib
import html
import traceback

try:
    import requests
    from bs4 import BeautifulSoup  # type: ignore
except Exception:
    requests = None
    BeautifulSoup = None

# Knowledge Manager (il tuo modulo)
from knowledge_manager import KnowledgeManager

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# -----------------------------
# Utility
# -----------------------------

def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")

def _safe_float(x, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default

def _str2date(s: str) -> Optional[datetime]:
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        with contextlib.suppress(Exception):
            return datetime.strptime(s, fmt)
    return None

def _is_stale(dt: Optional[datetime], max_days: int) -> bool:
    if not dt:
        return True
    return (datetime.now() - dt) > timedelta(days=max_days)

def _normalize_team_name(name: str) -> str:
    n = name.strip().lower()
    # mapping rapido
    aliases = {
        "genoa": "Genoa",
        "genoa cfc": "Genoa",
        "genoa cricket and football club": "Genoa",
        "inter": "Inter",
        "fc internazionale": "Inter",
        "juventus": "Juventus",
        "napoli": "Napoli",
        "milan": "Milan",
    }
    return aliases.get(n, name.strip().title())

def _intent_of(query: str) -> str:
    q = query.lower()
    if any(k in q for k in ["acquisti", "trasferiment", "mercato", "chi ha comprato", "ultimo acquisto", "nuovi arrivi"]):
        return "transfer"
    if any(k in q for k in ["infortun", "squalific", "rientro"]):
        return "injury"
    if any(k in q for k in ["asta", "conviene", "budget", "formazione", "strategie", "3-5-2", "4-3-3", "4-2-3-1", "3-4-1-2", "4-3-2-1", "4-2-2-2"]):
        return "value"
    if any(k in q for k in ["calendario", "prossime partite", "forma", "fixture"]):
        return "fixtures"
    return "generic"

# -----------------------------
# Fallback web (opzionale)
# -----------------------------

class WebFallback:
    """
    Fallback minimale per recuperare trasferimenti da fonti pubbliche.
    Di default è disabilitato (rispetta sito/robots di Transfermarkt).
    Attivalo con ENABLE_WEB_FALLBACK=1 e considera limiti/ToS.
    """

    def __init__(self, timeout: float = 6.0):
        self.enabled = os.environ.get("ENABLE_WEB_FALLBACK", "0") == "1"
        self.timeout = float(os.environ.get("WEB_FALLBACK_TIMEOUT", timeout))
        self.headers = {
            "User-Agent": "Mozilla/5.0 (compatible; FantacalcioAssistant/1.0; +https://example.local)"
        }

    def search_transfers(self, team: str) -> List[Dict[str, Any]]:
        """
        Restituisce lista di ultimi acquisti (best-effort).
        Se non disponibile o disabilitato → [].
        """
        if not self.enabled:
            logger.info("[WEB] Fallback disattivato (ENABLE_WEB_FALLBACK!=1)")
            return []

        if not requests or not BeautifulSoup:
            logger.warning("[WEB] requests/bs4 non disponibili nell'ambiente.")
            return []

        # Tentativo soft via Wikipedia IT: "Calciomercato [Team] 2025-26" o "Stagione ..."
        # NOTA: Wikipedia può avere formati variabili; questo è best-effort.
        team_norm = _normalize_team_name(team)
        candidates = [
            f"https://it.wikipedia.org/wiki/{team_norm.replace(' ', '_')}",
            f"https://it.wikipedia.org/wiki/{team_norm.replace(' ', '_')}_({datetime.now().year % 100:02d}-{(datetime.now().year+1) % 100:02d})",
            f"https://it.wikipedia.org/wiki/{team_norm.replace(' ', '_')}_Calciomercato",
        ]

        results: List[Dict[str, Any]] = []

        for url in candidates:
            try:
                r = requests.get(url, headers=self.headers, timeout=self.timeout)
                if r.status_code != 200 or not r.text:
                    continue
                soup = BeautifulSoup(r.text, "html.parser")
                # Heuristic: cerca sezioni "Acquisti", "Trasferimenti", tabelle giocatori
                sections = soup.find_all(["h2", "h3", "h4"])
                for h in sections:
                    title = (h.get_text() or "").lower()
                    if any(k in title for k in ["acquisti", "trasferimenti in entrata", "arrivi"]):
                        # Prendi la prossima lista/ul o tabella
                        nxt = h.find_next_sibling()
                        # iteriamo qualche sibling finché troviamo liste utili
                        hops = 0
                        while nxt is not None and hops < 4:
                            if nxt.name in ("ul", "ol"):
                                for li in nxt.find_all("li"):
                                    txt = " ".join(li.get_text(" ").split())
                                    if not txt:
                                        continue
                                    # Estrai nome plausibile (prima parte prima di " - " o " (")
                                    name = txt.split(" - ")[0].split("(")[0].strip()
                                    if len(name) < 3 or len(name.split()) > 5:
                                        continue
                                    results.append({
                                        "player": name,
                                        "team": team_norm,
                                        "source": url,
                                        "source_title": "Wikipedia (IT)",
                                        "source_date": datetime.now().strftime("%Y-%m-%d")
                                    })
                                break
                            if nxt.name == "table":
                                # parsing basilare a celle
                                rows = nxt.find_all("tr")
                                for tr in rows[1:]:
                                    cols = [c.get_text(" ").strip() for c in tr.find_all(["td", "th"])]
                                    if not cols:
                                        continue
                                    name = cols[0].split("(")[0].strip()
                                    if len(name) < 3:
                                        continue
                                    results.append({
                                        "player": name,
                                        "team": team_norm,
                                        "source": url,
                                        "source_title": "Wikipedia (IT)",
                                        "source_date": datetime.now().strftime("%Y-%m-%d")
                                    })
                                break
                            nxt = nxt.find_next_sibling()
                            hops += 1

                if results:
                    # dedup
                    seen = set()
                    uniq = []
                    for rcd in results:
                        key = (rcd["player"].lower(), rcd["team"].lower())
                        if key not in seen:
                            seen.add(key)
                            uniq.append(rcd)
                    logger.info(f"[WEB] Fallback Wikipedia ha trovato {len(uniq)} potenziali arrivi per {team_norm}")
                    return uniq[:8]

            except Exception:
                logger.warning("[WEB] Errore parsing Wikipedia per %s", team_norm)
                logger.debug(traceback.format_exc())

        # Se vuoi aggiungere Transfermarkt in futuro, aggancia qui (rispettando ToS/robots).
        return []

# -----------------------------
# Assistant
# -----------------------------

DEFAULT_SYSTEM_PROMPT = (
    "Sei un assistente fantacalcio. Regole: (1) Rispondi in italiano conciso e pratico. "
    "(2) Usa prima le informazioni verificate dal KB. (3) Se il KB è vuoto o datato, "
    "dichiara che non hai dati verificati e proponi di aggiornare. (4) Non inventare nomi o numeri. "
    "(5) Cita sempre le fonti (titolo e data) se presenti. (6) Per consigli d'asta: 2–3 criteri e rischio. "
    "(7) Per giocatori: includi ruolo, squadra, stagione, fantamedia se disponibili. "
    "(8) Preferisci info <= 8 settimane per trasferimenti/infortuni."
)

class FantacalcioAssistant:
    def __init__(self):
        # OpenAI client
        if OpenAI is None:
            self.client = None
        else:
            try:
                self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            except Exception:
                self.client = None

        # Prompt
        self.system_prompt = self._load_system_prompt()

        # KM
        self.knowledge_manager = KnowledgeManager(collection_name="fantacalcio_knowledge")
        logger.info("[Assistant] KnowledgeManager attivo")

        # Web fallback
        self.web_fallback = WebFallback()

        # Cache minimal
        self._cache_hits = 0
        self._cache_misses = 0
        self._resp_cache: Dict[str, str] = {}
        self._resp_cache_max = 64

        logger.info("[Assistant] Inizializzazione completata")

    # -------------------------
    # Prompt loader
    # -------------------------
    def _load_system_prompt(self) -> str:
        path = "prompt.json"
        if not os.path.exists(path):
            logger.warning("[Assistant] prompt.json non trovato: uso prompt di default")
            return DEFAULT_SYSTEM_PROMPT
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # supporta sia schema nuovo (system.content) sia chiave semplice "prompt"
            if isinstance(data, dict) and "system" in data and isinstance(data["system"], dict):
                content = data["system"].get("content")
                if isinstance(content, str) and content.strip():
                    logger.info("[Assistant] prompt.json caricato correttamente (system.content)")
                    return content.strip()
            if "prompt" in data and isinstance(data["prompt"], str):
                logger.info("[Assistant] prompt.json caricato correttamente (prompt)")
                return data["prompt"].strip()
            logger.error("[Assistant] Errore caricamento prompt: file senza chiave valida 'system.content' o 'prompt'")
            return DEFAULT_SYSTEM_PROMPT
        except Exception as e:
            logger.error("[Assistant] Errore lettura prompt.json: %s", e)
            return DEFAULT_SYSTEM_PROMPT

    # -------------------------
    # Pubbliche
    # -------------------------
    def get_response(self, message: str, context: Optional[Dict[str, Any]] = None) -> str:
        context = context or {}
        mode = context.get("mode") or context.get("language") or "classic"

        # cache
        cache_key = f"{message.strip().lower()}|{mode}"
        if cache_key in self._resp_cache:
            self._cache_hits += 1
            return self._resp_cache[cache_key]
        self._cache_misses += 1

        intent = _intent_of(message)
        logger.info("[Assistant] Intent rilevato: %s", intent)

        if intent == "transfer":
            reply = self._handle_transfer_query(message, context)
        elif intent == "value":
            reply = self._handle_value_query(message, context)
        elif intent == "injury":
            reply = self._handle_injury_query(message, context)
        elif intent == "fixtures":
            reply = self._handle_fixture_query(message, context)
        else:
            reply = self._handle_generic_query(message, context)

        # save cache (cap)
        if len(self._resp_cache) >= self._resp_cache_max:
            # rimuovi una entry arbitraria (semplice)
            self._resp_cache.pop(next(iter(self._resp_cache)))
        self._resp_cache[cache_key] = reply
        return reply

    def reset_conversation(self) -> str:
        self._resp_cache.clear()
        return "Conversazione resettata. Pronto a ripartire! 🟢"

    def get_cache_stats(self) -> Dict[str, Any]:
        total = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total * 100) if total else 0.0
        return {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate_percentage": round(hit_rate, 1),
            "cache_size": len(self._resp_cache),
            "max_cache_size": self._resp_cache_max,
        }

    # -------------------------
    # Handlers
    # -------------------------

    def _handle_transfer_query(self, message: str, context: Dict[str, Any]) -> str:
        """
        Pipeline anti-hallucination:
        1) Estrae team
        2) Cerca nel KB (type in ['transfer','current_player'])
        3) Valida freschezza (<= 56 giorni)
        4) Se vuoto/stale → opzionale web fallback
        5) Se ancora vuoto → risposta prudente senza nomi
        """
        # 1) Estrazione team semplice
        team = self._extract_team_from_text(message)
        team_disp = team or "la squadra richiesta"

        kb_sources: List[Dict[str, Any]] = []
        verified: List[Dict[str, Any]] = []

        # 2) Cerca nel KB
        try:
            where = {"type": ["transfer", "current_player"]}
            results = self._km_search(message, where=where, n_results=12)
            # normalizza
            for r in results:
                md = r.get("metadata", {}) or {}
                src_date = _str2date(str(md.get("source_date") or md.get("valid_from") or ""))
                item = {
                    "player": md.get("player"),
                    "team": md.get("team"),
                    "type": md.get("type"),
                    "source_title": md.get("source_title", "Interno KB"),
                    "source_date": md.get("source_date") or md.get("valid_from") or "",
                }
                kb_sources.append(item)
                # 3) verifica freschezza e coerenza team
                if (not _is_stale(src_date, 56)) and (not team or _normalize_team_name(md.get("team", "")) == _normalize_team_name(team)):
                    if md.get("type") in ("transfer", "current_player"):
                        if md.get("player"):
                            verified.append(item)
        except Exception as e:
            logger.error("[Assistant] Errore search_knowledge transfer: %s", e)

        # 4) Se vuoto/stale → web fallback (opzionale)
        web_sources: List[Dict[str, Any]] = []
        if not verified:
            web_results = self.web_fallback.search_transfers(team or "")
            # mappa in formato uniforme
            for w in web_results:
                web_sources.append({
                    "player": w.get("player"),
                    "team": w.get("team"),
                    "type": "transfer",
                    "source_title": w.get("source_title") or "Web",
                    "source_date": w.get("source_date") or datetime.now().strftime("%Y-%m-%d"),
                })

        # 5) Componi risposta con regole anti-hallucination
        if not verified and not web_sources:
            # NESSUN NOME
            txt = (
                f"Non ho dati verificati nel mio database sugli ultimi acquisti di {team_disp}. "
                "Posso provare a recuperarli da fonti pubbliche e aggiornare il KB (es. Wikipedia). "
                "Vuoi procedere con l’aggiornamento?"
            )
            return txt

        # Aggrega risultati (preferisci KB, poi Web)
        final_list = verified[:6] if verified else web_sources[:6]

        # Render essenziale + fonti
        lines = []
        for it in final_list:
            lines.append(f"- {it.get('player', 'N/D')} • {it.get('team', 'N/D')}")

        sources = []
        src_pool = verified if verified else web_sources
        # dedup by (title,date)
        seen_src = set()
        for it in src_pool:
            key = (it.get("source_title", ""), it.get("source_date", ""))
            if key in seen_src:
                continue
            seen_src.add(key)
            sources.append(f"{it.get('source_title','Fonte')} — {it.get('source_date','')}")
            if len(sources) >= 3:
                break

        return (
            f"Ultimi acquisti per {team_disp} (fonti recenti):\n"
            + "\n".join(lines) +
            ("\n\nFonti: " + " | ".join(sources) if sources else "")
        )

    def _handle_value_query(self, message: str, context: Dict[str, Any]) -> str:
        """
        Consigli d’asta / formazione.
        - Cerca nel KB giocatori con metadati (fantamedia/price/role).
        - Supporta formati tipo 3-5-2, 4-2-3-1, 4-2-2-2, 4-3-1-2, 3-4-1-2, 4-3-2-1.
        - Se non trovi abbastanza dati, risposta prudente + suggerimento ad aggiornare il KB.
        """
        formation = self._extract_formation(message)
        budget = self._extract_budget(message)

        # 1) prova a costruire un "catalogo" rapido dal KM
        catalog = self._build_player_catalog()  # lista di dict con price/fantamedia/role/team/player
        if not catalog:
            return (
                "Non ho abbastanza dati strutturati nel mio database per comporre una formazione affidabile. "
                "Suggerisco di aggiornare il KB (dati fantamedia/prezzo) e riprovare."
            )

        # 2) Se formation mancante, default al 3-5-2
        formation = formation or "3-5-2"
        if not self._formation_supported(formation):
            # normalizza verso una delle supportate
            formation = self._closest_supported(formation)

        # 3) Se manca budget, default 500
        budget = budget or 500

        # 4) Selezione greedy semplice: massimizza fantamedia/budget per ruolo
        try:
            squad, total = self._pick_squad(catalog, formation, budget)
        except Exception as e:
            logger.error("[Assistant] Errore pick_squad: %s", e)
            return "Ho avuto un problema nell’ottimizzare la formazione. Riprova tra poco."

        if not squad:
            return (
                f"Non riesco a costruire una {formation} con il budget di {budget} crediti con i dati attuali. "
                "Aggiorna il KB (fantamedia/prezzi) e riprova."
            )

        # 5) Rendi risposta
        lines = [f"Formazione consigliata {formation} — Budget usato: {total}/{budget}"]
        for role in ["P", "D", "C", "A"]:
            role_list = [p for p in squad if p["role"] == role]
            if role_list:
                lines.append(f"{self._role_label(role)}: " + ", ".join(f"{p['player']} ({p['team']}, {int(p['price'])})" for p in role_list))

        return "\n".join(lines)

    def _handle_injury_query(self, message: str, context: Dict[str, Any]) -> str:
        # molto semplice qui
        results = self._km_search(message, where={"type": ["injury", "suspension"]}, n_results=8)
        fresh = []
        for r in results:
            md = r.get("metadata", {}) or {}
            dt = _str2date(str(md.get("source_date") or ""))
            if not _is_stale(dt, 28):
                fresh.append(md)
        if not fresh:
            return "Non ho dati verificati e recenti su infortuni/squalifiche. Vuoi che provi ad aggiornare il KB?"

        lines = []
        sources = set()
        for md in fresh[:5]:
            lines.append(f"- {md.get('player','')} — {md.get('status','')} (rientro: {md.get('return_date','N/D')})")
            sources.add(f"{md.get('source_title','Interno KB')} — {md.get('source_date','')}")

        return "\n".join(lines) + ("\n\nFonti: " + " | ".join(list(sources)[:3]) if sources else "")

    def _handle_fixture_query(self, message: str, context: Dict[str, Any]) -> str:
        results = self._km_search(message, where={"type": ["fixture", "form", "team_stats"]}, n_results=10)
        if not results:
            return "Non ho dati aggiornati su calendario/forma. Suggerisco di aggiornare il KB."

        lines = []
        for r in results[:5]:
            md = r.get("metadata", {}) or {}
            snippet = r.get("text", "")[:120].strip()
            lines.append(f"- {md.get('team','')} — {snippet}… ({md.get('source_date','')})")
        return "\n".join(lines)

    def _handle_generic_query(self, message: str, context: Dict[str, Any]) -> str:
        # generic RAG
        results = self._km_search(message, n_results=6)
        if not results:
            return "Non ho fonti nel mio database per rispondere con precisione. Vuoi che aggiorni il KB e riprovi?"

        # Inoltra al modello LLM con contesto
        context_txt = self._format_context(results)
        return self._llm_answer(message, context_txt)

    # -------------------------
    # KM helpers
    # -------------------------

    def _km_search(self, query: str, where: Optional[Dict[str, Any]] = None, n_results: int = 8) -> List[Dict[str, Any]]:
        """
        Invoca KnowledgeManager.search_knowledge in modo compatibile.
        """
        try:
            # molte versioni del tuo KM accettano (query, n_results, where)
            return self.knowledge_manager.search_knowledge(query, n_results=n_results, where=where)  # type: ignore
        except TypeError:
            # fallback a firma senza where
            return self.knowledge_manager.search_knowledge(query, n_results=n_results)  # type: ignore
        except Exception as e:
            logger.error("[KM] search_knowledge error: %s", e)
            return []

    def _build_player_catalog(self) -> List[Dict[str, Any]]:
        """
        Estrae un mini-catalogo giocatori (player, team, role, price, fantamedia).
        """
        try:
            # Chiedi al KM se ha un metodo dedicato
            if hasattr(self.knowledge_manager, "build_player_catalog"):
                return getattr(self.knowledge_manager, "build_player_catalog")()  # type: ignore

            # Altrimenti query ampia
            results = self._km_search("player_info stagione", where={"type": ["player_info", "current_player"]}, n_results=200)
            catalog: List[Dict[str, Any]] = []
            for r in results:
                md = r.get("metadata", {}) or {}
                if not md.get("player") or not md.get("role"):
                    continue
                catalog.append({
                    "player": md.get("player"),
                    "team": md.get("team", "N/D"),
                    "role": md.get("role"),
                    "price": _safe_float(md.get("price", 0)),
                    "fantamedia": _safe_float(md.get("fantamedia", 0)),
                })
            # rimuovi duplicati su (player, team, role)
            seen = set()
            uniq = []
            for p in catalog:
                key = (p["player"].lower(), p["team"].lower(), p["role"])
                if key not in seen:
                    seen.add(key)
                    uniq.append(p)
            logger.info("[KM] Player catalog costruito: %d record", len(uniq))
            return uniq
        except Exception as e:
            logger.error("[KM] build_player_catalog error: %s", e)
            return []

    # -------------------------
    # Formazione helpers
    # -------------------------

    def _extract_formation(self, text: str) -> Optional[str]:
        m = re.search(r"\b([2-5]-[2-5]-[2-5](?:-[1-2])?)\b", text)
        if m:
            return m.group(1)
        return None

    def _extract_budget(self, text: str) -> Optional[int]:
        m = re.search(r"(\d{2,4})\s*credit", text.lower())
        if m:
            try:
                return int(m.group(1))
            except Exception:
                return None
        return None

    def _formation_supported(self, f: str) -> bool:
        return f in {
            "3-5-2", "4-3-3", "4-4-2", "4-2-3-1", "4-2-2-2", "4-3-1-2", "3-4-1-2", "4-3-2-1"
        }

    def _closest_supported(self, f: str) -> str:
        # fallback semplice
        return "3-5-2"

    def _role_label(self, role: str) -> str:
        return {"P": "Portieri", "D": "Difensori", "C": "Centrocampisti", "A": "Attaccanti"}.get(role, role)

    def _pick_squad(self, catalog: List[Dict[str, Any]], formation: str, budget: int) -> Tuple[List[Dict[str, Any]], int]:
        """
        Greedy semplice per formazione.
        Vincoli standard: 1P; D/C/A dipendono dalla formazione:
         - 3-5-2 → 1P, 3D, 5C, 2A
         - 4-2-3-1 → 1P, 4D, 5C (2C+3 "offensivi"), 1A → qui mappiamo come 4D,5C,1A
         - per semplicità: traduciamo tutte le varianti in D/C/A target.
        """
        role_targets = self._role_targets_from_formation(formation)
        # ordina per valore efficienza: fantamedia/price (evita divisioni per 0)
        def score(p):
            return p["fantamedia"] / max(p["price"], 1.0)

        selected: List[Dict[str, Any]] = []
        used_budget = 0

        # Scegli 1P migliore nel budget
        goalkeepers = [p for p in catalog if p["role"] == "P"]
        goalkeepers.sort(key=score, reverse=True)

        def pick_from_role(role: str, need: int):
            nonlocal used_budget, selected
            pool = [p for p in catalog if p["role"] == role]
            pool.sort(key=score, reverse=True)
            for p in pool:
                if len([x for x in selected if x["role"] == role]) >= need:
                    break
                if used_budget + p["price"] <= budget:
                    selected.append(p)
                    used_budget += int(p["price"])

        # 1 portiere
        for gk in goalkeepers:
            if used_budget + gk["price"] <= budget:
                selected.append(gk)
                used_budget += int(gk["price"])
                break

        # poi D, C, A
        pick_from_role("D", role_targets["D"])
        pick_from_role("C", role_targets["C"])
        pick_from_role("A", role_targets["A"])

        # Verifica completamento
        ok = (
            len([x for x in selected if x["role"] == "P"]) == 1 and
            len([x for x in selected if x["role"] == "D"]) == role_targets["D"] and
            len([x for x in selected if x["role"] == "C"]) == role_targets["C"] and
            len([x for x in selected if x["role"] == "A"]) == role_targets["A"]
        )
        return (selected if ok else [], used_budget)

    def _role_targets_from_formation(self, formation: str) -> Dict[str, int]:
        # mappa formazioni in D/C/A
        # ipotesi per semplicità: i tre numeri oltre al portiere, con C che include anche i trequartisti/esterni
        mapping = {
            "3-5-2": {"D": 3, "C": 5, "A": 2},
            "4-3-3": {"D": 4, "C": 3, "A": 3},
            "4-4-2": {"D": 4, "C": 4, "A": 2},
            "4-2-3-1": {"D": 4, "C": 5, "A": 1},
            "4-2-2-2": {"D": 4, "C": 4, "A": 2},
            "4-3-1-2": {"D": 4, "C": 4, "A": 2},
            "3-4-1-2": {"D": 3, "C": 5, "A": 2},
            "4-3-2-1": {"D": 4, "C": 5, "A": 1},
        }
        return mapping.get(formation, {"D": 3, "C": 5, "A": 2})

    # -------------------------
    # LLM
    # -------------------------

    def _llm_answer(self, user_msg: str, context_txt: str) -> str:
        """
        Chiama OpenAI solo con system prompt + contesto. Se client non configurato → messaggio di cortesia.
        """
        if not self.client:
            return ("⚠️ Servizio AI temporaneamente non disponibile. "
                    "Configura OPENAI_API_KEY per attivare le risposte generative.")

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Domanda: {user_msg}\n\nContesto (dal KB):\n{context_txt}\n\nIstruzioni: segui le regole del system prompt. Se il contesto è insufficiente, dillo chiaramente e proponi aggiornamento KB. Non inventare nomi."}
        ]

        try:
            resp = self.client.chat.completions.create(
                model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                messages=messages,
                temperature=float(os.environ.get("OPENAI_TEMPERATURE", "0.3")),
                max_tokens=int(os.environ.get("OPENAI_MAX_TOKENS", "600")),
                timeout=30,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            logger.error("[Assistant] Errore OpenAI: %s", e)
            return "Servizio momentaneamente non disponibile. Riprova tra poco."

    def _format_context(self, results: List[Dict[str, Any]]) -> str:
        parts = []
        for r in results[:6]:
            md = r.get("metadata", {}) or {}
            title = md.get("source_title", "Interno KB")
            date = md.get("source_date", "")
            txt = (r.get("text") or "")[:500]
            parts.append(f"- [{title} — {date}] {txt}")
        return "\n".join(parts)

    # -------------------------
    # NLP helpers
    # -------------------------

    def _extract_team_from_text(self, text: str) -> Optional[str]:
        # euristica semplice per team di Serie A (puoi ampliare il set)
        teams = [
            "Genoa","Inter","Milan","Juventus","Napoli","Roma","Lazio","Atalanta","Fiorentina",
            "Bologna","Torino","Sassuolo","Udinese","Empoli","Lecce","Monza","Cagliari","Verona",
            "Frosinone","Salernitana","Parma","Como","Venezia","Bari","Sampdoria","Palermo"
        ]
        tl = text.lower()
        for t in teams:
            if t.lower() in tl:
                return t
        # fallback: parola dopo "del/della/di"
        m = re.search(r"\b(del|della|di)\s+([a-zA-ZÀ-ÿ\.\- ]{3,})\b", text.lower())
        if m:
            guess = m.group(2).strip().title()
            if len(guess) <= 20:
                return guess
        return None
