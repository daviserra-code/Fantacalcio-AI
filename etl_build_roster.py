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
            if x is None or x == "":
                return default
            return int(x)
        except Exception:
            return default

    # Extract name from various possible fields
    name = (m.get("name") or m.get("player") or m.get("player_name") or "").strip()
    
    # Extract role and normalize it - check multiple possible fields
    role = (m.get("role") or m.get("position") or m.get("pos") or 
            m.get("player_position") or m.get("ruolo") or "").strip().upper()
    
    # Extract team name
    team = (m.get("team") or m.get("club") or m.get("team_name") or "").strip()
    
    # Handle birth year from different sources
    birth_year = (m.get("birth_year") or m.get("birthyear") or 
                  m.get("year_of_birth") or m.get("birth_date"))
    if birth_year and isinstance(birth_year, str):
        # Try to extract year from date string
        import re
        year_match = re.search(r'\b(19|20)\d{2}\b', str(birth_year))
        if year_match:
            birth_year = _int(year_match.group(), default=None)
        else:
            birth_year = _int(birth_year, default=None)
    else:
        birth_year = _int(birth_year, default=None)

    # For transfer data, try to get additional info from nested structures
    player_info = m.get("player_info", {}) if isinstance(m.get("player_info"), dict) else {}
    
    # Enhanced role detection
    if not role:
        role = (player_info.get("position") or player_info.get("role") or "").strip().upper()
    
    # Try to get market value as price if no price available
    price = _num(m.get("price") or m.get("cost") or m.get("market_value") or 
                player_info.get("market_value"), default=None)
    
    return {
        "name": name,
        "role": role,
        "team": team,
        "birth_year": birth_year,
        "price": price,
        "fantamedia": _num(m.get("fantamedia") or m.get("avg") or m.get("fm") or 
                          player_info.get("fantamedia"), default=None),
        "appearances": _int(m.get("appearances") or m.get("apps") or m.get("presenze") or
                           player_info.get("appearances"), default=0),
        "season": m.get("season"),
        "source": m.get("source"),
        "source_date": m.get("source_date"),
        "age": _int(m.get("age") or player_info.get("age"), default=None),
    }

def fetch_players_from_kb(km: KnowledgeManager, seasons: List[str], limit: int = 5000) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    
    # Try different query approaches to fetch player data
    try:
        # First approach: try to get all documents and filter manually
        LOG.info("[ETL] Fetching all documents from KB for filtering...")
        res = km.get_by_filter(where=None, limit=limit, include=["metadatas"])
        metas = res.get("metadatas") or []
        LOG.info("[ETL] Retrieved %d documents from KB", len(metas))
        
        for m in metas:
            if not isinstance(m, dict):
                continue
                
            # Check if it's player data
            doc_type = m.get("type", "")
            doc_season = m.get("season", "")
            
            # Accept various player-related types and season formats
            if (doc_type in ["player_info", "current_player", "transfer"] or 
                m.get("name") or m.get("player")):
                
                # Filter by season if specified
                if not seasons or doc_season in seasons or any(s in str(doc_season) for s in seasons):
                    player_data = normalize_player(m)
                    if player_data.get("name"):  # Only add if we have a name
                        out.append(player_data)
                        
    except Exception as e:
        LOG.error("[ETL] Error fetching from KB: %s", e)
        LOG.info("[ETL] Trying alternative search approach...")
        
        # Fallback: try search-based approach
        try:
            for season in seasons:
                search_res = km.search_knowledge(
                    text=f"player season {season}",
                    n_results=limit,
                    include=["metadatas"]
                )
                
                if "metadatas" in search_res and search_res["metadatas"]:
                    for meta_list in search_res["metadatas"]:
                        for m in meta_list if isinstance(meta_list, list) else [meta_list]:
                            if isinstance(m, dict):
                                player_data = normalize_player(m)
                                if player_data.get("name"):
                                    out.append(player_data)
        except Exception as e2:
            LOG.error("[ETL] Fallback search also failed: %s", e2)
    
    # Remove duplicates based on name-team combination
    seen = set()
    unique_out = []
    for player in out:
        key = (player.get("name", "").lower(), player.get("team", "").lower())
        if key not in seen and key[0]:  # Only add if name exists
            seen.add(key)
            unique_out.append(player)
    
    LOG.info("[ETL] Processed %d unique players from KB", len(unique_out))
    return unique_out

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

    # Don't overwrite if we have 0 players (likely indicates data issue)
    if len(clean) == 0:
        LOG.warning("[ETL] Non sovrascrivo %s - 0 giocatori trovati (possibile problema dati)", OUT_PATH)
        # Check if file exists and has content
        try:
            with open(OUT_PATH, "r", encoding="utf-8") as f:
                existing = json.load(f)
            if isinstance(existing, list) and len(existing) > 0:
                LOG.info("[ETL] Mantengo roster esistente con %d giocatori", len(existing))
                return
        except Exception:
            pass
    
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False, indent=2)
    LOG.info("[ETL] Salvato %s con %d giocatori", OUT_PATH, len(clean))

if __name__ == "__main__":
    main()
