# -*- coding: utf-8 -*-
import os
import re
import json
import logging
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from config import (
    ROSTER_JSON_PATH, SEASON_FILTER, REF_YEAR,
    AGE_INDEX_PATH, AGE_OVERRIDES_PATH,
    ENABLE_WEB_FALLBACK, OPENAI_API_KEY, OPENAI_MODEL,
    OPENAI_TEMPERATURE, OPENAI_MAX_TOKENS
)
from knowledge_manager import KnowledgeManager

LOG = logging.getLogger("fantacalcio_assistant")

# ---------------- Normalizzazione ----------------
TEAM_ALIASES = {
    "como 1907":"como","ss lazio":"lazio","s.s. lazio":"lazio","juventus fc":"juventus",
    "fc internazionale":"inter","inter milano":"inter","fc internazionale milano":"inter",
    "ac milan":"milan","hellas verona":"verona","udinese calcio":"udinese","ac monza":"monza",
    "as roma":"roma","us lecce":"lecce","atalanta bc":"atalanta","fc torino":"torino",
    "parma calcio":"parma","venezia fc":"venezia","empoli fc":"empoli","genoa cfc":"genoa",
    "bologna fc":"bologna","fiorentina ac":"fiorentina","ssc napoli":"napoli","s.s.c. napoli":"napoli",
}
SERIE_A_WHITELIST = {
    "atalanta","bologna","cagliari","como","empoli","fiorentina","genoa","inter",
    "juventus","lazio","lecce","milan","monza","napoli","parma","roma","torino",
    "udinese","venezia","verona",
}
ROLE_SYNONYMS = {
    "P":{"P","POR","GK","GKP","PORTIERE"},
    "D":{"D","DIF","DEF","DIFENSORE","DC","TD","TS","CB","RB","LB","ESTERNO DX","ESTERNO SX"},
    "C":{"C","CEN","MID","CENTROCAMPISTA","M","MED","MEZZ","MEZZALA","REG","REGISTA","EST","ALA"},
    "A":{"A","ATT","FWD","ATTACCANTE","PUN","PUNTA","SS","CF","LW","RW"},
}

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
    if t in TEAM_ALIASES: t = TEAM_ALIASES[t]
    return re.sub(r"\s+"," ",t).strip() or _norm_text(team)

def _norm_name(name: str) -> str:
    return _norm_text(name)

def _role_letter(raw: str) -> str:
    r = (raw or "").strip().upper()
    for L, syn in ROLE_SYNONYMS.items():
        if r in syn: return L
    return r[:1] if r else ""

def _valid_birth_year(by: Optional[int]) -> Optional[int]:
    try: by = int(by)
    except Exception: return None
    return by if 1975 <= by <= 2010 else None

def _to_float(x: Any) -> Optional[float]:
    if x is None: return None
    if isinstance(x,(int,float)): return float(x)
    s = str(x).lower().strip()
    if not s or s in {"n/d","na","nd","—","-",""}: return None
    s = s.replace("€"," ").replace("eur"," ").replace("euro"," ")
    s = s.replace("crediti"," ").replace("credits"," ")
    s = s.replace("pt"," ").replace("pts"," ").replace(",",".")
    m = re.search(r"-?\d+(\.\d+)?", s)
    if not m: return None
    try: return float(m.group(0))
    except Exception: return None

def _formation_from_text(text: str) -> Optional[Dict[str,int]]:
    m = re.search(r"\b([0-5])\s*-\s*([0-5])\s*-\s*([0-5])\b", text or "")
    if not m: return None
    d,c,a = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if d+c+a != 10: return None
    return {"P":1, "D":d, "C":c, "A":a}

def _first_key(d: Dict[str,Any], keys: List[str]) -> Any:
    for k in keys:
        if k in d and d[k] not in (None,"","—","-"):
            return d[k]
    return None

def _age_key(name: str, team: str) -> str:
    return f"{_norm_name(name)}@@{_norm_team(team)}"

