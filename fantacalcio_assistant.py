# -*- coding: utf-8 -*-
import os
import json
import time
import re
import logging
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

import httpx
from knowledge_manager import KnowledgeManager

LOG = logging.getLogger("fantacalcio_assistant")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def _env_true(val: Optional[str]) -> bool:
    if val is None:
        return False
    return str(val).strip().lower() in {"1", "true", "yes", "y", "on"}


def _strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s


def _norm_text(s: str) -> str:
    """Normalizza stringa (nome/squadra) per matching."""
    if not s:
        return ""
    s = _strip_accents(s)
    s = s.lower()

    # rimuovi boilerplate societario
    s = re.sub(r"\b(f\.?c\.?|a\.?c\.?|u\.?s\.?|ssd|ss|ssc|u?d?|s\.?p\.?a\.?|calcio|club|1907|1913|1919|1927|1909|1905)\b", " ", s)
    s = s.replace(".", " ").replace("-", " ")

    s = re.sub(r"[^a-z0-9\s]", " ", s)  # toglie simboli (anche '|')
    s = re.sub(r"\s+", " ", s).strip()

    TEAM_ALIASES = {
        # big
        "juventus": "juventus", "juventus fc": "juventus", "juve": "juventus",
        "inter": "inter", "internazionale": "inter", "inter milano": "inter",
        "milan": "milan", "ac milan": "milan",
        "napoli": "napoli", "ssc napoli": "napoli",
        "lazio": "lazio", "ss lazio": "lazio",
        "roma": "roma", "as roma": "roma",
        "atalanta": "atalanta", "atalanta bc": "atalanta",
        "bologna": "bologna", "bologna fc": "bologna",
        "udinese": "udinese", "udinese calcio": "udinese",
        "fiorentina": "fiorentina", "acf fiorentina": "fiorentina",
        "torino": "torino", "torino fc": "torino",
        "verona": "verona", "hellas verona": "verona",
        "genoa": "genoa", "como": "como", "monza": "monza",
        "sassuolo": "sassuolo", "lecce": "lecce", "empoli": "empoli",
        "cagliari": "cagliari", "parma": "parma", "venezia": "venezia",
        "cremonese": "cremonese", "bari": "bari",
        # strani nel tuo JSON
        "como 1907": "como",
        "pisa sporting club": "pisa",
        "venezia fc": "venezia",
        "football club torinese": "torino",  # storico: lo mappiamo a "torino" per utilità
        "unione sportiva internazionale napoli": "napoli",
        "alba roma 1907": "roma",
        "unione sportiva fiumana": "fiumana",  # rimarrà fuori dal roster moderno ma non rompe
    }
    if s in TEAM_ALIASES:
        s = TEAM_ALIASES[s]
    return s


def _role_is_def(role: str) -> bool:
    role = (role or "").upper()
    return role in {"D", "DEF", "DC", "TD", "TS", "BR"}


def _role_is_mid(role: str) -> bool:
    return (role or "").upper() in {"C", "CM", "CC", "MED", "M"}


def _role_is_fwd(role: str) -> bool:
    return (role or "").upper() in {"A", "ATT", "PUN", "ST"}


def _role_is_gk(role: str) -> bool:
    return (role or "").upper() in {"P", "GK", "POR"}


