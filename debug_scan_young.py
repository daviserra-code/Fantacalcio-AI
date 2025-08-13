# fantacalcio_assistant.py
# -*- coding: utf-8 -*-

import os
import re
import json
import time
import httpx
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

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


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _safe_int(x: Any) -> Optional[int]:
    try:
        return int(str(x).strip())
    except Exception:
        return None


class FantacalcioAssistant:
    """
    Orchestrazione:
    - prompt.json (regole)
    - KnowledgeManager (Chroma + embeddings)
    - roster locale (season_roster.json)
    - fallback su cache esterna U21/U23 (file JSON prodotto da ETL web)

    Novità:
    - Estrazione età robusta (age, birth_year, dob YYYY-MM-DD / DD/MM/YYYY / YYYY)
    - U21 su tutti i ruoli (o per ruolo se richiesto)
    - Fallback automatico U23
    - Se ancora vuoto → usa cache esterna (EXTERNAL_YOUTH_CACHE)
    """

    def __init__(self) -> None:
        LOG.info("Initializing FantacalcioAssistant...")

        self.enable_web_fallback: bool = _env_true(os.getenv("ENABLE_WEB_FALLBACK", "0"))
        LOG.info("[Assistant] ENABLE_WEB_FALLBACK raw='%s' parsed=%s",
                 os.getenv("ENABLE_WEB_FALLBACK", "0"), self.enable_web_fallback)

        self.roster_json_path: str = os.getenv("ROSTER_JSON_PATH", "./season_roster.json")
        LOG.info("[Assistant] ROSTER_JSON_PATH=%s", self.roster_json_path)

        self.external_youth_cache_path: str = os.getenv(
            "EXTERNAL_YOUTH_CACHE", "./cache/under21_cache.json"
        )
        LOG.info("[Assistant] EXTERNAL_YOUTH_CACHE=%s", self.external_youth_cache_path)

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
        self.external_youth_cache: List[Dict[str, Any]] = self._load_external_youth_cache()

        LOG.info("[Assistant] Inizializzazione completata")

    # ---------------------------
    # Prompt
    # ---------------------------
    def _load_prompt_json(self, path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            LOG.error("[Assistant] Errore caricamento prompt: %s", e)
            return ("Sei un assistente fantacalcio. Rispondi in modo conciso e pratico in italiano; "
                    "non inventare dati e dichiara incertezza se mancano fonti.")
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
        return ("Sei un assistente fantacalcio. Rispondi in modo conciso e pratico in italiano; "
                "non inventare dati e dichiara incertezza se mancano fonti.")

    # ---------------------------
    # Roster
    # ---------------------------
    def _load_and_normalize_roster(self, path: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        if not os.path.exists(path):
            LOG.warning("[Assistant] Roster file non trovato: %s", path)
            return out
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            LOG.error("[Assistant] Errore apertura roster: %s", e)
            return out

        if not isinstance(data, list):
            LOG.warning("[Assistant] roster non è una lista, lo ignoro")
            return out

        cnt_total = len(data)
        for item in data:
            if not isinstance(item, dict):
                continue
            name = (item.get("name") or item.get("player") or "").strip()
            role = (item.get("role") or item.get("position") or "").strip().upper()
            team = (item.get("team") or item.get("club") or "").strip()

            birth_year = item.get("birth_year") or item.get("year_of_birth")
            dob = item.get("dob") or item.get("date_of_birth") or item.get("birthdate")
            age = item.get("age") or item.get("eta") or item.get("Age")

            price = item.get("price") or item.get("cost")
            fm = item.get("fantamedia") or item.get("avg")

            out.append({
                "name": name, "role": role, "team": team,
                "birth_year": birth_year, "dob": dob, "age": age,
                "price": price, "fantamedia": fm
            })

        LOG.info("[Assistant] Roster normalizzato: %d/%d record utili", len(out), cnt_total)
        return out

    # ---------------------------
    # External youth cache
    # ---------------------------
    def _load_external_youth_cache(self) -> List[Dict[str, Any]]:
        path = self.external_youth_cache_path
        if not os.path.exists(path):
            LOG.warning("[Assistant] Cache esterno U21 non trovato: %s", path)
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                LOG.info("[Assistant] Youth cache caricato: %d record", len(data))
                return data
            LOG.warning("[Assistant] Youth cache non-list, ignorato")
            return []
        except Exception as e:
            LOG.error("[Assistant] Errore lettura youth cache: %s", e)
            return []

    # ---------------------------
    # Helpers età / ruolo
    # ---------------------------
    def _extract_age_years(self, rec: Dict[str, Any], ref_date: Optional[datetime] = None) -> Optional[int]:
        if ref_date is None:
            ref_date = datetime(2025, 8, 1)  # stagione 2025-26 approx

        # age diretto
        for k in ("age", "eta", "age_years", "Age"):
            v = rec.get(k)
            iv = _safe_int(v)
            if iv is not None and 0 < iv < 60:
                return iv

        # birth_year
        for k in ("birth_year", "year_of_birth"):
            by = _safe_int(rec.get(k))
            if by and 1900 < by <= ref_date.year:
                return ref_date.year - by

        # date strings
        for k in ("dob", "date_of_birth", "birthdate"):
            s = str(rec.get(k) or "").strip()
            if not s:
                continue
            # YYYY-MM-DD
            m = re.match(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})\s*$", s)
            if m:
                y = int(m.group(1))
                if 1900 < y <= ref_date.year:
                    return ref_date.year - y
            # DD/MM/YYYY
            m = re.match(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$", s)
            if m:
                y = int(m.group(3))
                if 1900 < y <= ref_date.year:
                    return ref_date.year - y
            # YYYY
            m = re.match(r"^\s*(\d{4})\s*$", s)
            if m:
                y = int(m.group(1))
                if 1900 < y <= ref_date.year:
                    return ref_date.year - y

        return None

    def _role_bucket(self, raw_role: str) -> str:
        r = (raw_role or "").strip().upper()
        if not r:
            return ""
        if r in {"P", "GK", "POR"}:
            return "P"
        if r in {"D", "DEF", "DC", "CB", "RB", "LB", "TD", "TS", "BR"}:
            return "D"
        if r in {"C", "CM", "MED", "M", "MEZ", "RM", "LM", "CC", "TQ", "AM", "TRE"}:
            return "C"
        if r in {"A", "ATT", "ST", "SS", "PUN", "EST", "W", "LW", "RW"}:
            return "A"
        if r and r[0] in {"P", "D", "C", "A"}:
            return r[0]
        return ""

    # ---------------------------
    # KM fetch
    # ---------------------------
    def _km_fetch_players(self, seasons: Optional[List[str]] = None, limit: int = 5000) -> List[Dict[str, Any]]:
        seasons = seasons or ["2025-26", "2024-25"]
        collected: List[Dict[str, Any]] = []

        where = {"$and": [
            {"type": {"$in": ["player_info", "current_player"]}},
            {"season": {"$in": seasons}}
        ]}
        include = ["metadatas"]

        try:
            # firma “nuova” vista in alcuni log
            res = self.km.search_knowledge(text=None, where=where, n_results=limit, include=include)
            metas = res.get("metadatas") or []
        except TypeError:
            # firma “vecchia”
            res = self.km.search_knowledge(where=where, limit=limit, include=include)  # type: ignore
            metas = res.get("metadatas") or []
        except Exception as e:
            LOG.error("[Assistant] _km_fetch_players error: %s", e)
            metas = []

        for m in metas:
            if not isinstance(m, dict):
                continue
            name = (m.get("name") or m.get("player") or "").strip()
            role = (m.get("role") or m.get("position") or "").strip().upper()
            team = (m.get("team") or m.get("club") or "").strip()
            birth_year = m.get("birth_year") or m.get("year_of_birth")
            dob = m.get("dob") or m.get("date_of_birth") or m.get("birthdate")
            age = m.get("age") or m.get("eta")
            price = m.get("price") or m.get("cost")
            fm = m.get("fantamedia") or m.get("avg")

            collected.append({
                "name": name, "role": role, "team": team,
                "birth_year": birth_year, "dob": dob, "age": age,
                "price": price, "fantamedia": fm
            })

        LOG.info("[Assistant] _km_fetch_players: %d record", len(collected))
        return collected

    # ---------------------------
    # Merge roster + KM
    # ---------------------------
    def _collect_all_players(self) -> List[Dict[str, Any]]:
        all_players = list(self.roster)
        try:
            all_players.extend(self._km_fetch_players())
        except Exception as e:
            LOG.error("[Assistant] errore nel fetch KM: %s", e)

        seen = set()
        deduped: List[Dict[str, Any]] = []
        for p in all_players:
            if not isinstance(p, dict):
                continue
            name = (p.get("name") or "").strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(p)
        return deduped

    # ---------------------------
    # Fallback cache esterno (U21/U23)
    # ---------------------------
    def _fallback_youth_from_cache(self, max_age: int, target_buckets: Optional[List[str]], k: int) -> List[Dict[str, Any]]:
        pool = self.external_youth_cache or []
        out: List[Dict[str, Any]] = []

        for p in pool:
            if not isinstance(p, dict):
                continue
            role_bucket = self._role_bucket(p.get("role") or p.get("position") or "")
            if target_buckets and role_bucket not in target_buckets:
                continue

            # accetto età pronta o calcolo da birth_year/dob
            age = None
            if p.get("age") is not None:
                age = _safe_int(p.get("age"))
            if age is None:
                age = self._extract_age_years(p)

            if age is None or age > max_age:
                continue

            out.append({
                "name": p.get("name"),
                "team": p.get("team") or p.get("club"),
                "role_bucket": role_bucket or "",
                "age": age,
                "fantamedia": _safe_float(p.get("fantamedia"), 0.0),
                "price": _safe_float(p.get("price"), 0.0),
                "_source": "external_cache"
            })

        out.sort(key=lambda x: (-_safe_float(x.get("fantamedia"), 0.0),
                                _safe_float(x.get("price"), 9999.0),
                                (x.get("name") or "")))
        return out[:k]

    # ---------------------------
    # Suggeritori giovani (roster+KM)
    # ---------------------------
    def _suggest_young(self, max_age: int, target_buckets: Optional[List[str]] = None, k: int = 3) -> List[Dict[str, Any]]:
        pool = self._collect_all_players()
        candidates: List[Dict[str, Any]] = []

        for p in pool:
            role_bucket = self._role_bucket(p.get("role") or "")
            if target_buckets and role_bucket not in target_buckets:
                continue
            age = self._extract_age_years(p)
            if age is None or age > max_age:
                continue
            candidates.append({
                "name": p.get("name"),
                "team": p.get("team"),
                "role_bucket": role_bucket or "",
                "age": age,
                "fantamedia": _safe_float(p.get("fantamedia"), 0.0),
                "price": _safe_float(p.get("price"), 0.0),
                "_source": "local_or_km"
            })

        candidates.sort(key=lambda x: (-_safe_float(x.get("fantamedia"), 0.0),
                                       _safe_float(x.get("price"), 9999.0),
                                       (x.get("name") or "")))
        return candidates[:k]

    # ---------------------------
    # LLM (fallback generico)
    # ---------------------------
    def _llm_complete(self, user_text: str, context_messages: Optional[List[Dict[str, str]]] = None) -> str:
        if not self.openai_api_key:
            return ("⚠️ Servizio AI temporaneamente non disponibile. "
                    "Configura OPENAI_API_KEY e riavvia.")
        messages = [{"role": "system", "content": self.system_prompt}]
        if context_messages:
            messages.extend(context_messages)
        messages.append({"role": "user", "content": user_text})
        headers = {"Authorization": f"Bearer {self.openai_api_key}", "Content-Type": "application/json"}
        payload = {"model": self.openai_model, "temperature": self.openai_temperature,
                   "max_tokens": self.openai_max_tokens, "messages": messages}
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post("https://api.openai.com/v1/chat/completions",
                                   headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            LOG.error("[Assistant] Errore OpenAI: %s", e)
            return "⚠️ Servizio momentaneamente non disponibile. Riprova tra poco."

    # ---------------------------
    # Intent routing
    # ---------------------------
    def _extract_requested_k(self, user_text: str, default: int = 3) -> int:
        m = re.search(r"\b(\d{1,2})\b", user_text)
        if not m:
            return default
        try:
            val = int(m.group(1))
            return max(1, min(10, val))
        except Exception:
            return default

    def _format_young_answer(self, items: List[Dict[str, Any]], label: str, age_cap: int) -> str:
        if not items:
            return (f"Nei miei dati non trovo profili **Under {age_cap}** con età certa per questo filtro. "
                    "Se vuoi, posso proporti alternative senza filtro età.")
        lines = []
        for p in items:
            bits = [f"**{p.get('name')}**"]
            team = p.get("team")
            if team:
                bits.append(f"({team})")
            meta = []
            if p.get("age") is not None:
                meta.append(f"{int(p['age'])} anni")
            if p.get("fantamedia"):
                meta.append(f"FM {_safe_float(p['fantamedia']):.2f}")
            if p.get("price"):
                meta.append(f"€ {int(_safe_float(p['price']))}")
            src = p.get("_source")
            if src == "external_cache":
                meta.append("fonte: cache esterna")
            if meta:
                bits.append(" — " + ", ".join(meta))
            lines.append(" ".join(bits))
        return f"Ecco {label} Under {age_cap}:\n- " + "\n- ".join(lines)

    def get_response(self, user_text: str, mode: str = "classic",
                     context: Optional[Dict[str, Any]] = None) -> str:
        lt = user_text.lower()
        u21_trigger = any(x in lt for x in ["under 21", "under21", "u21", "under-21"])

        if u21_trigger:
            k = self._extract_requested_k(user_text, default=3)
            want_def = any(x in lt for x in ["difensori", "difensore", "defender", "difensor"])
            want_mid = any(x in lt for x in ["centrocampisti", "centrocampista", "midfielder", "mezz", "mediano"])
            want_fwd = any(x in lt for x in ["attaccanti", "attaccante", "forward", "punta", "esterno offensivo"])
            bucket = None
            if want_def:
                bucket = ["D"]
            elif want_mid:
                bucket = ["C"]
            elif want_fwd:
                bucket = ["A"]

            # 1) U21 locali/KM
            items = self._suggest_young(max_age=20, target_buckets=bucket, k=k)
            if items:
                return self._format_young_answer(items, f"{k} profili", 21)

            # 2) U23 locali/KM (fallback leggero)
            items = self._suggest_young(max_age=22, target_buckets=bucket, k=k)
            if items:
                return ("Non trovo U21 con età certa per quel filtro. " +
                        self._format_young_answer(items, f"{k} alternative", 23))

            # 3) Fallback cache esterno se abilitato
            if self.enable_web_fallback and self.external_youth_cache:
                ext = self._fallback_youth_from_cache(max_age=20, target_buckets=bucket, k=k)
                if ext:
                    return ("(Fallback esterno) " +
                            self._format_young_answer(ext, f"{k} profili", 21))

                ext = self._fallback_youth_from_cache(max_age=22, target_buckets=bucket, k=k)
                if ext:
                    return ("(Fallback esterno) Non ho U21 certi. " +
                            self._format_young_answer(ext, f"{k} alternative", 23))

            # 4) Nessun dato
            return ("Non ho Under 21 affidabili con età nota per questo filtro. "
                    "Se vuoi, abilita/aggiorna il cache esterno (EXTERNAL_YOUTH_CACHE) o togli il vincolo di età.")

        # fallback generico: LLM
        return self._llm_complete(user_text, context_messages=[])
