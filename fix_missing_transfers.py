#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Targeted fix for missing Yunus Musah and Nicola Zalewski transfers
Handles complex transfer chains correctly
"""

import json
import logging
import shutil
from datetime import datetime

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

def fix_missing_transfers():
    """Fix specific missing transfer cases"""
    
    # Load current roster
    with open("season_roster.json", "r", encoding="utf-8") as f:
        roster = json.load(f)
    
    LOG.info(f"Current roster size: {len(roster)}")
    
    # Create name index for lookup
    name_index = {}
    for player in roster:
        name = player.get('name', '').strip()
        if name:
            name_lower = name.lower()
            name_index[name_lower] = player
    
    # Missing players to add/fix
    missing_fixes = [
        {
            "name": "Yunus Musah",
            "team": "Atalanta", 
            "role": "C",
            "price": 6,
            "fantamedia": 9.0,
            "action": "move_from_milan"
        },
        {
            "name": "Nicola Zalewski",
            "team": "Atalanta",
            "role": "D", 
            "price": 8,
            "fantamedia": 15.0,
            "action": "add_new"
        }
    ]
    
    changes_made = []
    
    for fix in missing_fixes:
        name = fix["name"]
        name_lower = name.lower()
        
        # Check if player already exists
        existing_player = name_index.get(name_lower)
        
        if existing_player:
            # Update existing player
            old_team = existing_player.get('team', '')
            existing_player['team'] = fix["team"]
            changes_made.append(f"MOVED: {name} from {old_team} to {fix['team']}")
            LOG.info(f"Moved {name} from {old_team} to {fix['team']}")
        else:
            # Add new player
            new_player = {
                "name": name,
                "role": fix["role"],
                "team": fix["team"],
                "birth_year": None,
                "price": fix["price"],
                "fantamedia": fix["fantamedia"],
                "appearances": 0,
                "source": "manual_transfer_fix_2025-09-26",
                "source_date": "2025-09-26",
                "name_prev": None
            }
            roster.append(new_player)
            name_index[name_lower] = new_player
            changes_made.append(f"ADDED: {name} to {fix['team']} as {fix['role']}")
            LOG.info(f"Added {name} to {fix['team']} as {fix['role']}")
    
    # Remove any potential duplicates by name (keep the one with Atalanta team)
    seen_names = set()
    deduped_roster = []
    for player in roster:
        name = player.get('name', '').strip()
        if name:
            name_lower = name.lower()
            if name_lower not in seen_names:
                seen_names.add(name_lower)
                deduped_roster.append(player)
            else:
                # If duplicate, prefer the one with Atalanta (for our specific fixes)
                existing_idx = None
                for i, existing in enumerate(deduped_roster):
                    if existing.get('name', '').lower() == name_lower:
                        existing_idx = i
                        break
                
                if existing_idx is not None:
                    current_team = deduped_roster[existing_idx].get('team', '')
                    new_team = player.get('team', '')
                    
                    # Prefer Atalanta for our specific cases
                    if new_team == 'Atalanta' and current_team != 'Atalanta':
                        deduped_roster[existing_idx] = player
                        changes_made.append(f"DEDUPE: Replaced {name} ({current_team}) with ({new_team})")
                        LOG.info(f"Deduplication: Replaced {name} ({current_team}) with ({new_team})")
    
    LOG.info(f"Final roster size: {len(deduped_roster)} (was {len(roster)})")
    
    # Create backup and write
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"season_roster.json_backup_manual_fix_{timestamp}"
    shutil.copy2("season_roster.json", backup_path)
    LOG.info(f"Backup created: {backup_path}")
    
    # Write updated roster
    with open("season_roster.json", "w", encoding="utf-8") as f:
        json.dump(deduped_roster, f, indent=2, ensure_ascii=False)
    
    LOG.info("Roster updated successfully")
    
    # Verify fixes
    verification_results = []
    for fix in missing_fixes:
        found = any(p.get('name', '').lower() == fix['name'].lower() and 
                   p.get('team', '') == fix['team'] for p in deduped_roster)
        verification_results.append(f"{fix['name']} → {fix['team']}: {'✅' if found else '❌'}")
    
    return {
        "changes_made": changes_made,
        "verification": verification_results,
        "final_size": len(deduped_roster),
        "backup_path": backup_path
    }

if __name__ == "__main__":
    results = fix_missing_transfers()
    print("\n=== MANUAL TRANSFER FIX RESULTS ===")
    print(f"Final roster size: {results['final_size']}")
    print(f"Backup: {results['backup_path']}")
    print("\nChanges made:")
    for change in results['changes_made']:
        print(f"  {change}")
    print("\nVerification:")
    for verification in results['verification']:
        print(f"  {verification}")