class FantacalcioAssistant:
    """
    Assistant principale:
    - prompt.json (system)
    - KnowledgeManager (Chroma)
    - roster locale (season_roster.json)
    - indice età robusto (age_index + overrides)
    """

    def __init__(self) -> None:
        LOG.info("Initializing FantacalcioAssistant...")

        self.enable_web_fallback: bool = _env_true(os.getenv("ENABLE_WEB_FALLBACK", "0"))
        LOG.info("[Assistant] ENABLE_WEB_FALLBACK raw='%s' parsed=%s",
                 os.getenv("ENABLE_WEB_FALLBACK", "0"), self.enable_web_fallback)

        self.roster_json_path: str = os.getenv("ROSTER_JSON_PATH", "./season_roster.json")
        LOG.info("[Assistant] ROSTER_JSON_PATH=%s", self.roster_json_path)

        self.age_index_path: str = os.getenv("AGE_INDEX_PATH", "./data/age_index.json")
        self.age_overrides_path: str = os.getenv("AGE_OVERRIDES_PATH", "./data/age_overrides.json")

        self.openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
        self.openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.openai_temperature: float = float(os.getenv("OPENAI_TEMPERATURE", "0.20"))
        self.openai_max_tokens: int = int(os.getenv("OPENAI_MAX_TOKENS", "600"))
        LOG.info("[Assistant] OpenAI model=%s temp=%.2f max_tokens=%d",
                 self.openai_model, self.openai_temperature, self.openai_max_tokens)

        self.system_prompt: str = self._load_prompt_json("./prompt.json")

        self.km: KnowledgeManager = KnowledgeManager()
        LOG.info("[Assistant] KnowledgeManager attivo")

        self.roster: List[Dict[str, Any]] = self._load_and_normalize_roster(self.roster_json_path)

        self.ref_year: int = int(os.getenv("REF_YEAR", "2025"))
        self._age_index_raw: Dict[str, Any] = self._load_age_json_safe(self.age_index_path)
        LOG.info("[Assistant] age_index caricato: %d chiavi", len(self._age_index_raw))
        self._age_overrides_raw: Dict[str, Any] = self._load_age_json_safe(self.age_overrides_path)
        if self._age_overrides_raw:
            LOG.info("[Assistant] overrides caricato: %d chiavi", len(self._age_overrides_raw))

        self._age_map = self._build_age_map(self._age_index_raw, self._age_overrides_raw)
        self._name_only_age = self._build_name_only_age(self._age_map)

        self.roster = self._enrich_roster_with_age(self.roster, self._age_map, self._name_only_age)

        n_with_age = sum(1 for r in self.roster if r.get("age") is not None)
        LOG.info("[Assistant] Roster normalizzato: %d/%d record utili (età arricchite: %d)",
                 len(self.roster), len(self.roster), n_with_age)
        LOG.info("[Assistant] Inizializzazione completata")

    # ---------- Loaders ----------
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

    def _load_and_normalize_roster(self, path: str) -> List[Dict[str, Any]]:
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

        for item in data:
            if not isinstance(item, dict):
                continue
            name = (item.get("name") or item.get("player") or "").strip()
            role = (item.get("role") or item.get("position") or "").strip().upper()
            team = (item.get("team") or item.get("club") or "").strip()
            birth_year = item.get("birth_year") or item.get("year_of_birth") or None
            price = item.get("price") or item.get("cost") or None
            fm = item.get("fantamedia") or item.get("avg") or None
            appearances = item.get("appearances") or item.get("apps") or None

            roster.append({
                "name": name,
                "role": role,
                "team": team,
                "birth_year": birth_year,
                "price": price,
                "fantamedia": fm,
                "appearances": appearances,
            })
        LOG.info("[Assistant] Roster normalizzato: %d/%d record utili", len(roster), len(data))
        return roster

    def _load_age_json_safe(self, path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
                if isinstance(data, list):
                    out = {}
                    for row in data:
                        if not isinstance(row, dict):
                            continue
                        nm = _norm_text(row.get("name", ""))
                        tm = _norm_text(row.get("team", ""))
                        by = row.get("birth_year")
                        if nm and by:
                            out[f"{nm}@@{tm}"] = int(by)
                    return out
        except Exception as e:
            LOG.error("[Assistant] errore lettura age_index %s: %s", path, e)
        return {}

    # ---------- Age Map Builders ----------
    def _valid_birth_year(self, by: Any) -> Optional[int]:
        try:
            by = int(by)
        except Exception:
            return None
        # filtri sanità: niente futuri/assurdi
        if by < 1900 or by > self.ref_year:
            return None
        # un calciatore professionista difficilmente < 15 anni
        if by > (self.ref_year - 14):
            return None
        return by

    def _split_key_name_team(self, k: str) -> Tuple[str, str]:
        """
        Supporta sia 'name@@team' che 'name|team'.
        Se nessun delimitatore → (norm(k), "")
        """
        if "@@" in k:
            nk, tk = k.split("@@", 1)
        elif "|" in k:
            nk, tk = k.split("|", 1)
        else:
            nk, tk = k, ""
        return _norm_text(nk), _norm_text(tk)

    def _build_age_map(self, *dicts: Dict[str, Any]) -> Dict[Tuple[str, str], int]:
        out: Dict[Tuple[str, str], int] = {}
        dropped = 0
        for d in dicts:
            if not d:
                continue
            for k, v in d.items():
                if not isinstance(k, str):
                    continue
                # accetta sia {"birth_year": ...} sia valore diretto
                if isinstance(v, dict) and "birth_year" in v:
                    by = v.get("birth_year")
                else:
                    by = v
                by = self._valid_birth_year(by)
                if by is None:
                    dropped += 1
                    continue
                nk, tk = self._split_key_name_team(k)
                out[(nk, tk)] = by
        if dropped:
            LOG.info("[Assistant] age_index: scartate %d righe per birth_year non valido", dropped)
        return out

    def _build_name_only_age(self, age_map: Dict[Tuple[str, str], int]) -> Dict[str, int]:
        tmp: Dict[str, set] = {}
        for (nm, tm), by in age_map.items():
            tmp.setdefault(nm, set()).add(by)
        name_only: Dict[str, int] = {}
        for nm, years in tmp.items():
            if len(years) == 1:
                name_only[nm] = list(years)[0]
        return name_only

    def _enrich_roster_with_age(
        self,
        roster: List[Dict[str, Any]],
        age_map: Dict[Tuple[str, str], int],
        name_only_age: Dict[str, int],
    ) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for r in roster:
            if not isinstance(r, dict):
                continue
            name = r.get("name") or ""
            team = r.get("team") or ""
            by = r.get("birth_year")
            age_val: Optional[int] = None

            if by is not None:
                try:
                    by_int = int(by)
                    if 1900 <= by_int <= self.ref_year:
                        age_val = self.ref_year - by_int
                except Exception:
                    age_val = None

            if age_val is None:
                nn = _norm_text(name)
                tn = _norm_text(team)
                by2 = age_map.get((nn, tn))
                if by2 is None:
                    by2 = age_map.get((nn, ""))  # wildcard team
                if by2 is None:
                    by2 = name_only_age.get(nn)  # solo nome, se univoco
                if by2 is not None:
                    age_val = self.ref_year - int(by2)

            rr = dict(r)
            rr["age"] = age_val
            out.append(rr)
        return out

    # ---------- LLM ----------
    def _llm_complete(self, user_text: str, context_messages: Optional[List[Dict[str, str]]] = None) -> str:
        if not self.openai_api_key:
            return ("⚠️ Servizio AI non disponibile. Configura OPENAI_API_KEY e riavvia.")
        messages = [{"role": "system", "content": self.system_prompt}]
        if context_messages:
            messages.extend(context_messages)
        messages.append({"role": "user", "content": user_text})
        headers = {"Authorization": f"Bearer {self.openai_api_key}", "Content-Type": "application/json"}
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
                return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            LOG.error("[Assistant] Errore OpenAI: %s", e)
            return "⚠️ Servizio momentaneamente non disponibile."

    # ---------- Query ----------
    def _players_by_role(self, role_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        role_filter = (role_filter or "").upper()
        out = []
        for r in self.roster:
            role = (r.get("role") or "").upper()
            if role_filter and role != role_filter:
                continue
            out.append(r)
        return out

    def count_age_coverage_by_role(self) -> Dict[str, Dict[str, int]]:
        roles = ["P", "D", "C", "A"]
        res: Dict[str, Dict[str, int]] = {}
        for ro in roles:
            items = self._players_by_role(ro)
            total = len(items)
            with_age = sum(1 for x in items if x.get("age") is not None)
            u21 = sum(1 for x in items if (x.get("age") is not None and x["age"] <= 21))
            u23 = sum(1 for x in items if (x.get("age") is not None and x["age"] <= 23))
            res[ro] = {"total": total, "with_age": with_age, "u21": u21, "u23": u23}
        return res

    def pick_under_by_role(self, role: str, max_age: int = 21, top_n: int = 3) -> List[Dict[str, Any]]:
        cand = []
        for r in self.roster:
            if (r.get("role") or "").upper() != role.upper():
                continue
            age = r.get("age")
            if age is None or age > max_age:
                continue
            cand.append(r)

        if not cand:
            return []

        def sort_key(x):
            fm = x.get("fantamedia")
            try:
                fm = float(fm) if fm is not None else -1.0
            except Exception:
                fm = -1.0
            price = x.get("price")
            try:
                pr = float(price) if price is not None else 9999.0
            except Exception:
                pr = 9999.0
            return (-fm, pr, x.get("age") if x.get("age") is not None else 99)

        cand.sort(key=sort_key)
        seen = set()
        out = []
        for c in cand:
            nm = (c.get("name") or "").strip()
            if nm and nm in seen:
                continue
            seen.add(nm)
            out.append(c)
            if len(out) >= top_n:
                break
        return out

    # ---------- Routing ----------
    def get_response(self, user_text: str, mode: str = "classic",
                     context: Optional[Dict[str, Any]] = None) -> str:
        lt = (user_text or "").lower()

        # intent under 21/23 per ruolo
        if ("under 21" in lt or "under21" in lt or "u21" in lt or "under 23" in lt or "u23" in lt):
            target_age = 21 if ("23" not in lt and "u23" not in lt) else 23
            role_letter = None
            if "difensor" in lt:
                role_letter = "D"
            elif "centrocamp" in lt or "mezz" in lt or "mediano" in lt:
                role_letter = "C"
            elif "attacc" in lt or "punta" in lt:
                role_letter = "A"
            elif "portier" in lt or "gk" in lt:
                role_letter = "P"

            if role_letter:
                picks = self.pick_under_by_role(role_letter, max_age=target_age, top_n=3)
                if not picks:
                    return (f"Non ho profili Under {target_age} affidabili per questo ruolo dal roster attuale. "
                            f"Puoi chiedere senza vincolo d’età o per un altro ruolo/lega.")
                lines = []
                for p in picks:
                    name = p.get("name") or "N/D"
                    team = p.get("team") or "—"
                    age = p.get("age")
                    fm = p.get("fantamedia")
                    price = p.get("price")
                    bits = [f"**{name}** ({team})"]
                    meta = []
                    if age is not None: meta.append(f"{age} anni")
                    if fm is not None:
                        try: meta.append(f"FM {float(fm):.2f}")
                        except Exception: meta.append(f"FM {fm}")
                    if price is not None: meta.append(f"€ {price}")
                    if meta: bits.append(" — " + ", ".join(meta))
                    lines.append(" ".join(bits))
                header = f"Ecco {len(lines)} Under {target_age} nel ruolo {role_letter}:"
                return header + "\n- " + "\n- ".join(lines)

        return self._llm_complete(user_text, context_messages=[])

    # ---------- Debug helpers ----------
    def debug_under_sample(self, role: str, max_age: int = 21, take: int = 5) -> List[Dict[str, Any]]:
        out = []
        for p in self.roster:
            if (p.get("role") or "").upper() != role.upper():
                continue
            age = p.get("age")
            if age is not None and age <= max_age:
                out.append({
                    "name": p.get("name"),
                    "team": p.get("team"),
                    "role": p.get("role"),
                    "age": age,
                    "fantamedia": p.get("fantamedia"),
                    "price": p.get("price"),
                })
        out.sort(key=lambda x: (-(float(x["fantamedia"]) if x["fantamedia"] is not None else -1.0),
                                x["price"] if x["price"] is not None else 9999,
                                x["age"] if x["age"] is not None else 99))
        return out[:take]

    def peek_age(self, name: str, team: str = "") -> Dict[str, Any]:
        nn = _norm_text(name)
        tn = _norm_text(team)
        by = None
        age = None
        if (nn, tn) in self._age_map:
            by = self._age_map[(nn, tn)]
        elif (nn, "") in self._age_map:
            by = self._age_map[(nn, "")]
        elif nn in self._name_only_age:
            by = self._name_only_age[nn]
        if by is not None:
            try:
                age = self.ref_year - int(by)
            except Exception:
                age = None
        return {"name": name, "team": team, "birth_year": by, "age": age}
