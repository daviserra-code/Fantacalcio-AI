# -*- coding: utf-8 -*-
import os
import re
import json
import logging
import unicodedata
from typing import Any, Dict, List, Optional, Tuple
import time
import shutil

from config import (
    ROSTER_JSON_PATH, SEASON_FILTER, REF_YEAR,
    AGE_INDEX_PATH, AGE_OVERRIDES_PATH,
    ENABLE_WEB_FALLBACK, OPENAI_API_KEY, OPENAI_MODEL,
    OPENAI_TEMPERATURE, OPENAI_MAX_TOKENS
)
from knowledge_manager import KnowledgeManager

# Dummy function to satisfy the import if corrections_manager is not available
LOG = logging.getLogger("fantacalcio_assistant")
try:
    from corrections_manager import CorrectionsManager
except ImportError:
    LOG.warning("[Assistant] Could not import CorrectionsManager, using dummy.")
    class CorrectionsManager:
        def __init__(self, knowledge_manager=None): pass
        def apply_corrections_to_data(self, data): return data
        def update_player_team(self, *args): pass
        def add_correction(self, *args): pass
        def remove_player(self, *args): return "Corrections manager not available."
        def get_data_quality_report(self): return {"error": "Corrections manager not available"}
        def is_serie_a_team(self, team): return True # Assume valid if not implemented
        def apply_corrections_to_text(self, text): return text, []
        def get_corrected_team(self, name, team): return team
        def get_corrected_name(self, name): return name
        def get_excluded_players(self): return []

# Helper function to check environment variables for boolean true
def _env_true(value: str) -> bool:
    return value.lower() in ("true", "1", "yes", "y")

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
    try:
        by = int(by)
        # Updated range for current players: born between 1975-2010 makes sense
        # Players born in 2010 would be ~15 years old in 2025
        if 1975 <= by <= 2010:
            return by
        return None
    except Exception:
        return None

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
    # Use the exact format from age_overrides.json (no normalization for team names)
    return f"{name}@@{team}"

def _safe_float(x: Any, default: float = 0.0) -> float:
    """Convert to float, return default if conversion fails or input is None."""
    if x is None: return default
    if isinstance(x, (int, float)): return float(x)
    try:
        return float(x)
    except (ValueError, TypeError):
        return default

