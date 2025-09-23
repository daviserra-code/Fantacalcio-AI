#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
static_transfers.py
Static transfer data loader for Fantasy Football app.
Loads transfer data from JSONL files instead of calling Apify at runtime.
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
from functools import lru_cache

LOG = logging.getLogger("static_transfers")

# Configuration
STATIC_TRANSFERS_PATH = os.environ.get("STATIC_TRANSFERS_PATH", "data/serie_a_transfers_2025-26.jsonl")
USE_STATIC_TRANSFERS = os.environ.get("USE_STATIC_TRANSFERS", "1") == "1"

class StaticTransfersLoader:
    """Loads and serves transfer data from static JSONL files."""
    
    def __init__(self, filepath: str = STATIC_TRANSFERS_PATH):
        self.filepath = Path(filepath)
        self._transfers_by_team: Optional[Dict[str, List[Dict[str, Any]]]] = None
        self._all_transfers: Optional[List[Dict[str, Any]]] = None
        
    def _load_data(self) -> None:
        """Load transfer data from JSONL file on first access."""
        if self._transfers_by_team is not None:
            return  # Already loaded
            
        self._transfers_by_team = {}
        self._all_transfers = []
        
        if not self.filepath.exists():
            LOG.warning(f"[STATIC] Transfer file not found: {self.filepath}")
            return
            
        try:
            with self.filepath.open("r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                        
                    try:
                        transfer = json.loads(line)
                        team = self._normalize_team_name(transfer.get("team", ""))
                        
                        if team:
                            if team not in self._transfers_by_team:
                                self._transfers_by_team[team] = []
                            self._transfers_by_team[team].append(transfer)
                            self._all_transfers.append(transfer)
                            
                    except json.JSONDecodeError as e:
                        LOG.warning(f"[STATIC] Invalid JSON on line {line_num}: {e}")
                        
            LOG.info(f"[STATIC] Loaded {len(self._all_transfers)} transfers for {len(self._transfers_by_team)} teams from {self.filepath}")
            
        except Exception as e:
            LOG.error(f"[STATIC] Error loading transfer data: {e}")
            self._transfers_by_team = {}
            self._all_transfers = []
    
    def _normalize_team_name(self, team: str) -> str:
        """Normalize team name for consistent lookups."""
        if not team:
            return ""
            
        # Convert to lowercase and handle common variations
        team_lower = team.lower().strip()
        
        # Team name mappings for consistency
        team_mappings = {
            "ac milan": "milan",
            "ac mailand": "milan", 
            "inter mailand": "inter",
            "inter milan": "inter",
            "fc inter": "inter",
            "atalanta bergamo": "atalanta",
            "hellas verona": "verona",
            "bologna fc": "bologna",
            "bologna fc 1909": "bologna",
            "udinese calcio": "udinese",
            "venezia fc": "venezia",
            "as roma": "roma",
            "ss lazio": "lazio",
            "ssc napoli": "napoli",
            "juventus fc": "juventus",
            "juventus turin": "juventus",
            "fiorentina": "fiorentina",
            "acf fiorentina": "fiorentina",
            "torino fc": "torino",
            "fc torino": "torino",
            "genoa cfc": "genoa",
            "us lecce": "lecce",
            "empoli fc": "empoli",
            "cagliari calcio": "cagliari",
            "monza": "monza",
            "ac monza": "monza",
            "como": "como",
            "como 1907": "como",
            "parma": "parma",
            "parma calcio": "parma"
        }
        
        return team_mappings.get(team_lower, team_lower)
    
    def get_arrivals(self, team: str, season: str = "2025-26") -> List[Dict[str, Any]]:
        """Get arrival transfers for a specific team."""
        self._load_data()
        
        normalized_team = self._normalize_team_name(team)
        team_transfers = self._transfers_by_team.get(normalized_team, [])
        
        # Filter for arrivals only (direction="in" or no departures)
        arrivals = []
        for transfer in team_transfers:
            direction = transfer.get("direction", "in")
            if direction == "in":
                arrivals.append(transfer)
                
        LOG.debug(f"[STATIC] {team} ({normalized_team}): {len(arrivals)} arrivals found")
        return arrivals
    
    def get_all_teams(self) -> List[str]:
        """Get list of all teams with transfer data."""
        self._load_data()
        return list(self._transfers_by_team.keys())
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about loaded transfer data."""
        self._load_data()
        
        team_counts = {}
        for team, transfers in self._transfers_by_team.items():
            arrivals = [t for t in transfers if t.get("direction") == "in"]
            team_counts[team] = len(arrivals)
            
        return {
            "total_transfers": len(self._all_transfers),
            "total_teams": len(self._transfers_by_team),
            "team_arrivals": team_counts,
            "filepath": str(self.filepath),
            "file_exists": self.filepath.exists()
        }

# Global instance
_loader = StaticTransfersLoader()

@lru_cache(maxsize=128)
def get_team_arrivals(team: str, season: str = "2025-26") -> List[Dict[str, Any]]:
    """Cached function to get team arrivals."""
    if not USE_STATIC_TRANSFERS:
        return []
    return _loader.get_arrivals(team, season)

def get_transfer_stats() -> Dict[str, Any]:
    """Get transfer data statistics."""
    return _loader.get_stats()

def is_static_mode_enabled() -> bool:
    """Check if static transfer mode is enabled."""
    return USE_STATIC_TRANSFERS

# Test function
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test the loader
    print("=== Static Transfers Test ===")
    print(f"Static mode enabled: {is_static_mode_enabled()}")
    
    stats = get_transfer_stats()
    print(f"Loaded: {stats['total_transfers']} transfers for {stats['total_teams']} teams")
    
    # Test a few teams
    for team in ["Atalanta", "Milan", "Inter", "Juventus"]:
        arrivals = get_team_arrivals(team)
        print(f"{team}: {len(arrivals)} arrivals")
        if arrivals:
            print(f"  Sample: {arrivals[0].get('player', 'N/A')} -> {arrivals[0].get('team', 'N/A')}")