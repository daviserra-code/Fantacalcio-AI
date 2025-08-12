# etl_build_roster.py
# -*- coding: utf-8 -*-

import os
import json
import logging
from typing import Any, Dict, List, Optional

from knowledge_manager import KnowledgeManager

LOG = logging.getLogger("etl_build_roster")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

DEFAULT_SEASON = os.getenv("SEASON", "2025-26")
DEFAULT_LIMIT = int(os.getenv("ETL_LIMIT", "5000"))
OUTPUT_PATH = os.getenv("ROSTER_JSON_PATH", "./season_roster.json")


def _where_players(season: str) -> Dict[str, Any]:
    """
    Costruisce un filtro compatibile con Chroma (un unico operatore top-level).
    Prendiamo player_info e current_player per la stagione data.
    """
    return {
        "$and": [
            {"type": {"$in": ["player_info", "current_player"]}},
            {"season": season}
        ]
    }


def _normalize_player(meta: Dict[str, Any]) -> Dict[str, Any]:
    name = (meta.get("name") or meta.get("player") or "").strip()
    role = (meta.get("role") or meta.get("position") or "").strip().upper()
    team = (meta.get("team") or meta.get("club") or "").strip()
    birth_year = meta.get("birth_year") or meta.get("birthyear")
    price = meta.get("price") or meta.get("cost")
    fm = meta.get("fantamedia") or meta.get("avg")

    # coerce numerici dove possibile
    def _num(x):
        try:
            if x is None or x == "":
                return None
            return float(x)
        except Exception:
            return None

    out = {
        "name": name,
        "role": role,
        "team": team,
        "birth_year": birth_year,
        "price": _num(price),
        "fantamedia": _num(fm) if _num(fm) is not None else fm
    }
    return out


def fetch_players_from_kb(km: KnowledgeManager, season: str, limit: int) -> List[Dict[str, Any]]:
    include = ["metadatas"]  # niente "ids" in get()
    where = _where_players(season)

    # usa API stabile del KM (senza text)
    res = km.search_knowledge(where=where, n_results=limit, include=include)
    metas = res.get("metadatas") or []
    if not isinstance(metas, list):
        LOG.warning("[ETL] Formato metadatas inatteso, lo ignoro")
        return []

    players: List[Dict[str, Any]] = []
    for m in metas:
        if not isinstance(m, dict):
            continue
        p = _normalize_player(m)
        if p["name"]:
            players.append(p)
    return players


def main():
    LOG.info("[ETL] Costruzione roster…")
    season = os.getenv("SEASON", DEFAULT_SEASON)
    limit = DEFAULT_LIMIT

    km = KnowledgeManager()

    # prova stagione target, poi fallback stagione precedente
    seasons_try = [season, "2024-25"] if season != "2024-25" else [season]

    all_players: List[Dict[str, Any]] = []
    for s in seasons_try:
        try:
            chunk = fetch_players_from_kb(km, season=s, limit=limit)
            LOG.info("[ETL] Dal KM (%s): %d record candidati", s, len(chunk))
            all_players.extend(chunk)
        except Exception as e:
            LOG.warning("[ETL] KM search error (%s): %s", s, e)

    # dedup per nome+team (soft)
    seen = set()
    deduped: List[Dict[str, Any]] = []
    for p in all_players:
        key = (p.get("name") or "", p.get("team") or "")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(p)

    # salva JSON come LISTA (non dict), così l'app non logga "roster non è una lista"
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(deduped, f, ensure_ascii=False, indent=2)

    LOG.info("[ETL] Salvato %s con %d giocatori", OUTPUT_PATH, len(deduped))


if __name__ == "__main__":
    main()