# ---------------- Assistant ----------------
class FantacalcioAssistant:
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

        # Initialize corrections manager
        try:
            from corrections_manager import CorrectionsManager
            self.corrections_manager = CorrectionsManager(knowledge_manager=self.km)
            LOG.info("[Assistant] CorrectionsManager inizializzato")
        except Exception as e:
            LOG.warning("[Assistant] Failed to initialize CorrectionsManager: %s", e)
            self.corrections_manager = None

        self.roster: List[Dict[str, Any]] = self._load_and_normalize_roster(self.roster_json_path)
        self.external_youth_cache: List[Dict[str, Any]] = self._load_external_youth_cache()

        # Initialize missing attributes
        self.season_filter = SEASON_FILTER or None
        self.age_index = self._load_age_index(AGE_INDEX_PATH)
        self.override_roles = {}  # Initialize before loading overrides
        self.overrides = self._load_overrides(AGE_OVERRIDES_PATH)
        self.guessed_age_index = {}

        # Apply data corrections immediately after loading roster
        if self.corrections_manager:
            original_count = len(self.roster)
            self.roster = self.corrections_manager.apply_corrections_to_data(self.roster)
            excluded_count = len(self.corrections_manager.get_excluded_players())
            LOG.info("[Assistant] Applied data corrections to roster: %d players, %d excluded", len(self.roster), excluded_count)
            
            # Log team corrections that were applied
            for player in self.roster:
                corrected_team = self.corrections_manager.get_corrected_team(player.get("name", ""), player.get("team", ""))
                if corrected_team and corrected_team != player.get("team"):
                    LOG.info("[Assistant] Applied team correction: %s %s → %s", player.get("name"), player.get("team"), corrected_team)
                    player["team"] = corrected_team

        self._auto_detect_season()
        self._apply_ages_to_roster()
        self._make_filtered_roster()
        LOG.info("[Assistant] Inizializzazione completata")

    def _load_prompt_json(self, path: str) -> str:
        """Load system prompt from JSON file"""
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
        self.override_roles = {}  # Store role information separately
        try:
            with open(path,"r",encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw,dict):
                for k,v in raw.items():
                    # Handle both old format (just year) and new format (dict with year and role)
                    if isinstance(v, dict):
                        by = _valid_birth_year(v.get("year") or v.get("birth_year"))
                        role = v.get("role", "")
                    else:
                        by = _valid_birth_year(v)
                        role = ""

                    if by is None: continue

                    # Store the key exactly as it appears in the JSON file
                    out[k] = by
                    if role:
                        self.override_roles[k] = _role_letter(role)

                    # NO MORE NORMALIZATION to prevent duplicates
                    # The matching logic will handle normalization when searching
        except FileNotFoundError:
            LOG.info("[Assistant] overrides non trovato: %s (opzionale)", path)
        except Exception as e:
            LOG.error("[Assistant] errore lettura overrides %s: %s", path, e)
        LOG.info("[Assistant] overrides caricato: %d chiavi", len(out))
        if hasattr(self, 'override_roles'):
            LOG.info("[Assistant] override roles caricati: %d", len(self.override_roles))
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
            # Create backup of corrupted file
            backup_path = f"{path}.corrupted.{int(time.time())}"
            try:
                shutil.copy2(path, backup_path)
                LOG.warning("[Assistant] File corrotto salvato come backup: %s", backup_path)
            except Exception:
                pass
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

            # Apply corrections early to raw data if possible
            if self.corrections_manager:
                corrected_name = self.corrections_manager.get_corrected_name(name)
                corrected_team = self.corrections_manager.get_corrected_team(name, team)
                name = corrected_name if corrected_name else name
                team = corrected_team if corrected_team else team

            roster.append({
                "name": name, "role": _role_letter(role_raw), "role_raw": role_raw,
                "team": team, "season": season,
                "birth_year": it.get("birth_year") or it.get("year_of_birth"),
                "price": price_raw, "fantamedia": fm_raw,
                "_price": _to_float(price_raw), "_fm": _to_float(fm_raw),
            })
        LOG.info("[Assistant] Roster normalizzato: %d/%d record utili", len(roster), len(data))
        return roster

    def _load_external_youth_cache(self) -> List[Dict[str, Any]]:
        """Load youth data from an external cache file."""
        if not os.path.exists(self.external_youth_cache_path):
            LOG.info("[Assistant] External youth cache not found: %s", self.external_youth_cache_path)
            return []
        try:
            with open(self.external_youth_cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            LOG.info("[Assistant] Loaded %d players from external youth cache.", len(data))
            return data
        except Exception as e:
            LOG.error("[Assistant] Error loading external youth cache: %s", e)
            return []

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
        """Check if team is Serie A 2024-25."""
        if not team:
            return False
        team_norm = team.strip().lower()

        # Current Serie A 2024-25 teams
        serie_a_teams = {
            "atalanta", "bologna", "cagliari", "como", "empoli", "fiorentina",
            "genoa", "inter", "juventus", "lazio", "lecce", "milan",
            "monza", "napoli", "parma", "roma", "torino", "udinese",
            "venezia", "verona", "hellas verona"
        }

        # Handle common variations
        team_mappings = {
            "hellas verona": "verona",
            "ac milan": "milan",
            "fc inter": "inter",
            "internazionale": "inter",
            "juventus fc": "juventus",
            "as roma": "roma",
            "ss lazio": "lazio",
            "ssc napoli": "napoli",
            "atalanta bc": "atalanta",
            "bologna fc": "bologna",
            "cagliari calcio": "cagliari",
            "como 1907": "como",
            "empoli fc": "empoli",
            "acf fiorentina": "fiorentina",
            "genoa cfc": "genoa",
            "us lecce": "lecce",
            "ac monza": "monza",
            "parma calcio": "parma",
            "torino fc": "torino",
            "udinese calcio": "udinese",
            "venezia fc": "venezia"
        }

        # Check direct match
        if team_norm in serie_a_teams:
            return True

        # Check mappings
        mapped_team = team_mappings.get(team_norm)
        if mapped_team and mapped_team in serie_a_teams:
            return True

        # Check partial matches for common abbreviations
        for serie_a_team in serie_a_teams:
            if serie_a_team in team_norm or team_norm in serie_a_team:
                return True

        return False

    def _make_filtered_roster(self) -> None:
        out=[]
        processed_override_players = set()

        # Use the already corrected roster (corrections applied at initialization)
        corrected_roster = self.roster

        # First, create all players from overrides that might not be in roster
        # BUT only include them for Under21 queries, not for budget-based formations
        processed_players = set()  # Track to prevent duplicates

        for key, birth_year in self.overrides.items():
            if "@@" in key:
                name, team = key.split("@@", 1)

                # Create unique identifier to prevent duplicates
                player_id = f"{_norm_name(name)}_{_norm_team(team)}"
                if player_id in processed_players:
                    continue
                processed_players.add(player_id)

                # Create a synthetic player record for override entries not in roster
                found_in_roster = False
                for p in corrected_roster:
                    p_name = _norm_name(p.get("name", "").strip())
                    p_team = _norm_team(p.get("team", "").strip())
                    if p_name == _norm_name(name) and p_team == _norm_team(team):
                        found_in_roster = True
                        break

                if not found_in_roster:
                    # Get role from override data, default to "C"
                    role = self.override_roles.get(key, "C")

                    # Only add synthetic players for Under21 tracking, mark them clearly
                    # Don't add them to the main pool to avoid forcing them in regular queries
                    synthetic_player = {
                        "name": name,
                        "team": team,
                        "role": role,
                        "birth_year": birth_year,
                        "price": None,
                        "fantamedia": None,
                        "_price": None,
                        "_fm": None,
                        "season": "2025-26",
                        "_source": "override_synthetic",
                        "_for_under21_only": True  # Mark these as Under21-only
                    }
                    # Store separately for Under21 queries only
                    if not hasattr(self, '_synthetic_under21_players'):
                        self._synthetic_under21_players = []
                    self._synthetic_under21_players.append(synthetic_player)
                    processed_override_players.add(key)

        # Then process corrected roster with override matching
        for p in corrected_roster:
            name = p.get("name", "").strip()
            team = p.get("team", "").strip()

            # Check if player has verified age in overrides with multiple key formats
            possible_keys = [
                f"{name}@@{team}",
                f"{_norm_name(name)}@@{_norm_team(team)}",
                _age_key(name, team)
            ]

            has_verified_age = False
            for key in possible_keys:
                if key in self.overrides or key in self.age_index:
                    has_verified_age = True
                    # Update birth_year from overrides
                    birth_year = self.overrides.get(key) or self.age_index.get(key)
                    if birth_year:
                        p["birth_year"] = birth_year
                    break

            if has_verified_age:
                out.append(p)
                continue

            # Standard filtering for other players
            if not self._team_ok(p.get("team","")): continue

            # For young players (Under 25), be more lenient with season filtering
            by = _valid_birth_year(p.get("birth_year"))
            is_young = by is not None and (REF_YEAR - by) <= 25

            if self.season_filter and not is_young:
                if (p.get("season") or "").strip() != self.season_filter:
                    continue

            if by is not None and (REF_YEAR - by) > 36:  # taglio hard vecchissimi
                continue
            out.append(p)

        self.filtered_roster = out
        synthetic_count = len(getattr(self, '_synthetic_under21_players', []))
        LOG.info("[Assistant] Pool filtrato: %d record principali + %d synthetic U21, stagione=%s",
                len(out), synthetic_count, self.season_filter or "ANY")

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
        # Get excluded players from corrections manager
        excluded_players = []
        if self.corrections_manager:
            try:
                excluded_players = [name.lower() for name in self.corrections_manager.get_excluded_players()]
            except Exception as e:
                LOG.error(f"Error getting excluded players in _pool_by_role: {e}")
        
        filtered_pool = []
        for p in self.filtered_roster:
            if _role_letter(p.get("role") or p.get("role_raw","")) == r:
                # Create a copy to avoid modifying the original
                player_copy = dict(p)
                
                # Apply team corrections
                if self.corrections_manager:
                    player_name = player_copy.get("name", "")
                    current_team = player_copy.get("team", "")
                    corrected_team = self.corrections_manager.get_corrected_team(player_name, current_team)
                    if corrected_team and corrected_team != current_team:
                        player_copy["team"] = corrected_team
                        LOG.info(f"[Pool] Applied team correction: {player_name} {current_team} → {corrected_team}")
                
                # Skip excluded players - use fuzzy matching
                player_name = (player_copy.get("name") or "").lower()
                should_skip = False
                for excluded in excluded_players:
                    excluded_lower = excluded.lower()
                    # Check if excluded name is contained in player name or vice versa
                    if excluded_lower in player_name or player_name in excluded_lower:
                        should_skip = True
                        break
                    # Also check if main part of name matches
                    excluded_parts = excluded_lower.split()
                    player_parts = player_name.split()
                    if any(part in player_parts for part in excluded_parts if len(part) > 2):
                        should_skip = True
                        break
                if not should_skip:
                    filtered_pool.append(player_copy)
                
        return filtered_pool

    def _age_from_by(self, by: Optional[int]) -> Optional[int]:
        try:
            age = REF_YEAR - int(by)
            # Sanity check: age should be reasonable for professional players
            if age < 15 or age > 45:
                return None
            return age
        except Exception:
            return None

    # ---------- Selettori ----------
    def _select_under(self, r: str, max_age: int = 21, take: int = 3) -> List[Dict[str,Any]]:
        pool=[]

        # Get ALL players from filtered roster and check role + age
        LOG.info(f"[Under21] Looking for {r} players under {max_age} in {len(self.filtered_roster)} total players")

        # Debug: check all override players for this role
        override_matches = []
        for key, birth_year in self.overrides.items():
            if "@@" in key:
                name, team = key.split("@@", 1)

                # Create unique identifier for this player
                player_id = f"{_norm_name(name)}_{_norm_team(team)}"

                # Check role, matching logic needs to be consistent
                role = self.override_roles.get(key)
                is_role_match = False
                if role == r:
                    is_role_match = True

                if is_role_match:
                    age = self._age_from_by(birth_year)
                    if age is not None and age <= max_age:
                        override_matches.append(f"{name} ({team}) - age {age}")

        LOG.info(f"[Under21] Total U{max_age} players in overrides: {len(override_matches)}")
        if override_matches[:5]:  # Show first 5
            LOG.info(f"[Under21] Examples: {', '.join(override_matches[:5])}")

        # Check each player in filtered roster + synthetic under21 players
        role_matches = 0
        age_matches = 0
        final_matches = 0
        seen_players = set()  # Prevent duplicate entries

        # Combine regular roster with synthetic under21 players for this query
        all_players = list(self.filtered_roster)
        if hasattr(self, '_synthetic_under21_players'):
            all_players.extend(self._synthetic_under21_players)

        for p in all_players:
            # Create unique identifier for this player
            name = p.get("name", "").strip()
            team = p.get("team", "").strip()
            player_id = f"{_norm_name(name)}_{_norm_team(team)}"

            if player_id in seen_players:
                continue
            seen_players.add(player_id)

            # Check role - use override role if available, otherwise use player role
            player_role = p.get("role", "").strip().upper()
            role_raw = p.get("role_raw", "").strip().upper()

            # Check if we have role info from overrides
            override_role = None
            for key in self.overrides.keys():
                if "@@" in key:
                    key_name, key_team = key.split("@@", 1)
                    if (_norm_name(key_name) == _norm_name(name) and
                        _norm_team(key_team) == _norm_team(team)):
                        override_role = self.override_roles.get(key)
                        break

            # Use override role if available, otherwise use player role
            effective_role = override_role or player_role

            # Role matching
            is_role_match = False
            if r == "D":
                is_role_match = (effective_role == "D" or player_role in ["D"] or
                               any(x in role_raw for x in ["DIFENSOR", "DIFENSORE", "DEF", "DC", "CB", "RB", "LB", "TD", "TS"]))
            elif r == "C":
                is_role_match = (effective_role == "C" or player_role in ["C"] or
                               any(x in role_raw for x in ["CENTROCAMP", "MED", "MEZZ", "CM", "CAM", "CDM", "AM", "TQ"]))
            elif r == "A":
                is_role_match = (effective_role == "A" or player_role in ["A"] or
                               any(x in role_raw for x in ["ATTACC", "ATT", "ST", "CF", "LW", "RW", "SS", "PUN"]))
            elif r == "P":
                is_role_match = (effective_role == "P" or player_role in ["P"] or
                               any(x in role_raw for x in ["PORTIER", "GK", "POR"]))

            if is_role_match:
                role_matches += 1

                # Check age - try to find birth year from overrides first
                birth_year = p.get("birth_year")
                for key in self.overrides.keys():
                    if "@@" in key:
                        key_name, key_team = key.split("@@", 1)
                        if (_norm_name(key_name) == _norm_name(name) and
                            _norm_team(key_team) == _norm_team(team)):
                            birth_year = self.overrides[key]
                            p["birth_year"] = birth_year
                            break

                if birth_year and _valid_birth_year(birth_year):
                    age = self._age_from_by(birth_year)
                    if age is not None and age <= max_age:
                        age_matches += 1
                        pool.append(p)
                        final_matches += 1
                        LOG.info(f"[Under21] MATCH: {name} ({team}) - role: {effective_role}, age: {age}")

        LOG.info(f"[Under21] Summary - Role matches: {role_matches}, Age matches: {age_matches}, Final: {final_matches}")

        # Sort by fantamedia descending, then price ascending
        pool.sort(key=lambda x: (-(x.get("_fm") or 0.0), (x.get("_price") or 9_999.0)))

        return pool[:take]

    def _select_top_by_budget(self, r: str, budget: int, take: int = 8
                              ) -> Tuple[List[Dict[str,Any]], List[Dict[str,Any]]]:
        within=[]; fm_only=[]
        
        # Get excluded players from corrections manager
        excluded_players = []
        if self.corrections_manager:
            try:
                excluded_players = [name.lower() for name in self.corrections_manager.get_excluded_players()]
            except Exception as e:
                LOG.error(f"Error getting excluded players: {e}")
        
        tmp=[]
        for p in self._pool_by_role(r):
            # Skip excluded players - use fuzzy matching
            player_name = (p.get("name") or "").lower()
            should_skip = False
            for excluded in excluded_players:
                excluded_lower = excluded.lower()
                # Check if excluded name is contained in player name or vice versa
                if excluded_lower in player_name or player_name in excluded_lower:
                    should_skip = True
                    LOG.info(f"Skipping excluded player: {p.get('name')} (matches exclusion: {excluded})")
                    break
                # Also check if main part of name matches (e.g., "arnautovic" matches "marko arnautovic")
                excluded_parts = excluded_lower.split()
                player_parts = player_name.split()
                if any(part in player_parts for part in excluded_parts if len(part) > 2):
                    should_skip = True
                    LOG.info(f"Skipping excluded player: {p.get('name')} (partial match: {excluded})")
                    break
            if should_skip:
                continue
                
            fm = p.get("_fm"); pr = p.get("_price")
            if isinstance(fm,(int,float)) and fm>0 and isinstance(pr,(int,float)) and 0<pr<=float(budget):
                q = dict(p); q["_value_ratio"] = fm / max(pr,1.0); tmp.append(q)
        tmp.sort(key=lambda x: (-x["_value_ratio"], -(x.get("_fm") or 0.0), x.get("_price") or 9_999.0))
        within = tmp[:take]

        if len(within) < take:
            tmp2=[]
            for p in self._pool_by_role(r):
                # Skip excluded players
                player_name = (p.get("name") or "").lower()
                if player_name in excluded_players:
                    continue
                    
                if p.get("_fm") is not None and (p.get("_fm") or 0.0) > 0 and p.get("_price") is None:
                    tmp2.append(p)
            tmp2.sort(key=lambda x: -(x.get("_fm") or 0.0))
            fm_only = tmp2[:max(0, take-len(within))]
        return within, fm_only

    def _select_top_role_any(self, r: str, take: int = 400) -> List[Dict[str,Any]]:
        pool=[]
        for p in self._pool_by_role(r):
            fm = p.get("_fm"); pr = p.get("_price")

            # Skip players without essential data for budget formations
            if p.get("_source") == "override_synthetic" and (fm is None or pr is None):
                continue

            fm_ok = float(fm) if isinstance(fm,(int,float)) else 0.0
            denom = pr if isinstance(pr,(int,float)) else 100.0
            vr = fm_ok / max(denom, 1.0)
            q = dict(p); q["_value_ratio"] = vr
            pool.append(q)
        pool.sort(key=lambda x: (-x.get("_value_ratio",0.0), -(x.get("_fm") or 0.0), x.get("_price") if isinstance(x.get("_price"),(int,float)) else 9_999.0))
        return pool[:take]

    # ---------- XI Builder ----------
    def _build_formation(self, formation: Dict[str,int], budget: int) -> Dict[str,Any]:
        """Build formation with improved budget allocation to utilize more of the available budget"""
        slots = dict(formation)
        picks = {"P":[], "D":[], "C":[], "A":[]}
        used = set()
        
        # Calculate target budget allocation per role (more aggressive spending)
        total_players = sum(slots.values())
        role_budget_targets = {
            "P": int(budget * 0.15),  # 15% for goalkeeper
            "D": int(budget * 0.25),  # 25% for defenders  
            "C": int(budget * 0.35),  # 35% for midfielders
            "A": int(budget * 0.25)   # 25% for attackers
        }

        # Strategy: Pick players within budget ranges for each role
        def pick_budget_conscious_role(role: str, needed_count: int, role_budget: int):
            pool = self._select_top_role_any(role, take=500)
            
            # Apply team corrections
            if self.corrections_manager:
                for p in pool:
                    player_name = p.get("name", "")
                    current_team = p.get("team", "")
                    corrected_team = self.corrections_manager.get_corrected_team(player_name, current_team)
                    if corrected_team and corrected_team != current_team:
                        p["team"] = corrected_team

            # Filter valid players with both price and fantamedia
            valid_pool = []
            for p in pool:
                if (p.get("_source") != "override_synthetic" and 
                    p.get("_price") is not None and p.get("_fm") is not None and
                    p.get("_fm") > 0):
                    valid_pool.append(p)

            if not valid_pool:
                return []

            # Filter by affordable players for this role budget
            avg_price_per_player = role_budget // max(needed_count, 1)
            max_single_player = min(role_budget * 0.6, avg_price_per_player * 2)  # Allow some premium players
            
            affordable_pool = [p for p in valid_pool if p.get("_price", 0) <= max_single_player]
            
            if not affordable_pool:
                # Fallback to cheapest available if budget is too tight
                valid_pool.sort(key=lambda x: x.get("_price", 9999))
                affordable_pool = valid_pool[:needed_count * 3]

            # Sort by value ratio within budget
            affordable_pool.sort(key=lambda x: (-x.get("_value_ratio", 0.0), -(x.get("_fm") or 0.0)))

            # Use greedy algorithm to maximize value within budget
            chosen = []
            remaining_budget = role_budget
            remaining_slots = needed_count

            for p in affordable_pool:
                if len(chosen) >= needed_count:
                    break
                    
                price = p.get("_price", 0)
                if price <= remaining_budget and p.get("name") not in used:
                    chosen.append(p)
                    used.add(p.get("name"))
                    remaining_budget -= price
                    remaining_slots -= 1

            # If we still need players and have budget left, be more flexible
            if len(chosen) < needed_count and remaining_budget > 0:
                remaining_pool = [p for p in valid_pool if p.get("name") not in used]
                remaining_pool.sort(key=lambda x: (x.get("_price", 9999), -(x.get("_fm") or 0.0)))
                
                for p in remaining_pool:
                    if len(chosen) >= needed_count:
                        break
                    price = p.get("_price", 0)
                    if price <= remaining_budget:
                        chosen.append(p)
                        used.add(p.get("name"))
                        remaining_budget -= price

            return chosen

        # Pick players for each role with budget consciousness
        for role in ["P", "D", "C", "A"]:
            if slots[role] > 0:
                picks[role] = pick_budget_conscious_role(role, slots[role], role_budget_targets[role])
        
        # Apply team corrections to all picked players before final display
        if self.corrections_manager:
            for role in ["P", "D", "C", "A"]:
                for player in picks[role]:
                    player_name = player.get("name", "")
                    current_team = player.get("team", "")
                    corrected_team = self.corrections_manager.get_corrected_team(player_name, current_team)
                    if corrected_team and corrected_team != current_team:
                        player["team"] = corrected_team
                        LOG.info(f"[Formation Final] Applied team correction: {player_name} {current_team} → {corrected_team}")

        # Calculate actual costs
        def calculate_total_cost():
            total = 0.0
            for role_picks in picks.values():
                for p in role_picks:
                    price = p.get("_price")
                    if isinstance(price, (int, float)):
                        total += price
            return total

        total_cost = calculate_total_cost()
        leftover = max(0, budget - total_cost)

        # Calculate role budgets for display
        role_budget = {}
        for role in ["P", "D", "C", "A"]:
            role_cost = sum(p.get("_price", 0) for p in picks[role] if isinstance(p.get("_price"), (int, float)))
            role_budget[role] = int(role_cost)

        return {"picks": picks, "budget_roles": role_budget, "leftover": leftover}

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
                        f"Verifica che i dati in age_overrides.json siano corretti e che i giocatori abbiano birth_year validi (1995-2010 per U21).")
        else:
            fallback_msg = ""

        lines=[]
        for p in top:
            name=p.get("name") or "N/D"; team=p.get("team") or "—"
            birth_year = p.get("birth_year")
            age=self._age_from_by(birth_year)
            fm=p.get("_fm"); pr=p.get("_price")
            bits=[]

            # Verify age is actually under the limit
            if age is not None and age <= max_age:
                bits.append(f"{age} anni")
            else:
                # Skip this player if age verification fails
                LOG.warning(f"[Under21] Skipping {name} - age {age} exceeds {max_age}")
                continue

            if isinstance(fm,(int,float)): bits.append(f"FM {fm:.2f}")
            bits.append(f"€ {int(round(pr))}" if isinstance(pr,(int,float)) else "prezzo N/D")
            lines.append(f"- **{name}** ({team}) — " + ", ".join(bits))

        if not lines:
            return f"Non ho trovato giocatori U{max_age} validi. Controlla i dati in age_overrides.json."

        return f"Ecco i profili Under {max_age}:\n" + "\n".join(lines) + fallback_msg

    def _enhance_youth_data(self):
        """Try to estimate ages for more players to improve youth detection - DISABLED for accuracy"""
        # Disable automatic age estimation as it was causing incorrect results
        # Only use verified ages from age_overrides.json and age_index.json
        if hasattr(self, '_youth_enhanced'):
            return  # Already done

        LOG.info("[Youth Enhancement] Automatic age estimation disabled - using only verified ages from overrides")
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
            sections.append("🎯 **Entro {budget} crediti (ordine Q/P)**\n" + "\n".join(lines))
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
                # Apply team corrections one more time for display
                player_name = p.get('name', 'N/D')
                original_team = p.get('team', '—')
                team_display = original_team
                
                # FORCE team corrections for display - this ensures we always show corrected teams
                if self.corrections_manager:
                    corrected_team = self.corrections_manager.get_corrected_team(player_name, original_team)
                    if corrected_team:
                        team_display = corrected_team
                        LOG.info(f"[Formation Display] FORCED team correction: {player_name} {original_team} → {corrected_team}")
                    else:
                        # Check if there's a correction that should apply
                        LOG.info(f"[Formation Display] No correction found for {player_name} (current team: {original_team})")
                
                fm=p.get("_fm"); pr=p.get("_price"); bits=[]
                if isinstance(fm,(int,float)): bits.append(f"FM {fm:.2f}")
                bits.append(f"€ {int(round(pr))}" if isinstance(pr,(int,float)) else "prezzo N/D")
                rows.append(f"- **{player_name}** ({team_display}) — " + ", ".join(bits))
            return f"**{label}:**\n" + "\n".join(rows)

        tot=0.0
        for r in picks:
            for p in picks[r]:
                pr=p.get("_price")
                if isinstance(pr,(int,float)): tot+=pr

        out=[]
        out.append(f"📋 **Formazione {formation['D']}-{formation['C']}-{formation['A']}** (budget riferimento: {budget} crediti)")
        out.append(f"Costo effettivo: P≈{rb['P']} • D≈{rb['D']} • C≈{rb['C']} • A≈{rb['A']}")
        out.append(fmt("P","Portiere"))
        out.append(fmt("D","Difensori"))
        out.append(fmt("C","Centrocampisti"))
        out.append(fmt("A","Attaccanti"))
        out.append(f"Totale stimato: **{int(round(tot))}** crediti • Differenza: **{int(round(leftover))}**")
        out.append("_Criterio: Mix bilanciato di giocatori top/medi/economici per valore reale._")
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

    def _handle_conversational_response(self, user_text: str, state: Dict[str, Any], context_messages: Optional[List[Dict[str, str]]] = None) -> Optional[str]:
        """Handle conversational patterns and context-aware responses"""
        user_lower = user_text.lower().strip()
        history = state.get("conversation_history", [])
        
        # Check for team correction feedback (e.g., "Luca Pellegrini gioca nella Lazio")
        team_correction_patterns = [
            r"(\w+(?:\s+\w+)*)\s+gioca\s+nell?[ao]\s+(\w+)",
            r"(\w+(?:\s+\w+)*)\s+è\s+nell?[ao]\s+(\w+)",
            r"(\w+(?:\s+\w+)*)\s+sta\s+nell?[ao]\s+(\w+)"
        ]
        
        for pattern in team_correction_patterns:
            match = re.search(pattern, user_lower)
            if match:
                player_name = match.group(1).strip().title()
                team_name = match.group(2).strip().title()
                
                LOG.info(f"[Conversational] Team correction detected: {player_name} → {team_name}")
                
                # Apply the correction
                if self.corrections_manager:
                    # Find the player's current team in roster (check transfers too)
                    current_team = None
                    for p in self.roster:
                        roster_name = (p.get("name", "") or p.get("Name", "")).lower()
                        if roster_name == player_name.lower():
                            current_team = p.get("team", "")
                            break
                    
                    if current_team:
                        self.corrections_manager.update_player_team(player_name, current_team, team_name)
                        LOG.info(f"[Conversational] Applied correction: {player_name} {current_team} → {team_name}")
                        
                        # Refresh data
                        self.roster = self.corrections_manager.apply_corrections_to_data(self.roster)
                        self._make_filtered_roster()
                        
                        return f"✅ Perfetto! Ho aggiornato i dati: **{player_name}** ora risulta correttamente nella **{team_name}**. Grazie per la correzione! 🎯\n\nVuoi che ricontrolli gli ultimi acquisti con i dati aggiornati?"
                    else:
                        # Even if not found in current roster, still add the correction for future transfers
                        self.corrections_manager.update_player_team(player_name, "Juventus", team_name)  # Assume correction from Juventus since that's the context
                        LOG.info(f"[Conversational] Applied correction for transfer data: {player_name} Juventus → {team_name}")
                        
                        return f"✅ Perfetto! Ho registrato la correzione: **{player_name}** appartiene alla **{team_name}**. Questo aggiornerà i futuri elenchi di trasferimenti. 🎯\n\nVuoi che ricontrolli gli ultimi acquisti con i dati aggiornati?"
                else:
                    return f"📝 Noted: **{player_name}** gioca nella **{team_name}**. I dati di trasferimento potrebbero essere obsoleti o incompleti."
        
        # Greeting patterns
        greeting_patterns = ["ciao", "buongiorno", "buonasera", "salve", "hey", "hello"]
        if any(pattern in user_lower for pattern in greeting_patterns) and len(user_lower) < 20:
            return "Ciao! 👋 Sono qui per aiutarti con il fantacalcio. Dimmi cosa ti serve: formazioni, consigli Under 21, strategie d'asta o altro!"
            
        # Thank you patterns
        thanks_patterns = ["grazie", "perfetto", "ottimo", "bene così", "va bene"]
        if any(pattern in user_lower for pattern in thanks_patterns) and len(user_lower) < 30:
            suggestions = [
                "Prego! Posso aiutarti con altro? Magari una formazione diversa o consigli per altri ruoli?",
                "Figurati! Hai bisogno di altri consigli per la tua squadra?",
                "Di nulla! Vuoi che analizziamo qualche altro aspetto della tua strategia fantacalcio?"
            ]
            import random
            return random.choice(suggestions)
            
        # Context-aware follow-ups
        if len(history) >= 2:
            last_assistant_msg = None
            for msg in reversed(history):
                if msg.get("role") == "assistant":
                    last_assistant_msg = msg.get("content", "")
                    break
                    
            # If last response contained Under 21 players, offer alternatives
            if last_assistant_msg and "Under 21" in last_assistant_msg:
                if any(word in user_lower for word in ["altri", "ancora", "alternative", "più"]):
                    # Extract role from last intent
                    last_intent = state.get("last_intent", {})
                    role = last_intent.get("role", "A")
                    max_age = last_intent.get("max_age", 21)
                    take = last_intent.get("take", 3)
                    
                    # Get more players
                    return self._answer_under21(role, max_age, take + 2)
                    
            # If last response contained formation, offer adjustments
            if last_assistant_msg and "Formazione" in last_assistant_msg:
                if any(word in user_lower for word in ["cambia", "modifica", "altro", "diverso"]):
                    return "Dimmi che modifica vuoi: cambiare modulo (es. '4-4-2'), aumentare/diminuire budget, o preferenze per ruoli specifici?"
                    
        # Clarification requests
        unclear_patterns = ["non ho capito", "cosa intendi", "spiegami", "come funziona"]
        if any(pattern in user_lower for pattern in unclear_patterns):
            return """Posso aiutarti con:
🏆 **Formazioni**: "formazione 5-3-2 budget 200"
⚡ **Under 21**: "3 attaccanti under 21" o "difensori u21"
💰 **Budget**: "top attaccanti budget 150"
🎯 **Strategie**: "strategia asta"
⚙️ **Portieri**: "migliori portieri budget 20"

Cosa ti interessa di più?"""

        # Context from previous interactions
        if any(word in user_lower for word in ["e poi", "inoltre", "anche", "pure"]):
            return "Dimmi pure, sono qui per aiutarti! Che altro ti serve per la tua strategia fantacalcio?"
            
        return None

    def _parse_intent(self, text: str, mode: str) -> Dict[str,Any]:
        lt = (text or "").lower().strip()
        intent={"type":"generic","mode":mode,"raw":lt}

        # Check for goalkeeper requests FIRST, as they might contain budget numbers
        if any(x in lt for x in ["portieri", "portiere", "goalkeeper", "gk"]):
            intent.update({"type": "goalkeeper", "original_text": text})
            return intent

        # Check for transfer/acquisitions requests
        if any(x in lt for x in ["ultimi acquisti", "acquisiti", "nuovi acquisti", "trasferimenti", "mercato", "acquisti"]):
            team = None
            for team_name in ["inter", "milan", "juventus", "napoli", "roma", "lazio", "atalanta", "fiorentina", "bologna", "torino", "genoa", "udinese", "cagliari", "lecce", "empoli", "monza", "venezia", "verona", "como", "parma"]:
                if team_name in lt:
                    team = team_name.title()
                    break
            intent.update({"type": "transfers", "team": team, "original_text": text})
            return intent

        # formazione
        if "formazione" in lt and re.search(r"\b[0-5]\s*-\s*[0-5]\s*-\s*[0-5]\b", lt):
            fm = re.search(r"\b([0-5])\s*-\s*([0-5])\s*-\s*([0-5])\b", lt).group(0)
            budget = self._parse_first_int(lt) or 500
            intent.update({"type":"formation","formation_text":fm, "budget":budget})
            return intent

        # under - CHECK THIS FIRST before budget detection
        if any(k in lt for k in ["under 21","under-21","under21","u21","under 23","u23"]):
            max_age = 21 if "23" not in lt else 23
            role="A"
            if "difensor" in lt or "terzin" in lt or "centrale" in lt: role="D"
            elif "centrocamp" in lt or "mezzala" in lt or "regista" in lt: role="C"
            elif "portier" in lt: role="P"
            take = 3
            m = re.search(r"\b(\d)\s+(nomi|giocatori|attaccant)\b", lt)
            if m: take = max(1, int(m.group(1)))
            intent.update({"type":"under","role":role,"max_age":max_age,"take":take})
            return intent

        # top attaccanti con budget
        if ("attacc" in lt or "top attaccanti" in lt or "punta" in lt) and ("budget" in lt or self._parse_first_int(lt)):
            budget = self._parse_first_int(lt) or 150
            intent.update({"type":"budget_attackers","budget":budget})
            return intent

        # asta
        if "strategia" in lt and "asta" in lt:
            intent.update({"type":"asta"})
            return intent

        # followup secco
        if lt in self._FOLLOWUP_TOKENS:
            intent.update({"type":"followup"})
            return intent

        # fallback generico: LLM
        intent.update({"type": "generic"})
        return intent

    # ---------- respond ----------
    def get_response(self, user_text: str, mode: str, context: Dict[str, Any]) -> str:
        """Main logic to get a response based on intent"""
        st = dict(context or {})
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
        elif intent["type"] == "goalkeeper":
            reply = self._handle_goalkeeper_request(intent.get("original_text", user_text))
        elif intent["type"] == "transfers":
            reply = self._handle_transfers_request(intent.get("team"), intent.get("original_text", user_text))
        elif intent["type"] == "asta":
            reply = ("🧭 **Strategia Asta (Classic)**\n"
                     "1) Tenere liquidità per gli slot premium in A.\n"
                     "2) Difesa a valore: esterni titolari con FM stabile.\n"
                     "3) Centrocampo profondo (rotazioni riducono i buchi).")
        elif intent["type"] == "generic":
             reply = self._llm_complete(user_text, context_messages=[], state=st)
             if not reply or "non disponibile" in reply.lower():
                reply = "Dimmi: *formazione 5-3-2 500*, *top attaccanti budget 150*, *2 difensori under 21*, oppure *strategia asta*."
        else:
            reply = "Non ho capito la richiesta. Prova con: *formazione 5-3-2 500*, *top attaccanti budget 150*, *2 difensori under 21*, oppure *strategia asta*."

        st["last_intent"] = intent
        return reply

    def respond(self, user_text: str, mode: str = "classic",
                state: Optional[Dict[str, Any]] = None,
                context_messages: Optional[List[Dict[str, str]]] = None) -> Tuple[str, Dict[str, Any]]:
        """Main response method that applies corrections and filters"""
        state = state or {}
        
        # Initialize conversation history if not present
        if "conversation_history" not in state:
            state["conversation_history"] = []
            
        # Add current user message to history
        state["conversation_history"].append({
            "role": "user", 
            "content": user_text,
            "timestamp": time.time()
        })
        
        # Keep only last 10 exchanges to prevent memory overflow
        state["conversation_history"] = state["conversation_history"][-20:]

        # Check for conversational patterns and context
        response = self._handle_conversational_response(user_text, state, context_messages)
        
        if not response:
            # Get response from main logic if no conversational response
            response = self.get_response(user_text, mode=mode, context=state)

        # Apply corrections if corrections manager is available
        if self.corrections_manager:
            try:
                corrected_response, applied_corrections = self.corrections_manager.apply_corrections_to_text(response)
                if applied_corrections:
                    LOG.info("Applied %d corrections to response", len(applied_corrections))
                    response = corrected_response
            except Exception as e:
                LOG.error("Error applying corrections in respond: %s", e)

        # Add assistant response to history
        state["conversation_history"].append({
            "role": "assistant",
            "content": response,
            "timestamp": time.time()
        })

        return response, state


    def _handle_transfers_request(self, team: str, user_text: str) -> str:
        """Handle transfer/acquisitions requests with proper data validation and corrections"""
        try:
            # Check if user wants to see all transfers
            show_all = "tutti" in user_text.lower() or "all" in user_text.lower()
            
            # Get excluded players from corrections manager
            excluded_players = []
            if self.corrections_manager:
                try:
                    excluded_players = [name.lower() for name in self.corrections_manager.get_excluded_players()]
                    LOG.info(f"[Transfers] Excluded players: {excluded_players}")
                except Exception as e:
                    LOG.error(f"Error getting excluded players in transfers: {e}")
            
            # First, check roster data for actual current transfers (direction = "in" only)
            roster_transfers = []
            seen_players = set()
            
            for p in self.roster:
                if p.get("type") == "transfer" and p.get("direction") == "in":
                    player_name = p.get("Name") or p.get("name", "")
                    original_team_name = p.get("team", "")
                    team_name = original_team_name
                    season = p.get("season", "")
                    
                    # Skip excluded players - use fuzzy matching
                    player_name_lower = player_name.lower().strip()
                    should_skip = False
                    for excluded in excluded_players:
                        excluded_lower = excluded.lower()
                        # Check if excluded name is contained in player name or vice versa
                        if excluded_lower in player_name_lower or player_name_lower in excluded_lower:
                            should_skip = True
                            LOG.info(f"[Transfers] Skipping excluded player: {player_name} (matches exclusion: {excluded})")
                            break
                        # Also check if main part of name matches
                        excluded_parts = excluded_lower.split()
                        player_parts = player_name_lower.split()
                        if any(part in player_parts for part in excluded_parts if len(part) > 2):
                            should_skip = True
                            LOG.info(f"[Transfers] Skipping excluded player: {player_name} (partial match: {excluded})")
                            break
                    if should_skip:
                        continue
                    
                    # Apply team corrections if available
                    corrected_team = None
                    if self.corrections_manager:
                        corrected_team = self.corrections_manager.get_corrected_team(player_name, team_name)
                        if corrected_team and corrected_team != team_name:
                            team_name = corrected_team
                            LOG.info(f"[Transfers] Applied team correction: {player_name} {original_team_name} → {corrected_team}")
                    
                    # Filter by team if specified - now check against corrected team
                    if team and team.lower() not in team_name.lower():
                        # Skip this player if they've been corrected to play for a different team
                        if corrected_team and corrected_team.lower() != team.lower():
                            LOG.info(f"[Transfers] Skipping {player_name} - corrected team {corrected_team} doesn't match requested team {team}")
                            continue
                        elif not corrected_team:
                            continue
                    
                    # Check for duplicate/conflicting data
                    player_key = player_name.lower().strip()
                    if player_key in seen_players:
                        LOG.warning(f"[Transfers] Duplicate player found: {player_name} for {team_name}")
                        continue
                    seen_players.add(player_key)
                    
                    # Validate this is actually a current transfer (not a loan return)
                    fee = p.get("fee", "")
                    if "fine prestito" in fee.lower():
                        LOG.info(f"[Transfers] Skipping loan return: {player_name} to {team_name}")
                        continue
                    
                    roster_transfers.append({
                        "player": player_name,
                        "team": team_name,
                        "season": season,
                        "fee": fee,
                        "source": p.get("source", "roster"),
                        "validated": True,
                        "corrected": corrected_team is not None
                    })
            
            # Also search knowledge base for additional transfer data
            knowledge_transfers = []
            if team:
                search_terms = [f"{team} acquisti 2025", f"Transfer IN: {team}", f"{team} 2025-26"]
            else:
                search_terms = ["acquisti Serie A 2025", "Transfer IN", "direction in"]
            
            for term in search_terms:
                try:
                    results = self.km.search_knowledge(
                        text=term, 
                        n_results=10,
                        include=["documents", "metadatas"]
                    )
                    
                    if results and "metadatas" in results:
                        for metadata_list in results["metadatas"]:
                            for metadata in metadata_list:
                                if (metadata.get("type") == "transfer" and 
                                    metadata.get("direction") == "in"):
                                    
                                    player_name = metadata.get("player", "")
                                    team_name = metadata.get("team", "")
                                    
                                    if player_name and team_name:
                                        # Apply team corrections
                                        if self.corrections_manager:
                                            corrected_team = self.corrections_manager.get_corrected_team(player_name, team_name)
                                            if corrected_team:
                                                team_name = corrected_team
                                        
                                        # Filter by team
                                        if team and team.lower() not in team_name.lower():
                                            continue
                                            
                                        knowledge_transfers.append({
                                            "player": player_name,
                                            "team": team_name,
                                            "season": metadata.get("season", "2025-26"),
                                            "fee": metadata.get("fee", ""),
                                            "source": "knowledge_base",
                                            "validated": False
                                        })
                except Exception as e:
                    LOG.debug(f"Error searching knowledge for {term}: {e}")
                    continue
            
            # Combine and validate transfers
            all_transfers = roster_transfers + knowledge_transfers
            
            # Final deduplication and validation
            validated_transfers = []
            player_names_seen = set()
            
            for t in all_transfers:
                player_lower = t["player"].lower().strip()
                
                # Skip if already processed
                if player_lower in player_names_seen:
                    continue
                player_names_seen.add(player_lower)
                
                # Skip excluded players - apply the same logic as roster transfers
                should_skip = False
                for excluded in excluded_players:
                    excluded_lower = excluded.lower()
                    # Check if excluded name is contained in player name or vice versa
                    if excluded_lower in player_lower or player_lower in excluded_lower:
                        should_skip = True
                        LOG.info(f"[Transfers] Skipping excluded player from KB: {t['player']} (matches exclusion: {excluded})")
                        break
                    # Also check if main part of name matches
                    excluded_parts = excluded_lower.split()
                    player_parts = player_lower.split()
                    if any(part in player_parts for part in excluded_parts if len(part) > 2):
                        should_skip = True
                        LOG.info(f"[Transfers] Skipping excluded player from KB: {t['player']} (partial match: {excluded})")
                        break
                if should_skip:
                    continue
                
                # Check if this player has been corrected to play for a different team
                if self.corrections_manager:
                    corrected_team = self.corrections_manager.get_corrected_team(t["player"], t["team"])
                    if corrected_team and corrected_team.lower() != t["team"].lower():
                        # Player has been corrected to different team
                        if team and corrected_team.lower() == team.lower():
                            # Player actually belongs to the requested team
                            t["team"] = corrected_team
                            t["corrected"] = True
                            LOG.info(f"[Transfers] Corrected {t['player']}: now correctly in {corrected_team}")
                        elif team and corrected_team.lower() != team.lower():
                            # Player belongs to different team, skip
                            LOG.info(f"[Transfers] Skipping {t['player']}: corrected to {corrected_team}, not {team}")
                            continue
                        else:
                            # No specific team filter, update team info
                            t["team"] = corrected_team
                            t["corrected"] = True
                
                # Validate player exists in current Serie A context
                is_valid_transfer = True
                
                # Check if player has conflicting data (plays for different team)
                for roster_player in self.roster:
                    roster_name = (roster_player.get("name") or "").lower().strip()
                    roster_team = roster_player.get("team", "").lower().strip()
                    
                    if (roster_name == player_lower and 
                        roster_player.get("type") != "transfer" and
                        roster_team != t["team"].lower().strip()):
                        
                        LOG.warning(f"[Transfers] Conflicting data for {t['player']}: transfer says {t['team']}, roster says {roster_player.get('team')}")
                        
                        # If corrections manager has info, use that
                        if self.corrections_manager:
                            corrected_team = self.corrections_manager.get_corrected_team(t["player"], roster_player.get("team", ""))
                            if corrected_team:
                                # Check if corrected team matches what we're looking for
                                if team and corrected_team.lower() != team.lower():
                                    LOG.info(f"[Transfers] Skipping {t['player']}: corrected to {corrected_team}, not {team}")
                                    continue
                                t["team"] = corrected_team
                                t["corrected"] = True
                                LOG.info(f"[Transfers] Applied correction: {t['player']} now correctly shows as {corrected_team}")
                            else:
                                # Mark as potentially invalid
                                t["needs_validation"] = True
                
                validated_transfers.append(t)
            
            if validated_transfers:
                if team:
                    if show_all:
                        reply = f"🔄 **Tutti gli acquisti {team} (2025-26):**\n\n"
                    else:
                        reply = f"🔄 **Ultimi acquisti {team} (2025-26):**\n\n"
                else:
                    if show_all:
                        reply = "🔄 **Tutti gli acquisti Serie A (2025-26):**\n\n"
                    else:
                        reply = "🔄 **Ultimi acquisti Serie A (2025-26):**\n\n"
                
                # Determine how many to show
                max_display = len(validated_transfers) if show_all else 8
                
                for i, transfer in enumerate(validated_transfers[:max_display], 1):
                    fee_info = ""
                    if transfer.get("fee") and "fine prestito" not in transfer.get("fee", "").lower():
                        fee_info = f" • {transfer['fee']}"
                    
                    source_info = ""
                    if "apify" in transfer.get("source", "").lower():
                        source_info = " 🆕"
                    elif transfer.get("corrected"):
                        source_info = " ✅"
                    elif transfer.get("needs_validation"):
                        source_info = " ⚠️"
                    
                    reply += f"{i}. **{transfer['player']}** → {transfer['team']}{fee_info}{source_info}\n"
                
                if not show_all and len(validated_transfers) > 8:
                    reply += f"\n*...e altri {len(validated_transfers) - 8} acquisti*"
                elif show_all:
                    reply += f"\n*Totale: {len(validated_transfers)} acquisti*"
                
                # Add validation notes
                validation_notes = []
                corrected_count = sum(1 for t in validated_transfers if t.get("corrected"))
                needs_validation_count = sum(1 for t in validated_transfers if t.get("needs_validation"))
                
                if corrected_count > 0:
                    validation_notes.append(f"✅ {corrected_count} correzioni applicate")
                if needs_validation_count > 0:
                    validation_notes.append(f"⚠️ {needs_validation_count} da verificare")
                
                if validation_notes:
                    reply += f"\n\n💡 *{', '.join(validation_notes)}*"
                    
                return reply
            else:
                if team:
                    return f"❌ Non ho trovato acquisti recenti validati per **{team}**.\n\n💡 **Suggerimenti:**\n• Verifica che il nome della squadra sia corretto\n• I dati potrebbero necessitare di aggiornamento\n• Controlla se ci sono conflitti nei dati di trasferimento"
                else:
                    return "❌ Non ho trovato acquisti recenti validati nel database.\n\n🔄 **Possibili cause:**\n• I dati necessitano di refresh\n• Conflitti nei dati di trasferimento\n• Problema temporaneo con la knowledge base"
                    
        except Exception as e:
            LOG.error(f"Error in _handle_transfers_request: {e}")
            return "⚠️ Errore nel recupero dei dati di mercato. Riprova più tardi."

    def _extract_player_from_text(self, text: str) -> str:
        """Extract player name from transfer document text"""
        if not text:
            return ""
        
        # Look for patterns like "Transfer IN: Player Name" or "Player Name → Team"
        import re
        
        patterns = [
            r"Transfer IN:\s*([A-ZÀ-ÿ][a-zA-ZÀ-ÿ\s]+?)(?:\s*→|\s*\(|\s*$)",
            r"([A-ZÀ-ÿ][a-zA-ZÀ-ÿ\s]+?)\s*→",
            r"Player:\s*([A-ZÀ-ÿ][a-zA-ZÀ-ÿ\s]+?)(?:\s|$)",
            r"^([A-ZÀ-ÿ][a-zA-ZÀ-ÿ\s]+?)(?:\s*\(|\s*-|\s*→)"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                player_name = match.group(1).strip()
                # Basic validation
                if len(player_name) > 2 and not any(word in player_name.lower() for word in ["transfer", "from", "to", "team"]):
                    return player_name
        
        return ""

    def _handle_goalkeeper_request(self, user_text: str) -> str:
        """Handle goalkeeper-specific requests with proper Serie A filtering"""
        pool = self._collect_all_players()
        goalkeepers = []

        # Updated goalkeeper data for 2025-26 Serie A season
        # These are approximate values and might need further refinement
        updated_gk_data = {
            "mike maignan": {"team": "Milan", "price": 25, "fantamedia": 6.4},
            "yann sommer": {"team": "Inter", "price": 18, "fantamedia": 6.1},
            "michele di gregorio": {"team": "Juventus", "price": 20, "fantamedia": 6.0},
            "alex meret": {"team": "Napoli", "price": 16, "fantamedia": 5.9},
            "ivan provedel": {"team": "Lazio", "price": 14, "fantamedia": 5.8},
            "mile svilar": {"team": "Roma", "price": 13, "fantamedia": 5.7},
            "marco carnesecchi": {"team": "Atalanta", "price": 12, "fantamedia": 5.6},
            "devis vasquez": {"team": "Empoli", "price": 8, "fantamedia": 5.4}, # Loan/transfer status might vary
            "maduka okoye": {"team": "Udinese", "price": 7, "fantamedia": 5.3},
            "elia caprile": {"team": "Cagliari", "price": 6, "fantamedia": 5.2}
        }

        for p in pool:
            role_bucket = self._role_bucket(p.get("role") or "")
            if role_bucket != "P":
                continue

            name = (p.get("name") or "").lower().strip()
            team = p.get("team") or ""

            # Use updated data if available, otherwise fallback to general data
            if name in updated_gk_data:
                gk_data = updated_gk_data[name]
                goalkeepers.append({
                    "name": p.get("name"),
                    "team": gk_data["team"],
                    "price": gk_data["price"],
                    "fantamedia": gk_data["fantamedia"]
                })
            elif self._is_serie_a_team(team):
                goalkeepers.append({
                    "name": p.get("name"),
                    "team": team,
                    "price": _safe_float(p.get("price"), 0.0),
                    "fantamedia": _safe_float(p.get("fantamedia"), 0.0)
                })

        # Extract budget from request, default to 50 if not found
        budget_match = re.search(r"budget\s+(\d+)", user_text)
        budget = int(budget_match.group(1)) if budget_match else 50

        # Filter by budget and sort
        filtered_gk = [gk for gk in goalkeepers if gk["price"] <= budget]
        filtered_gk.sort(key=lambda x: (-x["fantamedia"], x["price"], x["name"]))

        if not filtered_gk:
            return f"Non ho trovato portieri di Serie A con budget {budget} crediti."

        lines = []
        for gk in filtered_gk[:8]:  # Show top 8
            lines.append(f"**{gk['name']}** ({gk['team']}) — € {int(gk['price'])}")

        return f"📈 **Migliori Portieri (budget {budget} crediti, Serie A):**\n\n" + "\n".join([f"{i+1}. {line}" for i, line in enumerate(lines)])

    def _collect_all_players(self) -> List[Dict[str, Any]]:
        """
        Collects all available player data, combining roster, external cache, and KM.
        Applies corrections and deduplication.
        """
        all_players = list(self.roster)
        try:
            km_players = self._km_fetch_players()
            # Apply corrections to KM data as well
            if self.corrections_manager:
                km_players = self.corrections_manager.apply_corrections_to_data(km_players)
            all_players.extend(km_players)
        except Exception as e:
            LOG.error("[Assistant] errore nel fetch KM: %s", e)

        seen = set()
        deduped: List[Dict[str, Any]] = []
        for p in all_players:
            if not isinstance(p, dict):
                continue
            name = (p.get("name") or "").strip()
            team = (p.get("team") or "").strip()
            if not name:
                continue

            # Enhanced deduplication with team consideration
            key = f"{name.lower()}_{team.lower()}"
            if key in seen:
                continue
            seen.add(key)

            # Additional data quality checks
            if self._is_valid_player_data(p):
                deduped.append(p)

        return deduped

    def _km_fetch_players(self) -> List[Dict[str, Any]]:
        """Fetches player data from Knowledge Manager, applies basic normalization."""
        # This is a placeholder. A real implementation would query KM for player data.
        # For now, it returns an empty list as KM integration is complex and context-specific.
        # Example: Query KM for all players with 'Serie A' in their description or team.
        LOG.info("[Assistant] Fetching players from Knowledge Manager (placeholder)...")
        return []

    def _is_serie_a_team(self, team: str) -> bool:
        """Check if team is a Serie A team"""
        if self.corrections_manager:
            return self.corrections_manager.is_serie_a_team(team)
        else:
            return _norm_team(team) in SERIE_A_WHITELIST

    def _role_bucket(self, raw_role: str) -> str:
        """Convert role to standardized bucket (P, D, C, A)"""
        r = (raw_role or "").strip().upper()
        if not r:
            return ""
        if r in {"P", "GK", "POR", "PORTIERE"}:
            return "P"
        if r in {"D", "DEF", "DC", "CB", "RB", "LB", "TD", "TS", "BR", "DIFENSORE"}:
            return "D"
        if r in {"C", "CM", "MED", "M", "MEZ", "RM", "LM", "CC", "TQ", "AM", "TRE", "CENTROCAMPISTA"}:
            return "C"
        if r in {"A", "ATT", "FWD", "ATTACCANTE", "PUN", "PUNTA", "SS", "CF", "LW", "RW", "EST", "W", "LW", "RW"}:
            return "A"
        if r and r[0] in {"P", "D", "C", "A"}:
            return r[0]
        return ""

    def _is_valid_player_data(self, player: Dict[str, Any]) -> bool:
        """Validate player data quality"""
        name = player.get("name", "").strip()
        team = player.get("team", "").strip()

        # Basic validation
        if not name or len(name) < 2:
            return False

        # Check if team is Serie A (if corrections manager available)
        if not self._is_serie_a_team(team):
            return False

        # Check for obviously invalid data patterns
        invalid_patterns = ["test", "example", "dummy", "placeholder", "sconosciuto"]
        if any(pattern in name.lower() for pattern in invalid_patterns):
            return False

        return True

    def _get_roster_context(self) -> str:
        """Get a representative sample of roster data for LLM context"""
        if not hasattr(self, 'filtered_roster') or not self.filtered_roster:
            return "ROSTER VUOTO - aggiornare i dati"

        # Get top players by role for context
        context_parts = []

        for role in ["A", "C", "D", "P"]:
            role_players = [p for p in self.filtered_roster if self._role_bucket(p.get("role") or "") == role]
            # Sort by fantamedia desc, then by price asc
            role_players.sort(key=lambda x: (-(x.get("_fm") or 0.0), (x.get("_price") or 9999.0)))

            role_name = {"A": "Attaccanti", "C": "Centrocampisti", "D": "Difensori", "P": "Portieri"}[role]
            context_parts.append(f"\n{role_name} TOP (roster corrente):")

            for i, p in enumerate(role_players[:5]):  # Top 5 per ruolo
                name = p.get("name", "N/D")
                team = p.get("team", "N/D")
                fm = p.get("_fm")
                price = p.get("_price")

                fm_str = f"FM {fm:.2f}" if isinstance(fm, (int, float)) else "FM N/D"
                price_str = f"€{int(price)}" if isinstance(price, (int, float)) else "€N/D"

                context_parts.append(f"  {i+1}. {name} ({team}) - {fm_str}, {price_str}")

        total_players = len(self.filtered_roster)
        context_parts.insert(0, f"ROSTER CORRENTE ({total_players} giocatori Serie A 2024-25/2025-26):")

        return "\n".join(context_parts)

    def update_player_data(self, player_name: str, **updates):
        """Update player data with corrections tracking"""
        if not self.corrections_manager:
            return "Corrections manager not available"

        for field, new_value in updates.items():
            if field == "team":
                # Find old team value
                old_team = None
                for p in self.roster:
                    if p.get("name", "").lower() == player_name.lower():
                        old_team = p.get("team", "")
                        break
                # Use the corrected team name if available before updating
                corrected_team_name = self.corrections_manager.get_corrected_team(player_name, new_value)
                final_new_value = corrected_team_name if corrected_team_name else new_value

                self.corrections_manager.update_player_team(player_name, old_team or "Unknown", final_new_value)
            else:
                self.corrections_manager.add_correction(player_name, f"{field.upper()}_UPDATE", None, str(new_value))

        # Refresh data
        self.roster = self.corrections_manager.apply_corrections_to_data(self.roster)
        LOG.info(f"[Assistant] Applied updates for {player_name}: {updates}")
        return f"Updated {player_name}: {updates}"

    def remove_player_permanently(self, player_name: str):
        """Permanently remove player from all recommendations"""
        if not self.corrections_manager:
            return "Corrections manager not available"

        result = self.corrections_manager.remove_player(player_name)
        # Refresh data
        self.roster = self.corrections_manager.apply_corrections_to_data(self.roster)
        LOG.info(f"[Assistant] Removed player permanently: {player_name}")
        return result

    def get_data_quality_report(self):
        """Get comprehensive data quality report"""
        if not self.corrections_manager:
            return {"error": "Corrections manager not available"}

        report = self.corrections_manager.get_data_quality_report()

        # Add roster statistics
        total_players = len(self.roster)
        serie_a_players = len([p for p in self.roster if self.corrections_manager.is_serie_a_team(p.get("team", ""))])
        players_with_price = len([p for p in self.roster if p.get("price") is not None])
        players_with_fm = len([p for p in self.roster if p.get("fantamedia") is not None])

        report.update({
            "roster_stats": {
                "total_players": total_players,
                "serie_a_players": serie_a_players,
                "players_with_price": players_with_price,
                "players_with_fantamedia": players_with_fm,
                "data_completeness": round((players_with_price + players_with_fm) / (total_players * 2) * 100, 1) if total_players > 0 else 0
            }
        })

        return report

    # ---------------------------
    # LLM (fallback generico)
    # ---------------------------
    def _llm_complete(self, user_text: str, context_messages: List[Dict[str, str]] = None, state: Dict[str, Any] = None) -> str:
        """Complete using LLM with conversation context"""
        if not self.openai_api_key:
            LOG.warning("[Assistant] OPENAI_API_KEY not set, cannot use LLM.")
            return "⚠️ Servizio AI temporaneamente non disponibile. Configura OPENAI_API_KEY."

        try:
            import httpx

            # Build messages with context
            messages = [{"role": "system", "content": self._get_system_prompt()}]

            # Add conversation history from state for better context
            if state and "conversation_history" in state:
                # Get last 6 messages (3 exchanges) for context
                recent_history = state["conversation_history"][-6:]
                for msg in recent_history:
                    if msg.get("role") in ["user", "assistant"]:
                        messages.append({
                            "role": msg["role"],
                            "content": msg["content"]
                        })
            
            # Add external context messages if provided
            if context_messages:
                messages.extend(context_messages)

            # Add specific context for different query types
            user_lower = user_text.lower()
            
            # Enhanced context for specific queries
            if any(term in user_lower for term in ["attaccant", "miglior", "top", "punta"]):
                attackers = [p for p in self.filtered_roster if self._role_bucket(p.get("role") or "") == "A"]
                if attackers:
                    attackers.sort(key=lambda x: (-(x.get("_fm") or 0.0), (x.get("_price") or 9999.0)))
                    top_attackers = []
                    for p in attackers[:8]:
                        name = p.get("name", "")
                        team = p.get("team", "")
                        fm = p.get("_fm")
                        price = p.get("_price")
                        fm_str = f"FM {fm:.2f}" if isinstance(fm, (int, float)) else "FM N/D"
                        price_str = f"€{int(price)}" if isinstance(price, (int, float)) else "€N/D"
                        top_attackers.append(f"- {name} ({team}) - {fm_str}, {price_str}")

                    roster_context = f"ATTACCANTI DISPONIBILI NEL ROSTER:\n" + "\n".join(top_attackers)
                    messages.append({"role": "system", "content": roster_context})
            
            elif any(term in user_lower for term in ["centrocamp", "mediano", "mezz"]):
                midfielders = [p for p in self.filtered_roster if self._role_bucket(p.get("role") or "") == "C"]
                if midfielders:
                    midfielders.sort(key=lambda x: (-(x.get("_fm") or 0.0), (x.get("_price") or 9999.0)))
                    top_mids = []
                    for p in midfielders[:8]:
                        name = p.get("name", "")
                        team = p.get("team", "")
                        fm = p.get("_fm")
                        price = p.get("_price")
                        fm_str = f"FM {fm:.2f}" if isinstance(fm, (int, float)) else "FM N/D"
                        price_str = f"€{int(price)}" if isinstance(price, (int, float)) else "€N/D"
                        top_mids.append(f"- {name} ({team}) - {fm_str}, {price_str}")

                    roster_context = f"CENTROCAMPISTI DISPONIBILI NEL ROSTER:\n" + "\n".join(top_mids)
                    messages.append({"role": "system", "content": roster_context})

            # Don't add the user message again if it's already in conversation history
            if not (state and "conversation_history" in state and 
                   state["conversation_history"] and 
                   state["conversation_history"][-1].get("content") == user_text):
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

            LOG.debug("[Assistant] Calling OpenAI API with enhanced context")

            with httpx.Client(timeout=60.0) as client:
                resp = client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload
                )
                resp.raise_for_status()
                data = resp.json()
                response_content = data["choices"][0]["message"]["content"].strip()

                # Additional validation: ensure response doesn't mention players not in roster
                if self._contains_invalid_players(response_content):
                    LOG.warning("[Assistant] LLM response contained invalid players, filtering...")
                    response_content = self._filter_invalid_players(response_content)

                LOG.debug("[Assistant] OpenAI API response validated")
                return response_content

        except Exception as e:
            LOG.error("[Assistant] Errore OpenAI: %s", e)
            return "⚠️ Servizio momentaneamente non disponibile. Riprova tra poco."

    def _get_system_prompt(self) -> str:
        """Get enhanced system prompt for LLM with current roster context"""
        # Get a sample of current roster data for context
        roster_context = self._get_roster_context()

        return f"""Sei un assistente esperto e amichevole di fantacalcio italiano. Parla come un amico esperto che conosce bene il fantacalcio.

PERSONALITÀ:
- Usa un tono colloquiale e amichevole
- Mostra entusiasmo per il fantacalcio
- Usa emoji occasionalmente (⚽, 🎯, 💰, ⭐)
- Offri sempre consigli aggiuntivi pertinenti
- Ricorda il contesto della conversazione

DATI ROSTER CORRENTE:
{roster_context}

REGOLE FONDAMENTALI:
- BASATI SOLO sui giocatori nel roster sopra
- NON menzionare giocatori non disponibili (Osimhen, Kvaratskhelia, ecc.)
- Se i dati sono insufficienti, dillo chiaramente ma suggerisci alternative
- Prioritizza fantamedia e prezzo dai dati del roster

STILE CONVERSAZIONALE:
- "Ottima scelta!" invece di "È corretto"
- "Ti consiglio anche di dare un'occhiata a..." 
- "A proposito, hai considerato...?"
- "Per la tua strategia, potresti anche..."
- Fai domande di follow-up pertinenti

ESEMPI DI TONO:
❌ "I dati mostrano che Vlahović ha FM 7.18"
✅ "Vlahović è una bella scelta! ⚽ Con FM 7.18 è uno dei top, costa sui 20 crediti. Hai considerato anche Krstović del Lecce? Solo 10 crediti ma FM quasi 7!"

GESTIONE CONTESTO:
- Ricorda le richieste precedenti
- Collega i consigli alla strategia generale
- Suggerisci complementi logici (es. dopo attaccanti, proponi centrocampisti)
- Anticipa le prossime domande dell'utente

Il tuo obiettivo è essere il miglior amico fantacalcista dell'utente: competente, entusiasta e sempre pronto ad aiutare! 🏆"""

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

    def _contains_invalid_players(self, text: str) -> bool:
        """Check if text contains players not in current roster"""
        # Known outdated players that shouldn't appear
        outdated_players = [
            "osimhen", "victor osimhen", "kvaratskhelia", "kvara", 
            "donnarumma", "gianluigi donnarumma", "skriniar", "milan skriniar"
        ]

        text_lower = text.lower()
        return any(player in text_lower for player in outdated_players)

    def _filter_invalid_players(self, text: str) -> str:
        """Filter out mentions of players not in current roster"""
        if not self._contains_invalid_players(text):
            return text

        # Get actual roster data for replacement
        attackers = [p for p in self.filtered_roster if self._role_bucket(p.get("role") or "") == "A"]
        if not attackers:
            return "Non ho dati sufficienti sugli attaccanti nel roster corrente. Verifica che i dati siano aggiornati."

        # Sort by fantamedia and get top performers
        attackers.sort(key=lambda x: (-(x.get("_fm") or 0.0), (x.get("_price") or 9999.0)))

        response_lines = []
        response_lines.append("Basandomi sui dati del roster corrente, ecco i migliori attaccanti di Serie A:")

        for i, p in enumerate(attackers[:5], 1):
            name = p.get("name", "")
            team = p.get("team", "")
            fm = p.get("_fm")
            price = p.get("_price")

            line = f"{i}. **{name}** ({team})"

            details = []
            if isinstance(fm, (int, float)):
                details.append(f"FM {fm:.2f}")
            if isinstance(price, (int, float)):
                details.append(f"€{int(price)}")

            if details:
                line += f" — {', '.join(details)}"

            response_lines.append(line)

        response_lines.append("\n*Dati basati sul roster corrente. Se mancano giocatori attesi, verifica gli aggiornamenti dei dati.*")

        return "\n".join(response_lines)

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