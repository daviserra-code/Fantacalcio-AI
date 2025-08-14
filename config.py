# -*- coding: utf-8 -*-
import os
import logging

LOG = logging.getLogger("config")

def _load_dotenv(path: str = ".env"):
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line=line.strip()
                if not line or line.startswith("#"): 
                    continue
                if "=" not in line:
                    continue
                k,v = line.split("=",1)
                k=k.strip(); v=v.strip()
                if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                    v=v[1:-1]
                os.environ.setdefault(k, v)
        LOG.info("[config] .env caricato")
    except Exception as e:
        LOG.warning("[config] .env non caricato: %s", e)

_load_dotenv()

def env_str(key: str, default: str) -> str:
    return os.environ.get(key, default)

def env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except Exception:
        return default

def env_bool(key: str, default: bool) -> bool:
    val = os.environ.get(key)
    if val is None: return default
    return str(val).strip().lower() in {"1","true","yes","y","on"}

# ---- Chiavi unificate ----
HOST          = env_str("HOST", "0.0.0.0")
PORT          = env_int("PORT", 5000)
LOG_LEVEL     = env_str("LOG_LEVEL", "INFO")

ROSTER_JSON_PATH   = env_str("ROSTER_JSON_PATH", "./season_roster.json")
CHROMA_PATH        = env_str("CHROMA_PATH", "./chroma_db")
SEASON_FILTER      = env_str("SEASON_FILTER", "")  # se vuoto auto-detect
REF_YEAR           = env_int("REF_YEAR", 2025)

AGE_INDEX_PATH     = env_str("AGE_INDEX_PATH", "./data/age_index.cleaned.json")
AGE_OVERRIDES_PATH = env_str("AGE_OVERRIDES_PATH", "./data/age_overrides.json")

ENABLE_WEB_FALLBACK = env_bool("ENABLE_WEB_FALLBACK", False)

OPENAI_API_KEY     = env_str("OPENAI_API_KEY", "")
OPENAI_MODEL       = env_str("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_TEMPERATURE = float(env_str("OPENAI_TEMPERATURE", "0.20"))
OPENAI_MAX_TOKENS  = env_int("OPENAI_MAX_TOKENS", 600)
