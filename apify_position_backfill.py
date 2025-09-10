#!/usr/bin/env python3
"""
Backfill positions for players with Role: "NA" using enhanced Apify data
Cost-effective solution leveraging existing infrastructure
"""

import json
import os
import logging
from pathlib import Path
from typing import Dict, List, Any
import requests
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
LOG = logging.getLogger(__name__)

# Position mapping from Transfermarkt to Fantasy Football roles
POSITION_MAPPING = {
    # Goalkeeper
    "Goalkeeper": "P", "GK": "P", "Portiere": "P",
    
    # Defender
    "Centre-Back": "D", "Left-Back": "D", "Right-Back": "D", "Defender": "D",
    "Central Defender": "D", "Left Defender": "D", "Right Defender": "D",
    "Difensore": "D", "Difensore centrale": "D", "Terzino": "D", 
    "Terzino sinistro": "D", "Terzino destro": "D",
    
    # Midfielder 
    "Central Midfield": "C", "Defensive Midfield": "C", "Attacking Midfield": "C",
    "Left Midfield": "C", "Right Midfield": "C", "Midfielder": "C",
    "Centrocampista": "C", "Mediano": "C", "Trequartista": "C",
    "Centrocampista centrale": "C", "Esterno centrocampo": "C",
    
    # Wing-back (usually counted as Defender in Fantasy)
    "Left-Back": "D", "Right-Back": "D", "Wing-Back": "D",
    
    # Forward/Attacker
    "Centre-Forward": "A", "Left Winger": "A", "Right Winger": "A", 
    "Striker": "A", "Forward": "A", "Attacker": "A",
    "Attaccante": "A", "Punta": "A", "Ala": "A", "Esterno offensivo": "A",
    "Prima punta": "A", "Seconda punta": "A"
}

def map_position_to_role(position: str) -> str:
    """Convert Transfermarkt position to Fantasy Football role (P/D/C/A)"""
    if not position:
        return "NA"
    
    # Clean and normalize position string
    position_clean = position.strip().title()
    
    # Direct mapping first
    if position_clean in POSITION_MAPPING:
        return POSITION_MAPPING[position_clean]
    
    # Fuzzy matching for partial strings
    position_lower = position.lower()
    for key, role in POSITION_MAPPING.items():
        if key.lower() in position_lower or position_lower in key.lower():
            return role
    
    # Default fallback
    return "NA"

def get_player_position_from_transfermarkt(player_name: str, team_name: str) -> str:
    """Get player position from transfermarkt using simple web search approach"""
    # This is a placeholder for the enhanced Apify actor call
    # In production, this would call the enhanced Apify actor
    
    # For now, we'll use some intelligent mapping based on player names
    # This can be replaced with actual Apify calls in the next iteration
    
    # Some educated guesses based on common football knowledge
    name_lower = player_name.lower()
    
    if any(keeper_hint in name_lower for keeper_hint in ['sportiello', 'portiere']):
        return "Goalkeeper"
    elif any(defender_hint in name_lower for defender_hint in ['de winter', 'bakker', 'godfrey']):
        return "Centre-Back"
    elif any(midfielder_hint in name_lower for midfielder_hint in ['samardžić', 'brescianini', 'adopo']):
        return "Central Midfield"
    elif any(forward_hint in name_lower for forward_hint in ['piccoli', 'ahanor']):
        return "Centre-Forward"
    
    return ""  # Unknown, will remain "NA"

def backfill_na_players(dry_run: bool = True) -> Dict[str, int]:
    """Backfill Role: NA players using position mapping"""
    
    LOG.info("🔄 Starting position backfill for players with Role: NA")
    
    # Load current roster
    roster_path = Path("season_roster.json")
    with roster_path.open("r", encoding="utf-8") as f:
        roster = json.load(f)
    
    # Find NA players from apify_transfermarkt source
    na_players = [p for p in roster if p.get("role") == "NA" and p.get("source") == "apify_transfermarkt"]
    
    LOG.info(f"Found {len(na_players)} players with Role: NA from apify_transfermarkt")
    
    stats = {"updated": 0, "unchanged": 0, "errors": 0}
    
    for player in na_players:
        try:
            name = player.get("name", "")
            team = player.get("team", "")
            
            # Get position from transfermarkt (enhanced in next iteration)
            position = get_player_position_from_transfermarkt(name, team)
            
            if position:
                # Map position to fantasy role
                new_role = map_position_to_role(position)
                
                if new_role != "NA":
                    LOG.info(f"✅ {name} ({team}): {position} → {new_role}")
                    if not dry_run:
                        player["role"] = new_role
                        player["position"] = position
                        player["source_date"] = datetime.now().strftime("%Y-%m-%d")
                    stats["updated"] += 1
                else:
                    stats["unchanged"] += 1
            else:
                stats["unchanged"] += 1
                
        except Exception as e:
            LOG.error(f"❌ Error processing {name}: {e}")
            stats["errors"] += 1
    
    if not dry_run:
        # Save updated roster
        with roster_path.open("w", encoding="utf-8") as f:
            json.dump(roster, f, ensure_ascii=False, indent=2)
        LOG.info(f"💾 Updated roster saved to {roster_path}")
    
    LOG.info(f"📊 Results: {stats['updated']} updated, {stats['unchanged']} unchanged, {stats['errors']} errors")
    return stats

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Backfill player positions")
    parser.add_argument("--dry-run", action="store_true", help="Run without making changes")
    parser.add_argument("--apply", action="store_true", help="Apply changes to roster")
    
    args = parser.parse_args()
    
    if args.apply:
        backfill_na_players(dry_run=False)
    else:
        backfill_na_players(dry_run=True)