#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fix data quality issues for manually added players
Ensure all players have proper data types and values for API compatibility
"""

import json
import logging
import shutil
from datetime import datetime

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

def fix_data_quality():
    """Fix data quality issues in roster"""
    
    # Load current roster
    with open("season_roster.json", "r", encoding="utf-8") as f:
        roster = json.load(f)
    
    LOG.info(f"Fixing data quality for {len(roster)} players")
    
    fixes_applied = 0
    
    for player in roster:
        name = player.get('name', '').strip()
        original_data = player.copy()
        
        # Fix common data quality issues
        fixed = False
        
        # Ensure price is a number (not None)
        if player.get('price') is None:
            # Set default price based on role
            role = player.get('role', 'C')
            default_prices = {'P': 5, 'D': 8, 'C': 10, 'A': 12}
            player['price'] = default_prices.get(role, 8)
            fixed = True
        
        # Ensure fantamedia is a number (not None) 
        if player.get('fantamedia') is None:
            # Set modest default fantamedia
            player['fantamedia'] = 15.0
            fixed = True
        
        # Ensure appearances is a number
        if player.get('appearances') is None:
            player['appearances'] = 0
            fixed = True
        
        # Ensure birth_year is properly handled
        if player.get('birth_year') == 'None' or player.get('birth_year') == '':
            player['birth_year'] = None
        
        # Ensure all string fields are properly set
        for field in ['name', 'role', 'team', 'source', 'source_date']:
            if player.get(field) is None:
                if field == 'role':
                    player[field] = 'C'  # Default role
                elif field == 'source':
                    player[field] = 'data_quality_fix'
                elif field == 'source_date':
                    player[field] = '2025-09-26'
                else:
                    player[field] = player.get(field, '')
                fixed = True
        
        # Ensure role is uppercase and valid
        role = player.get('role', '').strip().upper()
        if role not in ['P', 'D', 'C', 'A']:
            player['role'] = 'C'  # Default to midfielder
            fixed = True
        else:
            player['role'] = role
        
        # Ensure numeric fields are proper types
        try:
            if isinstance(player.get('price'), str):
                player['price'] = float(player['price'])
                fixed = True
        except (ValueError, TypeError):
            player['price'] = 8.0
            fixed = True
        
        try:
            if isinstance(player.get('fantamedia'), str):
                player['fantamedia'] = float(player['fantamedia'])
                fixed = True
        except (ValueError, TypeError):
            player['fantamedia'] = 15.0
            fixed = True
        
        if fixed:
            fixes_applied += 1
            LOG.info(f"Fixed data quality for: {name}")
    
    LOG.info(f"Applied fixes to {fixes_applied} players")
    
    # Create backup and write
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"season_roster.json_backup_data_quality_{timestamp}"
    shutil.copy2("season_roster.json", backup_path)
    LOG.info(f"Backup created: {backup_path}")
    
    # Write updated roster
    with open("season_roster.json", "w", encoding="utf-8") as f:
        json.dump(roster, f, indent=2, ensure_ascii=False)
    
    LOG.info("Data quality fixes applied successfully")
    
    # Verify specific players
    verification = []
    for player in roster:
        name = player.get('name', '').lower()
        if 'yunus musah' in name or 'zalewski' in name:
            verification.append({
                "name": player.get('name'),
                "team": player.get('team'),
                "role": player.get('role'),
                "price": player.get('price'),
                "fantamedia": player.get('fantamedia'),
                "complete": all(player.get(field) is not None for field in ['price', 'fantamedia', 'role', 'team'])
            })
    
    return {
        "fixes_applied": fixes_applied,
        "total_players": len(roster),
        "backup_path": backup_path,
        "verification": verification
    }

if __name__ == "__main__":
    results = fix_data_quality()
    print("\n=== DATA QUALITY FIX RESULTS ===")
    print(f"Total players: {results['total_players']}")
    print(f"Fixes applied: {results['fixes_applied']}")
    print(f"Backup: {results['backup_path']}")
    print("\nSpecific player verification:")
    for player in results['verification']:
        status = "✅" if player['complete'] else "❌"
        print(f"  {status} {player['name']} ({player['team']}) - Role: {player['role']}, Price: {player['price']}, FM: {player['fantamedia']}")