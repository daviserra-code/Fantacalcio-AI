# entity_guard.py
# -*- coding: utf-8 -*-
import json
import logging
from typing import List, Dict, Any, Optional
from difflib import get_close_matches
from datetime import datetime

logger = logging.getLogger("entity_guard")
logger.setLevel(logging.INFO)

class RosterStore:
    def __init__(self, path: str = "season_roster.json"):
        self.path = path

    def load(self) -> Dict[str, Any]:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {
                "season": None,
                "league": "Serie A",
                "updated_at": None,
                "players": []
            }

    def save(self, roster: Dict[str, Any]) -> None:
        roster = dict(roster)
        if "updated_at" not in roster or not roster["updated_at"]:
            roster["updated_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(roster, f, ensure_ascii=False, indent=2)

def load_roster_safe(store: RosterStore) -> Dict[str, Any]:
    roster = store.load()
    # normalizza campi player
    cleaned: List[Dict[str, Any]] = []
    for p in roster.get("players", []):
        if not p.get("player") or not p.get("team") or not p.get("role"):
            continue
        # normalizza tipi
        if isinstance(p.get("age"), str):
            try:
                p["age"] = int(p["age"])
            except Exception:
                p["age"] = None
        # fm/price
        for k in ("fantamedia", "price", "starter_probability"):
            if isinstance(p.get(k), str):
                try:
                    p[k] = float(p[k])
                except Exception:
                    pass
        cleaned.append(p)
    roster["players"] = cleaned
    return roster

def canonicalize_player_names(players: List[Dict[str, Any]], requested: List[str], cutoff: float = 0.82) -> List[Dict[str, Any]]:
    """
    Ritorna i record corrispondenti alle richieste, con fuzzy matching ma
    solo su nomi presenti nel roster.
    """
    names = {p["player"]: p for p in players}
    name_list = list(names.keys())
    output: List[Dict[str, Any]] = []
    for req in requested:
        matches = get_close_matches(req, name_list, n=1, cutoff=cutoff)
        if matches:
            output.append(names[matches[0]])
    return output

def filter_players_by(players: List[Dict[str, Any]],
                      min_age: Optional[int] = None,
                      max_age: Optional[int] = None,
                      role: Optional[str] = None) -> List[Dict[str, Any]]:
    out = []
    for p in players:
        if role and p.get("role") != role:
            continue
        age = p.get("age")
        if min_age is not None and (age is None or age < min_age):
            continue
        if max_age is not None and (age is None or age > max_age):
            continue
        out.append(p)
    return out