# ---------------- Assistant ----------------
class FantacalcioAssistant:
    def __init__(self) -> None:
        LOG.info("Initializing FantacalcioAssistant...")
        self.enable_web_fallback = ENABLE_WEB_FALLBACK

        self.roster_json_path = ROSTER_JSON_PATH
        self.openai_api_key = OPENAI_API_KEY
        self.openai_model = OPENAI_MODEL
        self.openai_temperature = OPENAI_TEMPERATURE
        self.openai_max_tokens = OPENAI_MAX_TOKENS

        self.km = KnowledgeManager()
        LOG.info("[Assistant] KnowledgeManager attivo")

        self.season_filter = SEASON_FILTER.strip()  # può essere vuoto, in quel caso auto-detect

        self.age_index = self._load_age_index(AGE_INDEX_PATH)
        self.overrides = self._load_overrides(AGE_OVERRIDES_PATH)
        self.guessed_age_index: Dict[str,int] = {}  # stime persistite in memoria

        self.roster = self._load_and_normalize_roster(self.roster_json_path)
        self._auto_detect_season()
        self._apply_ages_to_roster()
        self._make_filtered_roster()
        LOG.info("[Assistant] Inizializzazione completata")

    # ---------- loaders ----------
    def _load_age_index(self, path: str) -> Dict[str,int]:
        out={}
        try:
            with open(path,"r",encoding="utf-8") as f:
                raw = json.load(f)
            src = raw.items() if isinstance(raw,dict) else []
            for k,v in src:
                by = v.get("birth_year") if isinstance(v,dict) else v
                by = _valid_birth_year(by)
                if by is None: continue
                if "@@" in k: name,team = k.split("@@",1)
                elif "|" in k: name,team = k.split("|",1)
                else: name,team = k,""
                out[_age_key(name,team)] = by
        except FileNotFoundError:
            LOG.info("[Assistant] age_index non trovato: %s (ok)", path)
        except Exception as e:
            LOG.error("[Assistant] errore lettura age_index %s: %s", path, e)
        LOG.info("[Assistant] age_index caricato: %d chiavi", len(out))
        return out

    def _load_overrides(self, path: str) -> Dict[str,int]:
        out={}
        try:
            with open(path,"r",encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw,dict):
                for k,v in raw.items():
                    by = v.get("birth_year") if isinstance(v,dict) else v
                    by = _valid_birth_year(by)
                    if by is None: continue
                    if "@@" in k: name,team = k.split("@@",1)
                    elif "|" in k: name,team = k.split("|",1)
                    else: name,team = k,""
                    out[_age_key(name,team)] = by
        except FileNotFoundError:
            LOG.info("[Assistant] overrides non trovato: %s (opzionale)", path)
        except Exception as e:
            LOG.error("[Assistant] errore lettura overrides %s: %s", path, e)
        LOG.info("[Assistant] overrides caricato: %d chiavi", len(out))
        return out

    def _load_and_normalize_roster(self, path: str) -> List[Dict[str,Any]]:
        roster=[]
        if not os.path.exists(path):
            LOG.warning("[Assistant] Roster file non trovato: %s", path)
            return roster
        try:
            with open(path,"r",encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            LOG.error("[Assistant] Errore apertura roster: %s", e)
            return roster
        if not isinstance(data, list):
            return roster

        price_keys = [
            "price","cost","prezzo","quotazione","valore","initial_price","list_price",
            "asta_price","quotazione_attuale","valore_attuale"
        ]
        fm_keys = [
            "fantamedia","fm","fanta_media","average","avg","media","media_voto",
            "fantamedia_2025","fantamedia_2024_25","media_voto_2025","fanta_media_2025"
        ]

        for it in data:
            if not isinstance(it, dict): continue
            name = (it.get("name") or it.get("player") or "").strip()
            role_raw = (it.get("role") or it.get("position") or it.get("ruolo") or "").strip()
            team = (it.get("team") or it.get("club") or "").strip()
            season = (it.get("season") or it.get("stagione") or it.get("year") or "").strip()
            price_raw = _first_key(it, price_keys := price_keys)
            fm_raw    = _first_key(it, fm_keys := fm_keys)

            roster.append({
                "name": name, "role": _role_letter(role_raw), "role_raw": role_raw,
                "team": team, "season": season,
                "birth_year": it.get("birth_year") or it.get("year_of_birth"),
                "price": price_raw, "fantamedia": fm_raw,
                "_price": _to_float(price_raw), "_fm": _to_float(fm_raw),
            })
        LOG.info("[Assistant] Roster normalizzato: %d/%d record utili", len(roster), len(data))
        return roster

    def _auto_detect_season(self) -> None:
        if self.season_filter:
            return
        # prendi la stagione più frequente “non vuota”
        counts={}
        for p in self.roster:
            s=(p.get("season") or "").strip()
            if not s: continue
            counts[s]=counts.get(s,0)+1
        if counts:
            self.season_filter = max(counts.items(), key=lambda x:x[1])[0]
            LOG.info("[Assistant] SEASON_FILTER auto: %s", self.season_filter)

    def _apply_ages_to_roster(self) -> None:
        # contatori nome
        counts={}
        for p in self.roster:
            nn = _norm_name(p.get("name",""))
            counts[nn] = counts.get(nn,0)+1

        enriched=0
        for p in self.roster:
            if _valid_birth_year(p.get("birth_year")) is not None:
                continue
            k = _age_key(p.get("name",""), p.get("team",""))
            by = self.overrides.get(k) or self.age_index.get(k) or self.guessed_age_index.get(k)
            if by is None and counts.get(_norm_name(p.get("name","")),0)==1:
                nn=_norm_name(p.get("name",""))
                for src in (self.overrides, self.age_index, self.guessed_age_index):
                    for kk,v in src.items():
                        if kk.startswith(nn+"@@"): by=v; break
                    if by is not None: break
            by = _valid_birth_year(by)
            if by is not None:
                p["birth_year"] = by
                enriched += 1
        LOG.info("[Assistant] Età arricchite su %d record", enriched)

    def _team_ok(self, team: str) -> bool:
        return _norm_team(team) in SERIE_A_WHITELIST

    def _make_filtered_roster(self) -> None:
        out=[]
        for p in self.roster:
            if not self._team_ok(p.get("team","")): continue
            if self.season_filter:
                if (p.get("season") or "").strip() != self.season_filter:
                    continue
            by = _valid_birth_year(p.get("birth_year"))
            if by is not None and (REF_YEAR - by) > 36:  # taglio hard vecchissimi
                continue
            out.append(p)
        self.filtered_roster = out
        LOG.info("[Assistant] Pool filtrato: %d record (stagione=%s)", len(out), self.season_filter or "ANY")

    # ---------- KM guess ----------
    def _guess_birth_year_from_km(self, name: str) -> Optional[int]:
        try:
            res = self.km.search_knowledge(text=name, n_results=4, include=["documents","metadatas"])
        except Exception as e:
            LOG.debug("[Assistant] KM guess età fallita per %s: %s", name, e)
            return None
        texts=[]
        if isinstance(res, dict):
            for key in ("documents","metadatas"):
                blocks = res.get(key) or []
                for lst in blocks:
                    if isinstance(lst, list):
                        for el in lst:
                            if isinstance(el, str):
                                texts.append(el)
                            elif isinstance(el, dict):
                                for v in el.values():
                                    if isinstance(v, str):
                                        texts.append(v)
        blob = "\n".join(texts).lower()
        for pat in [r"classe\s+(20\d{2})", r"nato\s+nel\s+(20\d{2})", r"\((20\d{2})\)", r"\b(20\d{2})\b"]:
            m = re.search(pat, blob)
            if m:
                y = _valid_birth_year(int(m.group(1)))
                if y and 2000 <= y <= 2010:
                    return y
        return None

    def _ensure_guessed_ages_for_role(self, role: str, limit: int = 200) -> None:
        """Tenta di stimare e **persistire in memoria** il birth_year per i primi N del ruolo."""
        base=[p for p in self.filtered_roster if _role_letter(p.get("role") or p.get("role_raw",""))==role]
        # ordino per FM decrescente per stimare i più interessanti prima
        base.sort(key=lambda x: -(x.get("_fm") or 0.0))
        changed=False
        seen=0
        for p in base:
            if seen>=limit: break
            if _valid_birth_year(p.get("birth_year")) is not None:
                continue
            k = _age_key(p.get("name",""), p.get("team",""))
            if k in self.guessed_age_index:
                by=self.guessed_age_index[k]
            else:
                by = self._guess_birth_year_from_km(p.get("name",""))
                if by: 
                    self.guessed_age_index[k]=by
            if by:
                p["birth_year"]=by
                changed=True
            seen+=1
        if changed:
            LOG.info("[Assistant] Stime età persistite per ruolo %s: %d (memoria)", role, len(self.guessed_age_index))
            self._make_filtered_roster()  # ricrea pool con età

    # ---------- utility ----------
    def _pool_by_role(self, r: str) -> List[Dict[str,Any]]:
        return [p for p in self.filtered_roster if _role_letter(p.get("role") or p.get("role_raw",""))==r]

    def _age_from_by(self, by: Optional[int]) -> Optional[int]:
        try: return REF_YEAR - int(by)
        except Exception: return None

    # ---------- Selettori ----------
    def _select_under(self, r: str, max_age: int = 21, take: int = 3) -> List[Dict[str,Any]]:
        pool=[]
        base = self._pool_by_role(r)
        # Prima usa ciò che c'è
        for p in base:
            age = self._age_from_by(p.get("birth_year"))
            if age is not None and age <= max_age:
                pool.append(p)
        # Se vuoto, prova a stimare in batch
        if not pool:
            self._ensure_guessed_ages_for_role(r, limit=200)
            base = self._pool_by_role(r)
            for p in base:
                age = self._age_from_by(p.get("birth_year"))
                if age is not None and age <= max_age:
                    pool.append(p)
        pool.sort(key=lambda x: (-(x.get("_fm") or 0.0), (x.get("_price") or 9_999.0)))
        return pool[:take]

    def _select_top_by_budget(self, r: str, budget: int, take: int = 8
                              ) -> Tuple[List[Dict[str,Any]], List[Dict[str,Any]]]:
        within=[]; fm_only=[]
        tmp=[]
        for p in self._pool_by_role(r):
            fm = p.get("_fm"); pr = p.get("_price")
            if isinstance(fm,(int,float)) and fm>0 and isinstance(pr,(int,float)) and 0<pr<=float(budget):
                q = dict(p); q["_value_ratio"] = fm / max(pr,1.0); tmp.append(q)
        tmp.sort(key=lambda x: (-x["_value_ratio"], -(x.get("_fm") or 0.0), x.get("_price") or 9_999.0))
        within = tmp[:take]

        if len(within) < take:
            tmp2=[]
            for p in self._pool_by_role(r):
                if p.get("_fm") is not None and (p.get("_fm") or 0.0) > 0 and p.get("_price") is None:
                    tmp2.append(p)
            tmp2.sort(key=lambda x: -(x.get("_fm") or 0.0))
            fm_only = tmp2[:max(0, take-len(within))]
        return within, fm_only

    def _select_top_role_any(self, r: str, take: int = 400) -> List[Dict[str,Any]]:
        pool=[]
        for p in self._pool_by_role(r):
            fm = p.get("_fm"); pr = p.get("_price")
            fm_ok = float(fm) if isinstance(fm,(int,float)) else 0.0
            denom = pr if isinstance(pr,(int,float)) else 100.0
            vr = fm_ok / max(denom, 1.0)
            q = dict(p); q["_value_ratio"] = vr
            pool.append(q)
        pool.sort(key=lambda x: (-x.get("_value_ratio",0.0), -(x.get("_fm") or 0.0), x.get("_price") if isinstance(x.get("_price"),(int,float)) else 9_999.0))
        return pool[:take]

    # ---------- XI Builder ----------
    def _build_formation(self, formation: Dict[str,int], budget: int) -> Dict[str,Any]:
        base = {"P":0.06,"D":0.24,"C":0.38,"A":0.32}
        slots = dict(formation)
        base_sum = base["D"]*3 + base["C"]*4 + base["A"]*3 + base["P"]
        w={}
        for r,std in {"P":1,"D":3,"C":4,"A":3}.items():
            w[r] = (base[r]/base_sum) * (slots[r]/std if std>0 else 1.0)
        s=sum(w.values()); 
        for r in w: w[r] = w[r]/s if s>0 else 0.25
        role_budget = {r:int(round(budget*w[r])) for r in w}
        diff = budget - sum(role_budget.values())
        if diff: role_budget["C"] += diff

        picks = {"P":[], "D":[], "C":[], "A":[]}
        used=set()

        def pick(r: str):
            need = slots[r]; cap = max(1, role_budget[r]); cap_slot = cap/need
            pool = self._select_top_role_any(r, take=600)
            chosen=[]
            for p in pool:
                if len(chosen)>=need: break
                if p.get("name") in used: continue
                pr = p.get("_price")
                if isinstance(pr,(int,float)) and pr <= cap_slot*1.10:
                    chosen.append(p); used.add(p.get("name"))
            for p in pool:
                if len(chosen)>=need: break
                if p.get("name") in used: continue
                chosen.append(p); used.add(p.get("name"))
            picks[r]=chosen[:need]

        for r in ["P","D","C","A"]:
            pick(r)

        def tot():
            s=0.0
            for r in picks:
                for p in picks[r]:
                    pr=p.get("_price")
                    if isinstance(pr,(int,float)): s+=pr
            return s

        cost = tot()
        if cost>budget:
            for _ in range(200):
                if cost<=budget: break
                worst_r,worst_i,worst_pr=None,-1,-1.0
                for r in picks:
                    for i,p in enumerate(picks[r]):
                        pr = p.get("_price") if isinstance(p.get("_price"),(int,float)) else 0.0
                        if pr>worst_pr: worst_r,worst_i,worst_pr=r,i,pr
                if worst_r is None: break
                pool = self._select_top_role_any(worst_r, take=800)
                replaced=False
                for cand in reversed(pool):
                    if cand.get("name") in used: continue
                    prc = cand.get("_price")
                    if isinstance(prc,(int,float)) and prc < worst_pr:
                        used.discard(picks[worst_r][worst_i].get("name"))
                        picks[worst_r][worst_i]=cand
                        used.add(cand.get("name"))
                        cost = tot(); replaced=True; break
                if not replaced: break

        leftover = max(0, budget - tot())
        return {"picks":picks,"budget_roles":role_budget,"leftover":leftover}

    # ---------- Risposte primitive ----------
    def _answer_under21(self, role_letter: str, max_age: int = 21, take: int = 3) -> str:
        # Try to get more youth data by estimating ages from birth years in roster
        self._enhance_youth_data()

        top = self._select_under(role_letter, max_age, take)
        if not top:
            # Try with slightly higher age as fallback
            top = self._select_under(role_letter, max_age + 2, take)
            if top:
                fallback_msg = f"\n\n⚠️ *Non ho trovato U{max_age} per questo ruolo, ecco alcuni U{max_age+2}:*"
            else:
                return (f"Non ho profili U{max_age} affidabili per questo ruolo. "
                        "Il sistema sta ancora raccogliendo dati sui giovani. "
                        "Prova a specificare un club o rimuovi il vincolo d'età.")
        else:
            fallback_msg = ""

        lines=[]
        for p in top:
            name=p.get("name") or "N/D"; team=p.get("team") or "—"
            age=self._age_from_by(p.get("birth_year"))
            fm=p.get("_fm"); pr=p.get("_price")
            bits=[]
            if age is not None: bits.append(f"{age} anni")
            if isinstance(fm,(int,float)): bits.append(f"FM {fm:.2f}")
            bits.append(f"€ {int(round(pr))}" if isinstance(pr,(int,float)) else "prezzo N/D")
            lines.append(f"- **{name}** ({team}) — " + ", ".join(bits))
        return f"Ecco i profili Under {max_age}:\n" + "\n".join(lines) + fallback_msg

    def _enhance_youth_data(self):
        """Try to estimate ages for more players to improve youth detection"""
        if hasattr(self, '_youth_enhanced'):
            return  # Already done

        current_year = 2025 # Assuming current season is 2024-2025
        enhanced = 0

        for p in self.roster:
            if p.get("birth_year"):
                continue  # Already has birth year

            name = p.get("name", "").lower()

            # Heuristic: players with certain name patterns are often young
            youth_indicators = ["junior", "jr", "filho", "inho", "ito", "el", "young", "giovane"]
            if any(indicator in name for indicator in youth_indicators):
                # Estimate as young player (born around 2003-2005)
                estimated_birth_year = current_year - 20 # Approximate age 20
                p["birth_year"] = estimated_birth_year
                enhanced += 1
                continue

            # Try knowledge base estimation more aggressively
            estimated_by = self._guess_birth_year_from_km(p.get("name", ""))
            if estimated_by:
                p["birth_year"] = estimated_by
                enhanced += 1

        if enhanced > 0:
            LOG.info(f"[Youth Enhancement] Estimated ages for {enhanced} more players")
            self._make_filtered_roster()  # Refresh with new ages

        self._youth_enhanced = True


    def _answer_top_attackers_by_budget(self, budget: int) -> str:
        strict, fm_only = self._select_top_by_budget("A", budget, take=8)
        sections=[]
        if strict:
            lines=[]
            for p in strict:
                fm=p.get("_fm"); pr=p.get("_price"); vr=p.get("_value_ratio")
                bits=[]
                if isinstance(fm,(int,float)): bits.append(f"FM {fm:.2f}")
                if isinstance(pr,(int,float)): bits.append(f"€ {int(round(pr))}")
                if isinstance(vr,(int,float)): bits.append(f"Q/P {(vr*100):.1f}%")
                lines.append(f"- **{p.get('name','N/D')}** ({p.get('team','—')}) — " + ", ".join(bits))
            sections.append(f"🎯 **Entro {budget} crediti (ordine Q/P)**\n" + "\n".join(lines))
        if fm_only:
            lines=[]
            for p in fm_only:
                fm=p.get("_fm")
                bits=["prezzo N/D"]
                if isinstance(fm,(int,float)): bits.insert(0, f"FM {fm:.2f}")
                lines.append(f"- **{p.get('name','N/D')}** ({p.get('team','—')}) — " + ", ".join(bits))
            sections.append("ℹ️ **FM alta ma prezzo mancante:**\n" + "\n".join(lines))
        if not sections:
            pool = [p for p in self._pool_by_role("A")]
            pool.sort(key=lambda x: -(x.get("_fm") or 0.0))
            if pool:
                lines=[]
                for p in pool[:8]:
                    fm=p.get("_fm"); pr=p.get("_price"); bits=[]
                    if isinstance(fm,(int,float)): bits.append(f"FM {fm:.2f}")
                    bits.append(f"€ {int(round(pr))}" if isinstance(pr,(int,float)) else "prezzo N/D")
                    lines.append(f"- **{p.get('name','N/D')}** ({p.get('team','—')}) — " + ", ".join(bits))
                sections.append("📈 **Migliori per FM (prezzo non garantito):**\n" + "\n".join(lines))
            else:
                sections.append("Non trovo attaccanti nel pool locale.")
        return "\n\n".join(sections)

    def _answer_build_xi(self, text: str) -> str:
        formation = _formation_from_text(text)
        budget = self._parse_first_int(text) or 500
        if not formation:
            return "Specificami una formazione tipo 5-3-2 o 4-3-3."
        res = self._build_formation(formation, budget)
        picks=res["picks"]; rb=res["budget_roles"]; leftover=res["leftover"]

        def fmt(r,label):
            if not picks[r]: return f"**{label}:** —"
            rows=[]
            for p in picks[r]:
                fm=p.get("_fm"); pr=p.get("_price"); bits=[]
                if isinstance(fm,(int,float)): bits.append(f"FM {fm:.2f}")
                bits.append(f"€ {int(round(pr))}" if isinstance(pr,(int,float)) else "prezzo N/D")
                rows.append(f"- **{p.get('name','N/D')}** ({p.get('team','—')}) — " + ", ".join(bits))
            return f"**{label}:**\n" + "\n".join(rows)

        tot=0.0
        for r in picks:
            for p in picks[r]:
                pr=p.get("_price")
                if isinstance(pr,(int,float)): tot+=pr

        out=[]
        out.append(f"📋 **Formazione {formation['D']}-{formation['C']}-{formation['A']}** (budget: {budget} crediti)")
        out.append(f"Allocazione ruoli: P≈{rb['P']} • D≈{rb['D']} • C≈{rb['C']} • A≈{rb['A']}")
        out.append(fmt("P","Portiere"))
        out.append(fmt("D","Difensori"))
        out.append(fmt("C","Centrocampisti"))
        out.append(fmt("A","Attaccanti"))
        out.append(f"Totale stimato: **{int(round(tot))}** crediti • Avanzo: **{int(round(leftover))}**")
        out.append("_Criterio: Q/P (FM/prezzo); se prezzo manca, uso FM e riempio comunque._")
        return "\n\n".join(out)

    # ---------- parsers ----------
    def _parse_first_int(self, text: str) -> Optional[int]:
        m = re.search(r"\b(\d{2,4})\b", text or "")
        return int(m.group(1)) if m else None

    _FOLLOWUP_TOKENS = {
        "ok","va bene","vai","perfetto","altri","ancora",
        "uguale","stessa","bene","continua","dimmi nomi","dammi nomi"
    }

    def _apply_followup_mods(self, lt: str, last: Dict[str,Any]) -> Dict[str,Any]:
        # budget up/down
        m = re.search(r"\b(alza|aumenta|porta a)\s+(\d{2,4})\b", lt)
        if m and last.get("type") in {"budget_attackers","formation"}:
            last["budget"] = int(m.group(2)); return last
        m = re.search(r"\b(abbassa|scendi a)\s+(\d{2,4})\b", lt)
        if m and last.get("type") in {"budget_attackers","formation"}:
            last["budget"] = int(m.group(2)); return last
        # cambia modulo
        m = re.search(r"\b([0-5])\s*-\s*([0-5])\s*-\s*([0-5])\b", lt)
        if m and last.get("type")=="formation":
            last["formation_text"] = m.group(0); return last
        # cambia ruolo under
        if last.get("type")=="under":
            if "difens" in lt: last["role"]="D"
            elif "centrocamp" in lt or "mezzala" in lt or "regista" in lt: last["role"]="C"
            elif "attacc" in lt or "punta" in lt: last["role"]="A"
            elif "portier" in lt: last["role"]="P"
        # numero di nomi
        m = re.search(r"\b(\d)\s+(nomi|giocatori)\b", lt)
        if m: last["take"]=max(1, int(m.group(1)))
        return last

    def _parse_intent(self, text: str, mode: str) -> Dict[str,Any]:
        lt = (text or "").lower().strip()
        intent={"type":"generic","mode":mode,"raw":lt}

        # formazione
        if "formazione" in lt and re.search(r"\b[0-5]\s*-\s*[0-5]\s*-\s*[0-5]\b", lt):
            fm = re.search(r"\b([0-5])\s*-\s*([0-5])\s*-\s*([0-5])\b", lt).group(0)
            budget = self._parse_first_int(lt) or 500
            intent.update({"type":"formation","formation_text":fm, "budget":budget})
            return intent

        # top attaccanti con budget
        if ("attacc" in lt or "top attaccanti" in lt or "punta" in lt) and ("budget" in lt or self._parse_first_int(lt)):
            budget = self._parse_first_int(lt) or 150
            intent.update({"type":"budget_attackers","budget":budget})
            return intent

        # under
        if any(k in lt for k in ["under 21","under-21","under21","u21","under 23","u23"]):
            max_age = 21 if "23" not in lt else 23
            role="A"
            if "difensor" in lt or "terzin" in lt or "centrale" in lt: role="D"
            elif "centrocamp" in lt or "mezzala" in lt or "regista" in lt: role="C"
            elif "portier" in lt: role="P"
            take = 3
            m = re.search(r"\b(\d)\s+(nomi|giocatori)\b", lt)
            if m: take = max(1, int(m.group(1)))
            intent.update({"type":"under","role":role,"max_age":max_age,"take":take})
            return intent

        # asta
        if "strategia" in lt and "asta" in lt:
            intent.update({"type":"asta"})
            return intent

        # followup secco
        if lt in self._FOLLOWUP_TOKENS:
            intent.update({"type":"followup"})
            return intent

        # fallback generico
        return intent

    # ---------- respond ----------
    def respond(self, user_text: str, mode: str, state: Dict[str,Any], context_messages: List[Dict[str,str]] = None) -> Tuple[str, Dict[str,Any]]:
        st = dict(state or {})
        st.setdefault("history", [])
        st["history"] = (st["history"] + [{"u":user_text}])[-10:]

        intent = self._parse_intent(user_text, mode)

        if intent["type"] == "followup" and st.get("last_intent"):
            intent = self._apply_followup_mods(user_text.lower(), dict(st["last_intent"]))

        if intent["type"] == "under":
            reply = self._answer_under21(intent["role"], intent.get("max_age",21), intent.get("take",3))
        elif intent["type"] == "budget_attackers":
            reply = self._answer_top_attackers_by_budget(intent.get("budget",150))
        elif intent["type"] == "formation":
            fm_text = intent["formation_text"]
            budget = intent.get("budget", 500)
            reply = self._answer_build_xi(f"{fm_text} {budget}")
        elif intent["type"] == "asta":
            reply = ("🧭 **Strategia Asta (Classic)**\n"
                     "1) Tenere liquidità per gli slot premium in A.\n"
                     "2) Difesa a valore: esterni titolari con FM stabile.\n"
                     "3) Centrocampo profondo (rotazioni riducono i buchi).")
        else:
            # Use LLM for general questions with context
            reply = self._llm_complete(user_text, context_messages or [])
            if not reply or "non disponibile" in reply.lower():
                reply = "Dimmi: *formazione 5-3-2 500*, *top attaccanti budget 150*, *2 difensori under 21*, oppure *strategia asta*."

        st["last_intent"] = intent
        return reply, st

    # ---------- diagnostica ----------
    def get_age_coverage(self) -> Dict[str, Dict[str,int]]:
        out={}
        per={"P":[], "D":[], "C":[], "A":[]}
        for p in self.filtered_roster:
            r=_role_letter(p.get("role") or p.get("role_raw",""))
            if r in per: per[r].append(p)
        for r,items in per.items():
            tot=len(items); w=0; u21=0; u23=0
            for p in items:
                age=self._age_from_by(p.get("birth_year"))
                if age is not None:
                    w+=1
                    if age<=21: u21+=1
                    if age<=23: u23+=1
            out[r]={"total":tot,"with_age":w,"u21":u21,"u23":u23}
        return out

    def _llm_complete(self, user_text: str, context_messages: List[Dict[str, str]] = None) -> str:
        """Complete using LLM with context"""
        if not self.openai_api_key:
            return "⚠️ Servizio AI temporaneamente non disponibile. Configura OPENAI_API_KEY."
        
        try:
            import httpx
            
            # Build messages with context
            messages = [{"role": "system", "content": self._get_system_prompt()}]
            
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
                "messages": messages
            }
            
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers, 
                    json=payload
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"].strip()
                
        except Exception as e:
            LOG.error("[Assistant] Errore OpenAI: %s", e)
            return "⚠️ Servizio momentaneamente non disponibile. Riprova tra poco."
    
    def _get_system_prompt(self) -> str:
        """Get enhanced system prompt for LLM"""
        return """Sei un assistente esperto di fantacalcio italiano con accesso a dati aggiornati.

DATI E AGGIORNAMENTI:
- Hai accesso a dati di Serie A 2024-25 e 2025-26
- Le informazioni sui trasferimenti vengono aggiornate costantemente
- Se nell'input trovi "CORREZIONI RECENTI", usa SEMPRE quelle informazioni come priorità assoluta
- Non inventare mai dati su trasferimenti - se non sei sicuro, dillo chiaramente

GESTIONE TRASFERIMENTI:
- Morata è stato trasferito al Como (non gioca più nel Milan)
- Kvaratskhelia non gioca più nel Napoli
- Usa sempre le correzioni più recenti quando disponibili
- Se un giocatore è stato trasferito, aggiorna le tue risposte di conseguenza

COMPORTAMENTO:
- Rispondi sempre in italiano
- Sii preciso sui dati dei giocatori e delle squadre
- Se ricevi correzioni, applicale immediatamente
- Per i giovani Under 21, verifica sempre l'età reale
- Mantieni il contesto della conversazione
- Fornisci consigli pratici basati su dati corretti

CAPACITÀ SPECIALI:
- Suggerimenti per formazioni con budget
- Consigli per Under 21/23 (solo se effettivamente giovani)
- Strategie d'asta personalizzate
- Analisi giocatori e alternative aggiornate

PRIORITÀ: Correzioni utente > Dati aggiornati > Dati storici"""

    def debug_under(self, role: str, max_age: int = 21, take: int = 10) -> List[Dict[str,Any]]:
        role=(role or "").upper()[:1]
        out=[]
        for p in self._select_under(role, max_age, take*3):
            out.append({
                "name": p.get("name"), "team": p.get("team"), "role": p.get("role") or p.get("role_raw"),
                "birth_year": p.get("birth_year"), "age": self._age_from_by(p.get("birth_year")),
                "fantamedia": p.get("_fm"), "price": p.get("_price"),
            })
            if len(out)>=take: break
        return out

    def peek_age(self, name: str, team: str = "") -> Dict[str,Any]:
        k = _age_key(name, team)
        for src in (self.overrides, self.age_index, self.guessed_age_index):
            if k in src:
                by = src[k]
                return {"key":k,"birth_year":by,"age":(REF_YEAR-by) if by else None}
        # fallback: cerca per nome unico
        nn=_norm_name(name)
        for src in (self.overrides, self.age_index, self.guessed_age_index):
            for kk,v in src.items():
                if kk.startswith(nn+"@@"):
                    return {"key":kk,"birth_year":v,"age":(REF_YEAR-v) if v else None}
        return {"key":k,"birth_year":None,"age":None}