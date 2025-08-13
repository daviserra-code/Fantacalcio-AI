# -*- coding: utf-8 -*-
import os
import re
import json
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

REF_YEAR = int(os.getenv("REF_YEAR", "2025"))

def _env_true(val: Optional[str]) -> bool:
    if val is None:
        return False
    return str(val).strip().lower() in {"1", "true", "yes", "y", "on"}

# ==============================
# Normalizzazione & alias
# ==============================
TEAM_ALIASES = {
    "como 1907": "como",
    "ss lazio": "lazio",
    "s.s. lazio": "lazio",
    "juventus fc": "juventus",
    "fc internazionale": "inter",
    "inter milano": "inter",
    "fc internazionale milano": "inter",
    "ac milan": "milan",
    "hellas verona": "verona",
    "udinese calcio": "udinese",
    "ac monza": "monza",
    "as roma": "roma",
    "us lecce": "lecce",
    "atalanta bc": "atalanta",
    "fc torino": "torino",
    "parma calcio": "parma",
    "venezia fc": "venezia",
    "empoli fc": "empoli",
    "genoa cfc": "genoa",
    "bologna fc": "bologna",
    "fiorentina ac": "fiorentina",
}

SERIE_A_WHITELIST = set([
    "atalanta","bologna","cagliari","como","empoli","fiorentina","genoa","inter",
    "juventus","lazio","lecce","milan","monza","napoli","parma","roma","torino",
    "udinese","venezia","verona",
])

def _norm_text(s: str) -> str:
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _norm_team(team: str) -> str:
    t = _norm_text(team)
    t = re.sub(r"\b(foot(ball)?|club|fc|ac|ss|usc|cfc|calcio|asd|ssd)\b", "", t)
    t = re.sub(r"\b(18|19|20)\d{2}\b", "", t).strip()
    t = re.sub(r"\s+", " ", t)
    if t in TEAM_ALIASES:
        t = TEAM_ALIASES[t]
    return t or _norm_text(team)

def _norm_name(name: str) -> str:
    return _norm_text(name)

def _age_key(name: str, team: str) -> str:
    return f"{_norm_name(name)}@@{_norm_team(team)}"

def _valid_birth_year(by: Optional[int]) -> Optional[int]:
    try:
        by = int(by)
    except Exception:
        return None
    if 1975 <= by <= 2010:
        return by
    return None

def _parse_first_int(s: str) -> Optional[int]:
    m = re.search(r"\b(\d{1,4})\b", s or "")
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None

def _to_float(x: Any) -> Optional[float]:
    """Converte stringhe tipo '€ 45', '45 crediti', '6,85', '--' in float."""
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().lower()
    if not s or s in {"n/d", "na", "nd", "—", "-", ""}:
        return None
    s = s.replace("€", " ").replace("eur", " ").replace("euro", " ")
    s = s.replace("crediti", " ").replace("credits", " ")
    s = s.replace("pt", " ").replace("pts", " ")
    s = s.replace(",", ".")
    m = re.search(r"-?\d+(\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None

def _formation_from_text(text: str) -> Optional[Dict[str, int]]:
    m = re.search(r"\b([0-5])\s*-\s*([0-5])\s*-\s*([0-5])\b", text or "")
    if not m:
        return None
    d, c, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if d + c + a != 10:
        return None
    return {"P": 1, "D": d, "C": c, "A": a}

def _first_key(d: Dict[str, Any], keys: List[str]) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, "", "—", "-"):
            return d[k]
    return None

