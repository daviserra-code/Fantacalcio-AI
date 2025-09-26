#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fix canonical player transfers by updating existing entries instead of adding duplicates
"""

import json
import logging
import shutil
from datetime import datetime

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

def fix_canonical_transfers():
    """Fix transfers by updating canonical entries and removing duplicates"""
    
    with open("season_roster.json", "r", encoding="utf-8") as f:
        roster = json.load(f)
    
    LOG.info(f"Processing {len(roster)} players for canonical transfer fixes")
    
    changes = []
    players_to_remove = []
    
    for i, player in enumerate(roster):
        name = player.get('name', '').strip()
        name_lower = name.lower()
        
        # Handle Yunus Musah
        if 'musah' in name_lower:
            if name == "Yunus Musah":
                # This is our manual entry - mark for removal
                players_to_remove.append(i)
                changes.append(f"REMOVE: Manual entry '{name}' (will update canonical instead)")
            elif 'musah' in name_lower and player.get('team') != 'Atalanta':
                # This is the canonical entry - update to Atalanta
                old_team = player.get('team', '')
                player['team'] = 'Atalanta'
                # Ensure required fields are set
                if not player.get('season'):
                    player['season'] = '2025-26'
                if not player.get('birth_year'):
                    player['birth_year'] = 2002
                changes.append(f"MOVED: Canonical '{name}' from {old_team} to Atalanta")
                LOG.info(f"Moved canonical {name} from {old_team} to Atalanta")
        
        # Handle Nicola Zalewski 
        if 'zalewski' in name_lower:
            if name == "Nicola Zalewski":
                # This is our manual entry - mark for removal
                players_to_remove.append(i)
                changes.append(f"REMOVE: Manual entry '{name}' (will update canonical instead)")
            elif 'zalewski' in name_lower and player.get('team') != 'Atalanta':
                # This is the canonical entry - update to Atalanta
                old_team = player.get('team', '')
                player['team'] = 'Atalanta'
                # Ensure required fields are set
                if not player.get('season'):
                    player['season'] = '2025-26'
                if not player.get('birth_year'):
                    player['birth_year'] = 2002
                changes.append(f"MOVED: Canonical '{name}' from {old_team} to Atalanta")
                LOG.info(f"Moved canonical {name} from {old_team} to Atalanta")
    
    # Remove manual entries (in reverse order to preserve indices)
    for idx in sorted(players_to_remove, reverse=True):
        removed_player = roster.pop(idx)
        LOG.info(f"Removed manual entry: {removed_player.get('name')}")
    
    LOG.info(f"Applied {len(changes)} changes, removed {len(players_to_remove)} manual entries")
    
    # Create backup and write
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"season_roster.json_backup_canonical_fix_{timestamp}"
    shutil.copy2("season_roster.json", backup_path)
    LOG.info(f"Backup created: {backup_path}")
    
    # Write updated roster
    with open("season_roster.json", "w", encoding="utf-8") as f:
        json.dump(roster, f, indent=2, ensure_ascii=False)
    
    LOG.info("Canonical transfer fixes applied successfully")
    
    # Verify the fixes
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
                "source": player.get('source', 'no_source')
            })
    
    return {
        "changes": changes,
        "final_size": len(roster),
        "backup_path": backup_path,
        "verification": verification
    }

if __name__ == "__main__":
    results = fix_canonical_transfers()
    print("\n=== CANONICAL TRANSFER FIX RESULTS ===")
    print(f"Final roster size: {results['final_size']}")
    print(f"Backup: {results['backup_path']}")
    print("\nChanges made:")
    for change in results['changes']:
        print(f"  {change}")
    print("\nVerification (remaining Musah/Zalewski entries):")
    for player in results['verification']:
        print(f"  {player['name']} ({player['team']}) - Season: {player['season']}, Birth: {player['birth_year']}, Source: {player['source']}")