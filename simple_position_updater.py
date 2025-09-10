#!/usr/bin/env python3
"""
Simple, working solution to update player positions
Manual research approach that actually works
"""

import json
import logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)

# Position mapping - tested and working
POSITION_MAPPING = {
    "Portiere": "P", "GK": "P", "Goalkeeper": "P",
    "Difensore": "D", "Difensore centrale": "D", "Terzino": "D", 
    "Centre-Back": "D", "Left-Back": "D", "Right-Back": "D",
    "Centrocampista": "C", "Mediano": "C", "Trequartista": "C",
    "Central Midfield": "C", "Defensive Midfield": "C", "Attacking Midfield": "C",
    "Attaccante": "A", "Punta": "A", "Ala": "A",
    "Centre-Forward": "A", "Left Winger": "A", "Right Winger": "A", "Striker": "A"
}

# Research-based position updates (add more as you research)
KNOWN_POSITIONS = {
    # High-profile players already researched
    "Ciro Immobile": "A",
    "Edin Džeko": "A", 
    "Albert Gudmundsson": "A",
    "Robin Gosens": "D",
    "Mats Hummels": "D",
    
    # Common Serie A players (add more as you research them)
    "Marco Sportiello": "P",  # Goalkeeper
    "Koni De Winter": "D",    # Defender
    "Lazar Samardžić": "C",   # Midfielder
    "Roberto Piccoli": "A",   # Forward
    
    # Add more players here as you research them manually
    # Format: "Player Name": "Role" (P/D/C/A)
}

def update_known_positions(dry_run=True):
    """Update positions for players we've researched"""
    
    LOG.info("🔄 Updating positions for known players...")
    
    # Load roster
    with open("season_roster.json", "r", encoding="utf-8") as f:
        roster = json.load(f)
    
    # Find NA players
    na_players = [p for p in roster if p.get("role") == "NA" and p.get("source") == "apify_transfermarkt"]
    LOG.info(f"Found {len(na_players)} players with Role: NA")
    
    updated = 0
    for player in roster:
        if player.get("role") == "NA" and player.get("name") in KNOWN_POSITIONS:
            new_role = KNOWN_POSITIONS[player["name"]]
            LOG.info(f"✅ Updating {player['name']} ({player.get('team', 'Unknown')}) → {new_role}")
            
            if not dry_run:
                player["role"] = new_role
                player["source_date"] = datetime.now().strftime("%Y-%m-%d")
            updated += 1
    
    if not dry_run and updated > 0:
        with open("season_roster.json", "w", encoding="utf-8") as f:
            json.dump(roster, f, ensure_ascii=False, indent=2)
        LOG.info(f"💾 Updated {updated} players in season_roster.json")
    
    LOG.info(f"📊 Summary: {updated} players updated")
    
    # Show remaining NA players by team for manual research
    remaining_na = [p for p in roster if p.get("role") == "NA" and p.get("source") == "apify_transfermarkt"]
    if remaining_na:
        LOG.info(f"🔍 {len(remaining_na)} players still need research:")
        
        by_team = {}
        for p in remaining_na:
            team = p.get("team", "Unknown")
            if team not in by_team:
                by_team[team] = []
            by_team[team].append(p.get("name", "Unknown"))
        
        for team, players in sorted(by_team.items()):
            LOG.info(f"  {team}: {len(players)} players")
            for player in players[:3]:  # Show first 3
                LOG.info(f"    - {player}")
            if len(players) > 3:
                LOG.info(f"    ... and {len(players)-3} more")
    
    return {"updated": updated, "remaining": len(remaining_na)}

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Update known player positions")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default is dry run)")
    
    args = parser.parse_args()
    
    result = update_known_positions(dry_run=not args.apply)
    
    if not args.apply:
        print("\n🧪 DRY RUN - No changes made. Use --apply to update the roster.")
    
    print(f"\n📊 Result: {result['updated']} updated, {result['remaining']} remaining")