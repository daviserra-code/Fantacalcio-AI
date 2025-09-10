#!/usr/bin/env python3
"""
Simple position updater - add players as you research them
Run this script each time you research more players
"""

import json
from datetime import datetime

# Add new players here as you research their positions on transfermarkt.it
# Format: "Player Name": "Role" (P=Goalkeeper, D=Defender, C=Midfielder, A=Forward)
NEW_PLAYER_POSITIONS = {
    # Como (7 players total - research these first)
    "Ferdi Er": "D",              # Defender
    "Daniele Attorre": "C",       # Midfielder
    "Viktor Ribeiro": "C",        # Midfielder
    
    # Lecce (8 players - research these next)
    "Márk Kosznovszky": "P",      # Goalkeeper
    "Josh Knight": "D",           # Defender  
    "John Swift": "C",            # Midfielder
    
    # Add more players here as you research them...
    # Examples:
    # "Player Name": "P",   # Goalkeeper
    # "Player Name": "D",   # Defender
    # "Player Name": "C",   # Midfielder
    # "Player Name": "A",   # Forward
}

def update_positions():
    """Update player positions in season_roster.json"""
    
    print("🔄 Loading season roster...")
    with open("season_roster.json", "r", encoding="utf-8") as f:
        roster = json.load(f)
    
    # Count initial NA players
    initial_na = len([p for p in roster if p.get("role") == "NA" and p.get("source") == "apify_transfermarkt"])
    print(f"Initial NA players: {initial_na}")
    
    # Update players
    updated = 0
    for player in roster:
        if (player.get("role") == "NA" and 
            player.get("source") == "apify_transfermarkt" and
            player.get("name") in NEW_PLAYER_POSITIONS):
            
            old_role = player["role"]
            new_role = NEW_PLAYER_POSITIONS[player["name"]]
            player["role"] = new_role
            player["source_date"] = datetime.now().strftime("%Y-%m-%d")
            
            print(f"✅ {player['name']} ({player.get('team', 'Unknown')}) : {old_role} → {new_role}")
            updated += 1
    
    # Save updates
    if updated > 0:
        with open("season_roster.json", "w", encoding="utf-8") as f:
            json.dump(roster, f, ensure_ascii=False, indent=2)
        print(f"💾 Saved {updated} updates")
    
    # Count final NA players
    final_na = len([p for p in roster if p.get("role") == "NA" and p.get("source") == "apify_transfermarkt"])
    print(f"Remaining NA players: {final_na}")
    print(f"Progress: {initial_na - final_na} players fixed!")
    
    # Show next teams to research
    print("\n🔍 Next teams to research (smallest first):")
    by_team = {}
    for p in roster:
        if p.get("role") == "NA" and p.get("source") == "apify_transfermarkt":
            team = p.get("team", "Unknown")
            if team not in by_team:
                by_team[team] = []
            by_team[team].append(p.get("name", "Unknown"))
    
    # Show teams sorted by player count
    for team, players in sorted(by_team.items(), key=lambda x: len(x[1])):
        print(f"  {team}: {len(players)} players")
        if len(players) <= 3:  # Show all players for small teams
            for player in players:
                print(f"    - {player}")

if __name__ == "__main__":
    update_positions()