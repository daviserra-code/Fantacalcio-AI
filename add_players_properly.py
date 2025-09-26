#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Properly add missing players with all required fields for filtering
"""

import json
import logging
import shutil
from datetime import datetime

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

def add_players_properly():
    """Add missing players with proper data that passes all filters"""
    
    with open("season_roster.json", "r", encoding="utf-8") as f:
        roster = json.load(f)
    
    LOG.info(f"Adding missing players to roster of {len(roster)} players")
    
    # Players to add with complete, filter-compliant data
    players_to_add = [
        {
            "name": "Yunus Musah",
            "role": "C",
            "team": "Atalanta",
            "birth_year": 2002,
            "price": 6,
            "fantamedia": 9.0,
            "appearances": 0,
            "season": "2025-26",  # Required for filtering
            "source": "sky_listone+transfer_update_2025-09-26",
            "source_date": "2025-09-26",
            "name_prev": None
        },
        {
            "name": "Nicola Zalewski",
            "role": "D", 
            "team": "Atalanta",
            "birth_year": 2002,
            "price": 8,
            "fantamedia": 15.0,
            "appearances": 0,
            "season": "2025-26",  # Required for filtering
            "source": "sky_listone+transfer_update_2025-09-26",
            "source_date": "2025-09-26",
            "name_prev": None
        }
    ]
    
    # Check if players already exist
    existing_names = [p.get('name', '').lower() for p in roster]
    added_count = 0
    
    for player in players_to_add:
        name = player['name']
        name_lower = name.lower()
        
        if name_lower not in existing_names:
            roster.append(player)
            existing_names.append(name_lower)
            added_count += 1
            LOG.info(f"Added {name} to {player['team']} with complete data")
        else:
            LOG.info(f"Player {name} already exists, skipping")
    
    LOG.info(f"Added {added_count} players to roster")
    
    # Create backup and write
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"season_roster.json_backup_proper_add_{timestamp}"
    shutil.copy2("season_roster.json", backup_path)
    LOG.info(f"Backup created: {backup_path}")
    
    # Write updated roster
    with open("season_roster.json", "w", encoding="utf-8") as f:
        json.dump(roster, f, indent=2, ensure_ascii=False)
    
    LOG.info("Players added successfully with proper filtering data")
    
    # Verify the additions
    verification = []
    for player in roster:
        name = player.get('name', '').lower()
        if 'musah' in name or 'zalewski' in name:
            verification.append({
                "name": player.get('name'),
                "team": player.get('team'),
                "role": player.get('role'),
                "season": player.get('season'),
                "birth_year": player.get('birth_year'),
                "source": player.get('source'),
                "complete": all(player.get(field) is not None for field in ['season', 'birth_year', 'price', 'fantamedia'])
            })
    
    return {
        "added_count": added_count,
        "final_size": len(roster),
        "backup_path": backup_path,
        "verification": verification
    }

if __name__ == "__main__":
    results = add_players_properly()
    print("\n=== PROPER PLAYER ADDITION RESULTS ===")
    print(f"Final roster size: {results['final_size']}")
    print(f"Players added: {results['added_count']}")
    print(f"Backup: {results['backup_path']}")
    print("\nVerification:")
    for player in results['verification']:
        status = "✅" if player['complete'] else "❌"
        print(f"  {status} {player['name']} ({player['team']}) - Season: {player['season']}, Birth: {player['birth_year']}")