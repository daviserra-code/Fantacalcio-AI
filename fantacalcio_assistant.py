# fantacalcio_assistant.py
# -*- coding: utf-8 -*-

import os
import re
import json
import time
import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx

from knowledge_manager import KnowledgeManager

LOG = logging.getLogger("fantacalcio_assistant")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# ---------------------------
# Utils
# ---------------------------
def _env_true(val: Optional[str]) -> bool:
    if val is None:
        return False
    return str(val).strip().lower() in {"1", "true", "yes", "y", "on"}

def _now_ts() -> float:
    try:
        return time.time()
    except Exception:
        return 0.0

def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default

def _safe_int(x: Any, default: int = 0) -> int:
    try:
        if x is None:
            return default
        return int(float(x))
    except Exception:
        return default


# ---------------------------
# Assistant
# ---------------------------
class FantacalcioAssistant:
    """
    Orchestratore:
    - prompt.json (regole)
    - KnowledgeManager (Chroma)
    - roster locale (season_roster.json) con hot-reload
    - fallback web (flag ENABLE_WEB_FALLBACK - gestito dal tuo layer, qui lo leggo solo)
    - intents quick (under21, formazioni).

    Nota: codice robusto contro roster “sporchi” (tipi misti, campi mancanti).
    """

    # Formazioni supportate → conteggio per ruolo (P sempre 1)
    FORMATION_MAP: Dict[str, Dict[str, int]] = {
        "3-5-2":   {"D": 3, "C": 5, "A": 2},
        "3-4-1-2": {"D": 3, "C": 5, "A": 2},  # 4+1 treq -> 5 C
        "4-2-3-1": {"D": 4, "C": 5, "A": 1},  # 2+3 -> 5 C
        "4-3-1-2": {"D": 4, "C": 4, "A": 2},  # 3+1 -> 4 C
        "4-3-2-1": {"D": 4, "C": 5, "A": 1},  # 3+2 -> 5 C
        "4-2-2-2": {"D": 4, "C": 4, "A": 2},  # 2+2 -> 4 C
        # fallback generico 4-4-2 se parsing fallisce
        "4-4-2":   {"D": 4, "C": 4, "A": 2},
    }

    # Allocazione budget suggerita di base (percentuali)
    DEFAULT_BUDGET_SPLIT = {"P": 0.06, "D": 0.24, "C": 0.38, "A": 0.32}

    # Prezzo “di default” per ruolo quando mancante (stima grossolana)
    ROLE_DEFAULT_PRICE = {"P": 12, "D": 18, "C": 28, "A": 36}

    def __init__(self) -> None:
        LOG.info("Initializing FantacalcioAssistant...")

        # Flags / ENV
        self.enable_web_fallback: bool = _env_true(os.getenv("ENABLE_WEB_FALLBACK", "0"))
        LOG.info("[Assistant] ENABLE_WEB_FALLBACK raw='%s' parsed=%s",
                 os.getenv("ENABLE_WEB_FALLBACK", "0"), self.enable_web_fallback)

        # File paths
        self.roster_json_path: str = os.getenv("ROSTER_JSON_PATH", "./season_roster.json")
        LOG.info("[Assistant] ROSTER_JSON_PATH=%s", self.roster_json_path)

        # OpenAI settings
        self.openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
        self.openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.openai_temperature: float = float(os.getenv("OPENAI_TEMPERATURE", "0.20"))
        self.openai_max_tokens: int = int(os.getenv("OPENAI_MAX_TOKENS", "600"))
        LOG.info("[Assistant] OpenAI model=%s temp=%.2f max_tokens=%d",
                 self.openai_model, self.openai_temperature, self.openai_max_tokens)

        # Prompt
        self.system_prompt: str = self._load_prompt_json("./prompt.json")

        # Knowledge Manager
        self.km: KnowledgeManager = KnowledgeManager()
        LOG.info("[Assistant] KnowledgeManager attivo")

        # Roster + mtime
        self.roster: List[Dict[str, Any]] = self._load_and_normalize_roster(self.roster_json_path)
        self._roster_mtime: float = self._get_mtime(self.roster_json_path)

        LOG.info("[Assistant] Inizializzazione completata")

    # ---------------------------
    # Setup / Caricamenti
    # ---------------------------
    def _load_prompt_json(self, path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            LOG.error("[Assistant] Errore caricamento prompt: %s", e)
            return ("Sei un assistente fantacalcio. Rispondi in modo conciso, pratico, in italiano; "
                    "non inventare dati, dichiara incertezza se mancano le fonti.")

        if isinstance(cfg, dict):
            if "system" in cfg and isinstance(cfg["system"], dict):
                sys = cfg["system"]
                name = sys.get("name", "fantacalcio_system")
                content = sys.get("content", "")
                style = sys.get("style", "")
                language = sys.get("language", "it")
                system_text = f"[{name}] ({language}, {style})\n{content}".strip()
                LOG.info("[Assistant] prompt.json caricato correttamente")
                return system_text
            if "prompt" in cfg and isinstance(cfg["prompt"], str):
                LOG.info("[Assistant] prompt.json caricato correttamente")
                return cfg["prompt"]

        LOG.error("[Assistant] prompt.json non contiene 'system' o 'prompt' validi")
        return ("Sei un assistente fantacalcio. Rispondi in modo conciso, pratico, in italiano; "
                "non inventare dati, dichiara incertezza se mancano le fonti.")

    def _get_mtime(self, path: str) -> float:
        try:
            return os.path.getmtime(path)
        except Exception:
            return 0.0

    def _maybe_reload_roster(self) -> None:
        """Ricarica il roster se il file è stato aggiornato (hot-reload via mtime)."""
        current_mtime = self._get_mtime(self.roster_json_path)
        if current_mtime and current_mtime > (self._roster_mtime or 0):
            LOG.info("[Assistant] Roster file aggiornato su disco (mtime %s → %s). Ricarico...",
                     self._roster_mtime, current_mtime)
            self.roster = self._load_and_normalize_roster(self.roster_json_path)
            self._roster_mtime = current_mtime

    def _load_and_normalize_roster(self, path: str) -> List[Dict[str, Any]]:
        """
        Carica season_roster.json e normalizza:
        - ignora elementi non-dizionario
        - normalizza chiavi base (name, role, team, birth_year, price, fantamedia)
        - mappa ruoli “strani” su P/D/C/A
        """
        roster: List[Dict[str, Any]] = []
        if not os.path.exists(path):
            LOG.warning("[Assistant] Roster file non trovato: %s", path)
            return roster

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            LOG.error("[Assistant] Errore apertura roster: %s", e)
            return roster

        if not isinstance(data, list):
            LOG.warning("[Assistant] roster non è una lista, lo ignoro")
            return roster

        def map_role(raw: str) -> str:
            r = (raw or "").strip().upper()
            if r in {"P", "POR", "GK", "PT"}:
                return "P"
            if r in {"D", "DEF", "DC", "TD", "TS", "BR"}:
                return "D"
            if r in {"C", "CC", "MED", "M", "TQ", "TRQ", "MEZZ", "EST"}:
                return "C"
            if r in {"A", "ATT", "FW", "SP", "PUN", "ESTA"}:
                return "A"
            # default prudente
            return "C"

        cnt_total = len(data)
        for item in data:
            if not isinstance(item, dict):
                continue
            name = (item.get("name") or item.get("player") or "").strip()
            role = map_role(item.get("role") or item.get("position") or "")
            team = (item.get("team") or item.get("club") or "").strip()
            birth_year = item.get("birth_year") or item.get("year_of_birth") or None
            price = item.get("price") or item.get("cost") or None
            fm = item.get("fantamedia") or item.get("avg") or item.get("rating") or None

            norm = {
                "name": name,
                "role": role,
                "team": team,
                "birth_year": birth_year,
                "price": price,
                "fantamedia": fm
            }
            # accetto anche senza nome se proprio
            if name:
                roster.append(norm)

        LOG.info("[Assistant] Roster normalizzato: %d/%d record utili",
                 len(roster), cnt_total)
        return roster

    # ---------------------------
    # OpenAI (fallback generale)
    # ---------------------------
    def _llm_complete(self, user_text: str, context_messages: Optional[List[Dict[str, str]]] = None) -> str:
        if not self.openai_api_key:
            return ("⚠️ Servizio AI temporaneamente non disponibile. "
                    "Configura OPENAI_API_KEY e riavvia.")

        messages = [{"role": "system", "content": self.system_prompt}]
        if context_messages:
            messages.extend(context_messages)
        messages.append({"role": "user", "content": user_text})

        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.openai_model,
            "temperature": self.openai_temperature,
            "max_tokens": self.openai_max_tokens,
            "messages": messages,
        }

        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post("https://api.openai.com/v1/chat/completions",
                                   headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                out = data["choices"][0]["message"]["content"].strip()
                return out
        except Exception as e:
            LOG.error("[Assistant] Errore OpenAI: %s", e)
            return ("⚠️ Servizio momentaneamente non disponibile. Riprova tra poco.")

    # ---------------------------
    # Helpers: età/ruoli/prezzi
    # ---------------------------
    def _is_defender(self, role: str) -> bool:
        return role == "D"

    def _age_from_birth_year(self, birth_year: Optional[int], ref_year: int = 2025) -> Optional[int]:
        try:
            by = int(birth_year)
            return ref_year - by
        except Exception:
            return None

    def _estimate_price(self, p: Dict[str, Any]) -> float:
        role = p.get("role") or "C"
        price = p.get("price")
        fm = _safe_float(p.get("fantamedia"), 0.0)
        if price is None or price == "":
            # stima semplice: base per ruolo + incremento da FM
            base = self.ROLE_DEFAULT_PRICE.get(role, 25)
            # FM ~ 5-8 -> aggiustamento
            adj = max(0.0, (fm - 5.5) * 8.0)
            return float(base + adj)
        return _safe_float(price, self.ROLE_DEFAULT_PRICE.get(role, 25))

    def _score_player(self, p: Dict[str, Any]) -> float:
        # priorità alla fantamedia, con piccolo premio se team valorizzato
        fm = _safe_float(p.get("fantamedia"), 0.0)
        team_bonus = 0.5 if (p.get("team") or "").strip() else 0.0
        return fm * 10.0 + team_bonus

    # ---------------------------
    # Intent: difensori under 21
    # ---------------------------
    def _handle_under21_defenders(self, user_text: str) -> str:
        self._maybe_reload_roster()

        # 1) dal roster locale
        roster_defs: List[Dict[str, Any]] = []
        for r in self.roster:
            if not isinstance(r, dict):
                continue
            if not self._is_defender(r.get("role") or ""):
                continue
            age = self._age_from_birth_year(r.get("birth_year"))
            if age is None or age >= 21:
                continue
            roster_defs.append(r)

        # 2) se pochi, prova a integrare con un piccolo catalogo dal KM (metadati)
        if len(roster_defs) < 3:
            try:
                km_cand = self._build_player_catalog_few(limit=300)
            except Exception as e:
                LOG.error("[Assistant] build_player_catalog_few error: %s", e)
                km_cand = []
            for m in km_cand:
                if not isinstance(m, dict):
                    continue
                if not self._is_defender(m.get("role") or ""):
                    continue
                age = self._age_from_birth_year(m.get("birth_year"))
                if age is None or age >= 21:
                    continue
                roster_defs.append(m)

        # dedup per nome
        seen = set()
        unique_defs: List[Dict[str, Any]] = []
        for d in roster_defs:
            name = (d.get("name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            unique_defs.append(d)

        if not unique_defs:
            return ("Non ho difensori Under 21 con dati sufficienti. "
                    "Ripeti tra poco: l’ETL potrebbe aver appena aggiornato il roster.")

        # ordina per (fantamedia desc, poi prezzo stimato asc)
        def sort_key(x):
            fm = _safe_float(x.get("fantamedia"), 0.0)
            pr = self._estimate_price(x)
            return (-fm, pr)

        unique_defs.sort(key=sort_key)
        top = unique_defs[:3]

        lines = []
        for p in top:
            name = p.get("name") or "N/D"
            team = p.get("team") or "—"
            age = self._age_from_birth_year(p.get("birth_year"))
            fm = p.get("fantamedia")
            price = self._estimate_price(p)

            bits = [f"**{name}**"]
            if team and team != "—":
                bits.append(f"({team})")
            meta = []
            if age is not None:
                meta.append(f"{age} anni")
            if fm is not None:
                try:
                    meta.append(f"FM {float(fm):.2f}")
                except Exception:
                    meta.append(f"FM {fm}")
            if price:
                meta.append(f"stima prezzo {int(round(price))}")
            if meta:
                bits.append(" — " + ", ".join(meta))
            lines.append(" ".join(bits))

        return "Ecco 2-3 difensori Under 21 interessanti:\n- " + "\n- ".join(lines)

    def _build_player_catalog_few(self, limit: int = 300) -> List[Dict[str, Any]]:
        seasons = ["2025-26", "2024-25"]
        candidates: List[Dict[str, Any]] = []
        for season in seasons:
            where = {"$and": [{"type": {"$in": ["player_info", "current_player"]}}, {"season": season}]}
            try:
                res = self.km.search_knowledge(
                    text=None,
                    where=where,
                    n_results=limit,
                    include=["metadatas"]
                )
            except TypeError:
                res = self.km.search_knowledge(
                    where=where,
                    n_results=limit,
                    include=["metadatas"]
                )
            except Exception as e:
                LOG.error("[KM] search_knowledge error: %s", e)
                continue

            metas = res.get("metadatas") or []
            if not isinstance(metas, list):
                continue
            for m in metas:
                if not isinstance(m, dict):
                    continue
                name = (m.get("name") or m.get("player") or "").strip()
                role = (m.get("role") or m.get("position") or "").strip().upper()
                team = (m.get("team") or m.get("club") or "").strip()
                birth_year = m.get("birth_year") or m.get("birthyear")
                price = m.get("price") or m.get("cost")
                fm = m.get("fantamedia") or m.get("avg")
                if name:
                    candidates.append({
                        "name": name, "role": role, "team": team,
                        "birth_year": birth_year, "price": price, "fantamedia": fm
                    })
        LOG.info("[Assistant] build_player_catalog_few OK: %d record", len(candidates))
        return candidates

    # ---------------------------
    # Intent: formazione con budget
    # ---------------------------
    def _parse_budget(self, text: str, default_budget: int = 500) -> int:
        m = re.search(r"(\d{2,4})\s*credit", text.lower())
        if m:
            return _safe_int(m.group(1), default_budget)
        # fallback: numero isolato
        m2 = re.search(r"\b(\d{2,4})\b", text)
        if m2:
            return _safe_int(m2.group(1), default_budget)
        return default_budget

    def _parse_formation_key(self, text: str) -> str:
        t = text.replace(" ", "")
        for key in self.FORMATION_MAP.keys():
            if key in t:
                return key
        # tenta pattern generico N-N-N(-N)
        m = re.search(r"\b([2345])\-([23456])\-([1234])(?:\-([12]))?\b", t)
        if m:
            base = "-".join([g for g in m.groups() if g])
            if base in self.FORMATION_MAP:
                return base
        return "4-4-2"

    def _split_by_role(self) -> Dict[str, List[Dict[str, Any]]]:
        pools = {"P": [], "D": [], "C": [], "A": []}
        for p in self.roster:
            if not isinstance(p, dict):
                continue
            r = (p.get("role") or "C").upper()
            if r not in pools:
                r = "C"
            pools[r].append(p)
        # ordina ogni pool per score desc (fm alta prima), poi prezzo stimato asc
        for r in pools:
            pools[r].sort(key=lambda x: (-self._score_player(x), self._estimate_price(x)))
        return pools

    def _select_lineup(self, formation_key: str, budget: int) -> Tuple[List[Dict[str, Any]], float]:
        """
        Selezione greedy rispettando ruoli e provando a stare nel budget.
        Se il budget è molto stretto e i prezzi mancano, usa stime e cerca alternative più economiche.
        """
        self._maybe_reload_roster()
        if not self.roster:
            return [], 0.0

        req = self.FORMATION_MAP.get(formation_key, self.FORMATION_MAP["4-4-2"])
        pools = self._split_by_role()

        # Per-ruolo budget (distribuzione base)
        split = self.DEFAULT_BUDGET_SPLIT
        role_budget = {
            "P": budget * split["P"],
            "D": budget * split["D"],
            "C": budget * split["C"],
            "A": budget * split["A"],
        }

        lineup: List[Dict[str, Any]] = []
        total = 0.0

        # 1) Portiere
        keeper = None
        for cand in pools["P"]:
            price = self._estimate_price(cand)
            keeper = cand
            total += price
            break
        if keeper:
            lineup.append(keeper)

        # 2) Difensori / Centrocampisti / Attaccanti
        for role in ("D", "C", "A"):
            needed = req.get(role, 0)
            if needed <= 0:
                continue
            chosen: List[Dict[str, Any]] = []
            for cand in pools[role]:
                if len(chosen) >= needed:
                    break
                price = self._estimate_price(cand)
                # selezione semplice: aggiungi, limeremo dopo se sfora
                chosen.append(cand)
                total += price
            lineup.extend(chosen)

        # 3) Se sforiamo tanto, prova rimpiazzi più economici (very simple heuristic)
        if total > budget:
            # ordina i titolari per (costo stimato desc, score asc) per sostituire i peggiori più costosi
            lineup.sort(key=lambda p: (-self._estimate_price(p), self._score_player(p)))
            for i, over_p in enumerate(list(lineup)):
                if total <= budget:
                    break
                role = (over_p.get("role") or "C").upper()
                # cerca un rimpiazzo più economico nel pool dello stesso ruolo
                for cand in pools[role]:
                    if cand in lineup:
                        continue
                    cand_price = self._estimate_price(cand)
                    over_price = self._estimate_price(over_p)
                    if cand_price + (total - over_price) <= budget:
                        # swap
                        lineup.remove(over_p)
                        lineup.append(cand)
                        total = total - over_price + cand_price
                        break

        return lineup, total

    def _format_lineup(self, formation_key: str, budget: int, lineup: List[Dict[str, Any]], total: float) -> str:
        req = self.FORMATION_MAP.get(formation_key, self.FORMATION_MAP["4-4-2"])
        # ordina per ruolo
        lined = {"P": [], "D": [], "C": [], "A": []}
        for p in lineup:
            r = (p.get("role") or "C").upper()
            if r not in lined:
                r = "C"
            price = self._estimate_price(p)
            fm = p.get("fantamedia")
            team = p.get("team") or "—"
            try:
                fm_txt = f"{float(fm):.2f}" if fm is not None else "—"
            except Exception:
                fm_txt = str(fm)
            lined[r].append(f"**{p.get('name')}** ({team}) — FM {fm_txt}, stima €{int(round(price))}")

        lines = [f"Formazione suggerita **{formation_key}** con budget **{budget}** crediti:"]
        if lined["P"]:
            lines.append(f"P ({req.get('D',0)+req.get('C',0)+req.get('A',0)+1 - (req.get('D',0)+req.get('C',0)+req.get('A',0))}): " + ", ".join(lined["P"]))
        if lined["D"]:
            lines.append(f"D ({req.get('D',0)}): " + ", ".join(lined["D"][:req.get('D',0)]))
        if lined["C"]:
            lines.append(f"C ({req.get('C',0)}): " + ", ".join(lined["C"][:req.get('C',0)]))
        if lined["A"]:
            lines.append(f"A ({req.get('A',0)}): " + ", ".join(lined["A"][:req.get('A',0)]))

        lines.append(f"**Totale stimato**: ~{int(round(total))} crediti")
        lines.append("Nota: prezzi stimati quando mancanti (da ruolo/fantamedia). Affina dopo l’aggiornamento completo.")
        return "\n".join(lines)

    def _handle_formation_with_budget(self, user_text: str) -> str:
        self._maybe_reload_roster()
        formation_key = self._parse_formation_key(user_text)
        budget = self._parse_budget(user_text, 500)

        if not self.roster:
            # roster ancora non pronto
            return (f"Sto aggiornando i dati: riprova tra qualche secondo. "
                    f"Nel frattempo, allocazione consigliata per **{formation_key}** (budget {budget}): "
                    f"P 5–6%, D 22–25%, C 36–40%, A 33–36%.")

        lineup, total = self._select_lineup(formation_key, budget)
        if not lineup:
            # come fallback, torna allocazione, ma ora il roster c’è: capita solo se parsing fallito duramente
            return (f"Allocazione budget consigliata per **{formation_key}** (budget {budget}): "
                    f"P 5–6%, D 22–25%, C 36–40%, A 33–36%.\n"
                    f"(Non sono riuscito a costruire un 11 coerente; ritenta subito dopo.)")

        return self._format_lineup(formation_key, budget, lineup, total)

    # ---------------------------
    # Routing principale
    # ---------------------------
    def get_response(self, user_text: str, mode: str = "classic",
                     context: Optional[Dict[str, Any]] = None) -> str:
        lt = user_text.lower().strip()

        # Intent: difensori under 21
        if ("under 21" in lt or "under21" in lt) and ("difensor" in lt or "difensori" in lt or "difensore" in lt):
            return self._handle_under21_defenders(user_text)

        # Intent: formazione con budget (riconosci alcune chiavi)
        if any(k in lt for k in ["3-5-2", "3-4-1-2", "4-2-3-1", "4-2-2-2", "4-3-1-2", "4-3-2-1", "4-4-2", "formazione"]):
            if "credit" in lt or re.search(r"\b\d{2,4}\b", lt):
                return self._handle_formation_with_budget(user_text)

        # Fallback: LLM generico
        return self._llm_complete(user_text, context_messages=[])
