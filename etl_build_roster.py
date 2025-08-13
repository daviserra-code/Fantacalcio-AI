# etl_build_roster.py
# -*- coding: utf-8 -*-
import os
import json
import logging
from typing import Any, Dict, List
from knowledge_manager import KnowledgeManager

LOG = logging.getLogger("etl_build_roster")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

OUT_PATH = os.getenv("ROSTER_JSON_PATH", "./season_roster.json")

def normalize_player(m: Dict[str, Any]) -> Dict[str, Any]:
    def _num(x, default=None):
        try:
            if x is None or x == "":
                return default
            return float(x)
        except Exception:
            return default
    def _int(x, default=0):
        try:
            return int(x)
        except Exception:
            return default

    return {
        "name": (m.get("name") or m.get("player") or "").strip(),
        "role": (m.get("role") or m.get("position") or "").strip().upper(),
        "team": (m.get("team") or m.get("club") or "").strip(),
        "birth_year": m.get("birth_year") or m.get("birthyear"),
        "price": _num(m.get("price") or m.get("cost"), default=None),
        "fantamedia": _num(m.get("fantamedia") or m.get("avg"), default=None),
        "appearances": _int(m.get("appearances") or m.get("apps") or 0, 0),
    }

def fetch_players_from_kb(km: KnowledgeManager, seasons: List[str], limit: int = 5000) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for season in seasons:
        where = {"$and": [
            {"type": {"$in": ["player_info", "current_player"]}},
            {"season": {"$eq": season}}
        ]}
        res = km.get_by_filter(where=where, limit=limit, include=["metadatas"])
        metas = res.get("metadatas") or []
        for m in metas:
            if isinstance(m, dict):
                out.append(normalize_player(m))
    return out

def main():
    LOG.info("[ETL] Costruzione roster…")
    km = KnowledgeManager()
    seasons = ["2025-26", "2024-25"]
    players = fetch_players_from_kb(km, seasons=seasons, limit=50000)

    # dedup per name-team-role
    seen = set()
    clean = []
    for p in players:
        key = (p["name"], p["team"], p["role"])
        if key in seen:
            continue
        seen.add(key)
        clean.append(p)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False, indent=2)
    LOG.info("[ETL] Salvato %s con %d giocatori", OUT_PATH, len(clean))

if __name__ == "__main__":
    main()