class FantacalcioAssistant:
    """
    Assistente data-driven:
    - filtra stagione/club Serie A;
    - quick actions senza LLM (niente nomi inventati);
    - parser robusto prezzo/FM.
    """
    def __init__(self) -> None:
        LOG.info("Initializing FantacalcioAssistant...")
        self.enable_web_fallback: bool = _env_true(os.getenv("ENABLE_WEB_FALLBACK", "0"))
        LOG.info("[Assistant] ENABLE_WEB_FALLBACK raw='%s' parsed=%s",
                 os.getenv("ENABLE_WEB_FALLBACK", "0"), self.enable_web_fallback)

        self.roster_json_path: str = os.getenv("ROSTER_JSON_PATH", "./season_roster.json")
        LOG.info("[Assistant] ROSTER_JSON_PATH=%s", self.roster_json_path)

        self.openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
        self.openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.openai_temperature: float = float(os.getenv("OPENAI_TEMPERATURE", "0.20"))
        self.openai_max_tokens: int = int(os.getenv("OPENAI_MAX_TOKENS", "600"))
        LOG.info("[Assistant] OpenAI model=%s temp=%.2f max_tokens=%d",
                 self.openai_model, self.openai_temperature, self.openai_max_tokens)

        self.system_prompt: str = self._load_prompt_json("./prompt.json")
        self.km: KnowledgeManager = KnowledgeManager()
        LOG.info("[Assistant] KnowledgeManager attivo")

        self.season_filter = os.getenv("SEASON_FILTER", "").strip()  # es. "2025-26"

        # Età (opzionale)
        self.age_index_path = os.getenv("AGE_INDEX_PATH", "./data/age_index.cleaned.json")
        self.age_overrides_path = os.getenv("AGE_OVERRIDES_PATH", "./data/age_overrides.json")
        self.age_index: Dict[str, int] = self._load_age_index(self.age_index_path)
        self.overrides: Dict[str, int] = self._load_overrides(self.age_overrides_path)

        # Roster
        self.roster: List[Dict[str, Any]] = self._load_and_normalize_roster(self.roster_json_path)
        self._apply_ages_to_roster()
        self._make_filtered_roster()  # <— pool già ripulito per stagione/club
        LOG.info("[Assistant] Inizializzazione completata")

    # -------- Prompt --------
    def _load_prompt_json(self, path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            LOG.error("[Assistant] Errore caricamento prompt: %s", e)
            return "Sei un assistente fantacalcio. Rispondi in italiano, conciso, senza inventare dati."
        if isinstance(cfg, dict):
            if "system" in cfg and isinstance(cfg["system"], dict):
                sys = cfg["system"]
                name = sys.get("name", "fantacalcio_system")
                content = sys.get("content", "")
                style = sys.get("style", "")
                language = sys.get("language", "it")
                return f"[{name}] ({language}, {style})\n{content}".strip()
            if "prompt" in cfg and isinstance(cfg["prompt"], str):
                return cfg["prompt"]
        return "Sei un assistente fantacalcio. Rispondi in italiano, conciso, senza inventare dati."

    # -------- Età --------
    def _load_age_index(self, path: str) -> Dict[str, int]:
        data: Dict[str, int] = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            items = raw.items() if isinstance(raw, dict) else []
            for k, v in items:
                by = v.get("birth_year") if isinstance(v, dict) else v
                by = _valid_birth_year(by)
                if by is None:
                    continue
                name, team = k, ""
                if "@@" in k: name, team = k.split("@@", 1)
                elif "|" in k: name, team = k.split("|", 1)
                data[_age_key(name, team)] = by
        except FileNotFoundError:
            LOG.info("[Assistant] age_index non trovato: %s (ok)", path)
        except Exception as e:
            LOG.error("[Assistant] errore lettura age_index %s: %s", path, e)
        LOG.info("[Assistant] age_index caricato: %d chiavi", len(data))
        return data

    def _load_overrides(self, path: str) -> Dict[str, int]:
        out: Dict[str, int] = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                for k, v in raw.items():
                    by = _valid_birth_year(v.get("birth_year") if isinstance(v, dict) else v)
                    if by is None:
                        continue
                    name, team = k, ""
                    if "@@" in k: name, team = k.split("@@", 1)
                    elif "|" in k: name, team = k.split("|", 1)
                    out[_age_key(name, team)] = by
        except FileNotFoundError:
            LOG.info("[Assistant] overrides non trovato: %s (opzionale)", path)
        except Exception as e:
            LOG.error("[Assistant] errore lettura overrides %s: %s", path, e)
        LOG.info("[Assistant] overrides caricato: %d chiavi", len(out))
        return out

    # -------- Roster --------
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
            LOG.warning("[Assistant] roster non è una lista")
            return roster

        for item in data:
            if not isinstance(item, dict):
                continue
            name = (item.get("name") or item.get("player") or "").strip()
            role = (item.get("role") or item.get("position") or "").strip().upper()
            team = (item.get("team") or item.get("club") or "").strip()
            season = (item.get("season") or item.get("stagione") or item.get("year") or "").strip()

            price_raw = _first_key(item, ["price","cost","prezzo","quotazione","valore","initial_price","list_price","asta_price"])
            fm_raw    = _first_key(item, ["fantamedia","fm","fanta_media","average","avg","media","media_voto"])

            price = _to_float(price_raw)
            fm    = _to_float(fm_raw)

            roster.append({
                "name": name,
                "role": role,
                "team": team,
                "season": season,
                "birth_year": item.get("birth_year") or item.get("year_of_birth"),
                "price": price_raw,
                "fantamedia": fm_raw,
                "_price": price,
                "_fm": fm,
            })
        LOG.info("[Assistant] Roster normalizzato: %d/%d record utili", len(roster), len(data))
        return roster

    def _apply_ages_to_roster(self) -> None:
        name_counts: Dict[str, int] = {}
        for p in self.roster:
            nn = _norm_name(p.get("name", ""))
            if nn:
                name_counts[nn] = name_counts.get(nn, 0) + 1

        enriched = 0
        for p in self.roster:
            by = _valid_birth_year(p.get("birth_year"))
            if by is None:
                k = _age_key(p.get("name", ""), p.get("team", ""))
                by = self.overrides.get(k) or self.age_index.get(k)
                if _valid_birth_year(by) is None and name_counts.get(_norm_name(p.get("name","")), 0) == 1:
                    nn = _norm_name(p.get("name",""))
                    for kk, v in self.overrides.items():
                        if kk.startswith(nn + "@@"):
                            by = v; break
                    if _valid_birth_year(by) is None:
                        for kk, v in self.age_index.items():
                            if kk.startswith(nn + "@@"):
                                by = v; break
            by = _valid_birth_year(by)
            if by is not None:
                p["birth_year"] = by
                enriched += 1
        LOG.info("[Assistant] Età arricchite su %d record", enriched)

    def _team_ok(self, team: str) -> bool:
        t = _norm_team(team)
        return t in SERIE_A_WHITELIST

    def _make_filtered_roster(self) -> None:
        out = []
        for p in self.roster:
            if not self._team_ok(p.get("team","")):
                continue
            if self.season_filter:
                s = (p.get("season") or "").strip()
                if s != self.season_filter:
                    continue
            by = _valid_birth_year(p.get("birth_year"))
            if by is not None and (REF_YEAR - by) > 39:
                continue
            out.append(p)
        self.filtered_roster: List[Dict[str, Any]] = out
        LOG.info("[Assistant] Pool filtrato: %d record (stagione=%s)", len(out), self.season_filter or "ANY")

    # -------- Helpers ruolo --------
    def _is_defender(self, role: str) -> bool:
        return (role or "").upper().startswith("D")
    def _is_mid(self, role: str) -> bool:
        return (role or "").upper().startswith("C")
    def _is_forward(self, role: str) -> bool:
        return (role or "").upper().startswith("A")
    def _is_goalie(self, role: str) -> bool:
        return (role or "").upper().startswith("P")
    def _age_from_birth_year(self, birth_year: Optional[int]) -> Optional[int]:
        try:
            by = int(birth_year)
            return REF_YEAR - by
        except Exception:
            return None

    def _pool_by_role(self, role_letter: str) -> List[Dict[str, Any]]:
        pool_src = getattr(self, "filtered_roster", self.roster)
        def role_ok(r):
            if role_letter == "D": return self._is_defender(r)
            if role_letter == "C": return self._is_mid(r)
            if role_letter == "A": return self._is_forward(r)
            if role_letter == "P": return self._is_goalie(r)
            return True

        pool: List[Dict[str, Any]] = []
        for p in pool_src:
            if role_ok(p.get("role","")):
                pool.append(p)
        return pool

    # -------- Selettori --------
    def _select_under(self, role_letter: str, max_age: int = 21, take: int = 3) -> List[Dict[str, Any]]:
        pool = []
        for p in self._pool_by_role(role_letter):
            age = self._age_from_birth_year(p.get("birth_year"))
            if age is None:
                continue
            if age <= max_age:
                pool.append(p)
        def sort_key(x):
            fm = x.get("_fm") or 0.0
            price = x.get("_price") if isinstance(x.get("_price"), (int,float)) else 9_999.0
            return (-fm, price)
        pool.sort(key=sort_key)
        return pool[:take]

    def _select_top_by_budget(self, role_letter: str, budget: int, take: int = 8
                              ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        within: List[Dict[str, Any]] = []
        no_price_but_good_fm: List[Dict[str, Any]] = []

        tmp: List[Dict[str, Any]] = []
        for p in self._pool_by_role(role_letter):
            fm = p.get("_fm"); pr = p.get("_price")
            if isinstance(fm,(int,float)) and fm > 0 and isinstance(pr,(int,float)) and 0 < pr <= float(budget):
                q = dict(p); q["_value_ratio"] = fm / max(pr, 1.0); tmp.append(q)
        tmp.sort(key=lambda x: (-x["_value_ratio"], -(x.get("_fm") or 0.0), x.get("_price") or 9_999.0))
        within = tmp[:take]

        if len(within) < take:
            tmp2=[]
            for p in self._pool_by_role(role_letter):
                if p.get("_price") is None:
                    fm = p.get("_fm")
                    if isinstance(fm,(int,float)) and fm > 0:
                        tmp2.append(p)
            tmp2.sort(key=lambda x: -(x.get("_fm") or 0.0))
            no_price_but_good_fm = tmp2[: max(0, take - len(within))]
        return within, no_price_but_good_fm

    def _select_top_role(self, role_letter: str, take: int = 10, strategy: str = "value",
                         max_price: Optional[float] = None, min_fm: float = 0.0) -> List[Dict[str, Any]]:
        pool=[]
        for p in self._pool_by_role(role_letter):
            fm = p.get("_fm")
            if not isinstance(fm,(int,float)) or fm < min_fm: continue
            pr = p.get("_price")
            if max_price is not None:
                if not isinstance(pr,(int,float)) or pr > max_price: continue
            q = dict(p)
            q["_value_ratio"] = fm / max((pr if isinstance(pr,(int,float)) else 9_999.0), 1.0)
            pool.append(q)
        if strategy == "fm":
            pool.sort(key=lambda x: -(x.get("_fm") or 0.0))
        else:
            pool.sort(key=lambda x: (-x.get("_value_ratio",0.0), -(x.get("_fm") or 0.0), x.get("_price") if isinstance(x.get("_price"),(int,float)) else 9_999.0))
        return pool[:take]

    # -------- Builder XI --------
    def _build_formation(self, formation: Dict[str,int], budget: int) -> Dict[str, Any]:
        base = {"P": 0.06, "D": 0.24, "C": 0.38, "A": 0.32}
        slots = formation.copy()
        base_sum = base["D"]*3 + base["C"]*4 + base["A"]*3 + base["P"]
        weights = {}
        for r in ["P","D","C","A"]:
            std = {"P":1,"D":3,"C":4,"A":3}[r]
            w = (base[r]/base_sum) * (slots[r]/std if std>0 else 1.0)
            weights[r] = w
        s = sum(weights.values())
        for r in weights:
            weights[r] = weights[r]/s if s>0 else 0.25

        role_budget = {r: int(round(budget*weights[r])) for r in weights}
        diff = budget - sum(role_budget.values())
        if diff != 0:
            role_budget["C"] += diff

        picks: Dict[str,List[Dict[str,Any]]] = {"P":[], "D":[], "C":[], "A":[]}
        used = set()

        def pick_for_role(r: str):
            need = slots[r]; cap = max(1, role_budget[r]); cap_slot = cap/need
            pool = self._select_top_role(r, take=300, strategy="value")
            chosen=[]
            for p in pool:
                if len(chosen) >= need: break
                if p.get("name") in used: continue
                pr = p.get("_price")
                if isinstance(pr,(int,float)) and pr <= cap_slot*1.10:
                    chosen.append(p); used.add(p.get("name"))
            if len(chosen) < need:
                for p in pool:
                    if len(chosen) >= need: break
                    if p.get("name") in used: continue
                    chosen.append(p); used.add(p.get("name"))
            picks[r] = chosen[:need]

        for r in ["P","D","C","A"]:
            pick_for_role(r)

        def total_cost():
            s = 0.0
            for r in picks:
                for p in picks[r]:
                    pr = p.get("_price")
                    if isinstance(pr,(int,float)):
                        s += pr
            return s

        cost = total_cost()
        if cost > budget:
            for _ in range(200):
                if cost <= budget: break
                target_r, target_p, target_idx, target_cost = None, None, -1, -1.0
                for r in picks:
                    for i, p in enumerate(picks[r]):
                        pr = p.get("_price") if isinstance(p.get("_price"),(int,float)) else 0.0
                        if pr > target_cost:
                            target_r, target_p, target_idx, target_cost = r, p, i, pr
                if target_p is None: break
                pool = self._select_top_role(target_r, take=400, strategy="value")
                replaced = False
                for cand in reversed(pool):
                    if cand.get("name") in used: continue
                    pr_c = cand.get("_price")
                    if isinstance(pr_c,(int,float)) and pr_c < target_cost:
                        used.remove(target_p.get("name")); used.add(cand.get("name"))
                        picks[target_r][target_idx] = cand
                        cost = total_cost(); replaced = True; break
                if not replaced: break

        leftover = max(0, budget - total_cost())
        return {"picks": picks, "budget_roles": role_budget, "leftover": leftover}

    # -------- Risposte --------
    def _answer_under21(self, role_letter: str) -> str:
        top = self._select_under(role_letter=role_letter, max_age=21, take=3)
        if not top:
            return ("Non ho profili U21 affidabili per questo ruolo nei dati locali "
                    "(serve età certa). Prova senza vincolo d’età o indica un club.")
        lines=[]
        for p in top:
            name = p.get("name") or "N/D"; team = p.get("team") or "—"
            age = self._age_from_birth_year(p.get("birth_year"))
            fm = p.get("_fm"); price = p.get("_price")
            meta=[]
            if age is not None: meta.append(f"{age} anni")
            if isinstance(fm,(int,float)): meta.append(f"FM {fm:.2f}")
            if isinstance(price,(int,float)): meta.append(f"€ {int(round(price))}")
            elif p.get("price"): meta.append(f"€ {p.get('price')}")
            line = f"**{name}** ({team})"
            if meta: line += " — " + ", ".join(meta)
            lines.append(line)
        return "Ecco i profili Under 21 richiesti:\n- " + "\n- ".join(lines)

    def _answer_top_attackers_by_budget(self, budget: int) -> str:
        strict, fm_only = self._select_top_by_budget("A", budget, take=8)
        sections=[]
        if strict:
            lines=[]
            for p in strict:
                name=p.get("name") or "N/D"; team=p.get("team") or "—"
                fm=p.get("_fm"); pr=p.get("_price"); vr=p.get("_value_ratio")
                bits=[]
                if isinstance(fm,(int,float)): bits.append(f"FM {fm:.2f}")
                if isinstance(pr,(int,float)): bits.append(f"€ {int(round(pr))}")
                if isinstance(vr,(int,float)): bits.append(f"Q/P {(vr*100):.1f}%")
                lines.append(f"- **{name}** ({team}) — " + ", ".join(bits))
            sections.append(f"🎯 **Entro {budget} crediti (ordine Q/P)**\n" + "\n".join(lines))
        if fm_only:
            lines=[]
            for p in fm_only:
                name=p.get("name") or "N/D"; team=p.get("team") or "—"; fm=p.get("_fm")
                bits=[]
                if isinstance(fm,(int,float)): bits.append(f"FM {fm:.2f}")
                bits.append("prezzo N/D")
                lines.append(f"- **{name}** ({team}) — " + ", ".join(bits))
            sections.append("ℹ️ **Prezzo non disponibile ma FM alta (candidati interessanti):**\n" + "\n".join(lines))
        if not sections:
            pool = [p for p in self._pool_by_role("A") if isinstance(p.get("_fm"),(int,float)) and p["_fm"]>0]
            pool.sort(key=lambda x: -(x.get("_fm") or 0.0))
            if pool:
                lines=[]
                for p in pool[:8]:
                    name=p.get("name") or "N/D"; team=p.get("team") or "—"
                    fm=p.get("_fm"); pr=p.get("_price")
                    bits=[]
                    if isinstance(fm,(int,float)): bits.append(f"FM {fm:.2f}")
                    if isinstance(pr,(int,float)): bits.append(f"€ {int(round(pr))}")
                    else: bits.append("prezzo N/D")
                    lines.append(f"- **{name}** ({team}) — " + ", ".join(bits))
                sections.append("📈 **Migliori per FM (prezzo spesso mancante nei dati):**\n" + "\n".join(lines))
        return "\n\n".join(sections)

    def _answer_build_xi(self, text: str) -> str:
        formation = _formation_from_text(text)
        budget = _parse_first_int(text) or 500
        if not formation:
            return "Specificami una formazione tipo 5-3-2 o 4-3-3."
        res = self._build_formation(formation, budget)
        picks = res["picks"]; leftover = res["leftover"]; rb = res["budget_roles"]

        def fmt_role(r: str, label: str) -> str:
            if not picks[r]: return f"**{label}:** —"
            rows=[]
            for p in picks[r]:
                fm=p.get("_fm"); pr=p.get("_price")
                bits=[]
                if isinstance(fm,(int,float)): bits.append(f"FM {fm:.2f}")
                if isinstance(pr,(int,float)): bits.append(f"€ {int(round(pr))}")
                elif p.get("price"): bits.append(f"€ {p.get('price')}")
                rows.append(f"- **{p.get('name','N/D')}** ({p.get('team','—')}) — " + ", ".join(bits))
            return f"**{label}:**\n" + "\n".join(rows)

        tot_cost = 0.0
        for r in picks:
            for p in picks[r]:
                pr = p.get("_price")
                if isinstance(pr,(int,float)):
                    tot_cost += pr

        parts = []
        parts.append(f"📋 **Formazione {formation['D']}-{formation['C']}-{formation['A']}** (budget: {budget} crediti)")
        parts.append(f"Allocazione ruoli: P≈{rb['P']} • D≈{rb['D']} • C≈{rb['C']} • A≈{rb['A']}")
        parts.append(fmt_role("P", "Portiere"))
        parts.append(fmt_role("D", "Difensori"))
        parts.append(fmt_role("C", "Centrocampisti"))
        parts.append(fmt_role("A", "Attaccanti"))
        parts.append(f"Totale stimato: **{int(round(tot_cost))}** crediti • Avanzo: **{int(round(leftover))}**")
        parts.append("_Criterio: rapporto qualità/prezzo (FM/prezzo) su pool stagione Serie A filtrato._")
        return "\n\n".join(parts)

    def _answer_asta_strategy(self, text: str) -> str:
        n_part = _parse_first_int(text) or 8
        budget = 500
        base = {"P": 0.06, "D": 0.24, "C": 0.38, "A": 0.32}

        def preview(rows, k=3):
            out=[]
            for p in rows[:k]:
                fm=p.get("_fm"); pr=p.get("_price"); bits=[]
                if isinstance(fm,(int,float)): bits.append(f"FM {fm:.2f}")
                if isinstance(pr,(int,float)): bits.append(f"€ {int(round(pr))}")
                out.append(f"- **{p.get('name','N/D')}** ({p.get('team','—')}) — " + ", ".join(bits))
            return "\n".join(out) if out else "—"

        top_p = self._select_top_role("P", take=5, strategy="value")
        top_d = self._select_top_role("D", take=7, strategy="value")
        top_c = self._select_top_role("C", take=10, strategy="value")
        top_a = self._select_top_role("A", take=7, strategy="value")

        text_out = []
        text_out.append(f"🧭 **Strategia Asta (Classic, {n_part} partecipanti)**")
        text_out.append("Ripartizione budget consigliata (dati locali, stagione filtrata):")
        text_out.append(f"- P **{int(budget*base['P'])}** • D **{int(budget*base['D'])}** • C **{int(budget*base['C'])}** • A **{int(budget*base['A'])}**")
        text_out.append("**Target per ruolo (top Q/P):**")
        text_out.append("**Portieri**\n" + preview(top_p))
        text_out.append("**Difensori**\n" + preview(top_d))
        text_out.append("**Centrocampisti**\n" + preview(top_c, k=5))
        text_out.append("**Attaccanti**\n" + preview(top_a))
        text_out.append("_Criterio: Q/P (FM/prezzo). Se i prezzi mancano, priorità alla FM._")
        return "\n\n".join(text_out)

    # Mantra/Draft/Superscudetto (proxy classico)
    def _answer_mantra_top_cm_assist(self) -> str:
        rows = self._select_top_role("C", take=8, strategy="fm", min_fm=6.5)
        if not rows:
            return "Non ho centrocampisti con dati sufficienti per una lista affidabile."
        out=[]
        for p in rows:
            bits=[]
            if isinstance(p.get("_fm"),(int,float)): bits.append(f"FM {p['_fm']:.2f}")
            if isinstance(p.get("_price"),(int,float)): bits.append(f"€ {int(round(p['_price']))}")
            out.append(f"- **{p.get('name')}** ({p.get('team')}) — " + ", ".join(bits))
        return "🎯 **Centrocampisti “assist-friendly” (proxy FM)**\n" + "\n".join(out)

    def _answer_clean_sheet_def(self) -> str:
        rows = self._select_top_role("D", take=8, strategy="fm", min_fm=6.3)
        if not rows:
            return "Non ho difensori con dati sufficienti per una lista affidabile."
        out=[]
        for p in rows:
            bits=[]
            if isinstance(p.get("_fm"),(int,float)): bits.append(f"FM {p['_fm']:.2f}")
            if isinstance(p.get("_price"),(int,float)): bits.append(f"€ {int(round(p['_price']))}")
            out.append(f"- **{p.get('name')}** ({p.get('team')}) — " + ", ".join(bits))
        return "🛡️ **Difensori affidabili (proxy clean-sheet: FM)**\n" + "\n".join(out)

    def _answer_draft_snake(self, text: str) -> str:
        n_part = _parse_first_int(text) or 8
        top_all=[]
        for r in ["A","C","D","P"]:
            top_all.extend(self._select_top_role(r, take=12, strategy="fm"))
        top_all.sort(key=lambda x: -(x.get("_fm") or 0.0))
        tier1, tier2, tier3 = top_all[:6], top_all[6:12], top_all[12:18]

        def fmt(rows):
            out=[]
            for p in rows:
                fm = p.get("_fm")
                out.append(f"- **{p.get('name')}** ({p.get('team')}) — FM {fm:.2f}" if isinstance(fm,(int,float)) else f"- **{p.get('name')}** ({p.get('team')})")
            return "\n".join(out) if out else "—"

        return (f"🐍 **Draft Snake ({n_part} partecipanti)**\n"
                f"**TIER 1**:\n{fmt(tier1)}\n\n"
                f"**TIER 2**:\n{fmt(tier2)}\n\n"
                f"**TIER 3**:\n{fmt(tier3)}\n\n"
                "_Se prendi un A top, rientra su C di valore nel secondo giro._")

    def _answer_draft_order_roles(self) -> str:
        return ("📋 **Ordine ruoli consigliato (proxy locale)**\n"
                "1) A top\n2) C alta FM/QP\n3) D affidabili\n4) P solido")

    def _answer_draft_first_rounds(self) -> str:
        rows=[]
        for r in ["A","C","D","P"]:
            rows.extend(self._select_top_role(r, take=4, strategy="fm"))
        rows.sort(key=lambda x: -(x.get("_fm") or 0.0))
        out=[]
        for p in rows[:12]:
            fm = p.get("_fm")
            out.append(f"- **{p.get('name')}** ({p.get('team')}) — FM {fm:.2f}" if isinstance(fm,(int,float)) else f"- **{p.get('name')}** ({p.get('team')})")
        return "🥇 **Prime scelte (prime 2–3 tornate)**\n" + ("\n".join(out) if out else "—")

    def _answer_draft_sleepers(self) -> str:
        sleepers=[]
        for r in ["A","C","D","P"]:
            pool = self._select_top_role(r, take=200, strategy="value")
            prices = [p.get("_price") for p in pool if isinstance(p.get("_price"), (int,float))]
            if not prices:
                continue
            prices_sorted = sorted(prices)
            med = prices_sorted[len(prices_sorted)//2]
            for p in pool:
                pr = p.get("_price")
                if isinstance(pr,(int,float)) and pr <= med:
                    sleepers.append(p)
        sleepers.sort(key=lambda x: (-x.get("_value_ratio",0), -(x.get("_fm") or 0)))
        out=[]
        for p in sleepers[:10]:
            vr = p.get("_value_ratio") or 0.0
            fm = p.get("_fm") or 0.0
            pr = p.get("_price")
            out.append(f"- **{p.get('name')}** ({p.get('team')}) — FM {fm:.2f}, € {int(round(pr)) if isinstance(pr,(int,float)) else 'N/D'}, Q/P {vr*100:.1f}%")
        return "💎 **Sleeper picks (Q/P alto, prezzo ≤ mediana ruolo)**\n" + ("\n".join(out) if out else "—")

    def _answer_supers_formazione(self, text: str) -> str:
        return self._answer_build_xi(text)
    def _answer_supers_rules(self) -> str:
        return ("⭐ **Superscudetto (proxy locale)**\n"
                "- Priorità ad A e C con FM alta.\n"
                "- Evita FM < 6.0 salvo scommesse.\n"
                "- Portiere: FM costante a prezzo moderato.")
    def _answer_supers_bonus(self) -> str:
        rows=[]
        rows.extend(self._select_top_role("A", take=6, strategy="fm", min_fm=6.7))
        rows.extend(self._select_top_role("C", take=6, strategy="fm", min_fm=6.6))
        rows.sort(key=lambda x: -(x.get("_fm") or 0.0))
        out=[]
        for p in rows[:10]:
            fm=p.get("_fm"); pr=p.get("_price"); bits=[]
            if isinstance(fm,(int,float)): bits.append(f"FM {fm:.2f}")
            if isinstance(pr,(int,float)): bits.append(f"€ {int(round(pr))}")
            out.append(f"- **{p.get('name')}** ({p.get('team')}) — " + ", ".join(bits))
        return "🏅 **Giocatori “bonus-friendly” (proxy FM)**\n" + ("\n".join(out) if out else "—")

    # -------- Fallback LLM (solo extra, NON quick actions) --------
    def _llm_complete(self, user_text: str, context_messages: Optional[List[Dict[str, str]]] = None) -> str:
        if not self.openai_api_key:
            return ("⚠️ Servizio AI non configurato. Uso solo i dati locali filtrati.")
        messages = [{"role": "system", "content": self.system_prompt}]
        if context_messages:
            messages.extend(context_messages)
        messages.append({"role": "user", "content": user_text})
        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "Content-Type": "application/json"
        }
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
            return ("⚠️ Modello non disponibile. Uso solo le basi locali.")

    # -------- Routing --------
    def get_response(self, user_text: str, mode: str = "classic",
                     context: Optional[Dict[str, Any]] = None) -> str:
        lt = (user_text or "").lower()

        # UNDER 21
        if ("under 21" in lt or "under-21" in lt or "under21" in lt or "u21" in lt):
            if "difensor" in lt or "centrale" in lt or "terzin" in lt:
                return self._answer_under21("D")
            if "centrocamp" in lt or "mezzala" in lt or "regista" in lt:
                return self._answer_under21("C")
            if "attacc" in lt or "punta" in lt or "seconda punta" in lt:
                return self._answer_under21("A")
            if "portier" in lt:
                return self._answer_under21("P")
            for rl in ["D","C","A","P"]:
                ans = self._select_under(rl, 21, 2)
                if ans:
                    lines = []
                    for p in ans:
                        age = self._age_from_birth_year(p.get("birth_year"))
                        lines.append(f"**{p.get('name','N/D')}** ({p.get('team','—')}) — {age} anni")
                    return "Qualche Under 21 interessante:\n- " + "\n- ".join(lines)
            return ("Non ho profili con età certa per quel filtro. Prova senza vincolo d’età o specifica un club.")

        # QUICK ACTIONS — Classic
        if (("attacc" in lt or "punta" in lt or "top attaccanti" in lt) and "budget" in lt) or ("top attaccanti" in lt):
            budget = _parse_first_int(lt) or 150
            return self._answer_top_attackers_by_budget(budget)
        if "formazione" in lt and re.search(r"\b[0-5]\s*-\s*[0-5]\s*-\s*[0-5]\b", lt):
            return self._answer_build_xi(lt)
        if "strategia" in lt and "asta" in lt and ("classic" in lt or mode=="classic"):
            return self._answer_asta_strategy(lt)
        if "prossime partite" in lt or ("analizza" in lt and "partite" in lt):
            return ("Per le prossime partite non ho calendario offline affidabile; uso FM storica.")

        # Mantra
        if mode=="mantra":
            if "centrocamp" in lt and ("assist" in lt or "bonus" in lt):
                return self._answer_mantra_top_cm_assist()
            if "formazione" in lt and re.search(r"\b[0-5]\s*-\s*[0-5]\s*-\s*[0-5]\b", lt):
                return self._answer_build_xi(lt)
            if "strategia" in lt and "asta" in lt:
                return self._answer_asta_strategy(lt)
            if "clean sheet" in lt or ("difensori" in lt and "clean" in lt):
                return self._answer_clean_sheet_def()

        # Draft
        if mode=="draft":
            if "snake" in lt and "strategia" in lt:
                return self._answer_draft_snake(lt)
            if "ordine" in lt and "ruoli" in lt:
                return self._answer_draft_order_roles()
            if "prime scelte" in lt:
                return self._answer_draft_first_rounds()
            if "sleeper" in lt:
                return self._answer_draft_sleepers()

        # Superscudetto
        if mode=="superscudetto":
            if "formazione" in lt and re.search(r"\b[0-5]\s*-\s*[0-5]\s*-\s*[0-5]\b", lt):
                return self._answer_supers_formazione(lt)
            if "regole speciali" in lt or "strategia" in lt:
                return self._answer_supers_rules()
            if "premi" in lt or "bonus" in lt:
                return self._answer_supers_bonus()

        # Altro → (eventuale) LLM
        return self._llm_complete(user_text, context_messages=[])

    # -------- Diagnostica --------
    def get_age_coverage(self) -> Dict[str, Dict[str, int]]:
        out: Dict[str, Dict[str, int]] = {}
        per_role: Dict[str, List[Dict[str, Any]]] = {"P": [], "D": [], "C": [], "A": []}
        for p in getattr(self, "filtered_roster", self.roster):
            r = (p.get("role") or "").upper()[:1]
            if r not in per_role: continue
            per_role[r].append(p)
        for r, items in per_role.items():
            tot = len(items); with_age = 0; u21 = 0; u23 = 0
            for p in items:
                age = self._age_from_birth_year(p.get("birth_year"))
                if age is not None:
                    with_age += 1
                    if age <= 21: u21 += 1
                    if age <= 23: u23 += 1
            out[r] = {"total": tot, "with_age": with_age, "u21": u21, "u23": u23}
        return out

    def debug_under(self, role: str, max_age: int = 21, take: int = 10) -> List[Dict[str, Any]]:
        role = (role or "").upper()[:1]
        out=[]
        for p in self._select_under(role, max_age, take*3):
            out.append({
                "name": p.get("name"),
                "team": p.get("team"),
                "role": p.get("role"),
                "birth_year": p.get("birth_year"),
                "age": self._age_from_birth_year(p.get("birth_year")),
                "fantamedia": p.get("_fm"),
                "price": p.get("_price"),
            })
            if len(out) >= take: break
        return out

    def peek_age(self, name: str, team: str = "") -> Dict[str, Any]:
        k = _age_key(name, team)
        by = self.overrides.get(k) or self.age_index.get(k)
        if by is None:
            nn = _norm_name(name)
            for kk, v in self.overrides.items():
                if kk.startswith(nn + "@@"):
                    by = v; k = kk; break
            if by is None:
                for kk, v in self.age_index.items():
                    if kk.startswith(nn + "@@"):
                        by = v; k = kk; break
        return {"key": k, "birth_year": by, "age": (REF_YEAR - by) if by else None}
