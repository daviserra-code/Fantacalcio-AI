#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Idempotent Transfer Applier for September 2025 Transfers
Processes combined JSONL transfer data and updates season_roster.json
"""

import json
import logging
import os
import shutil
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

# Set up logging
LOG = logging.getLogger(__name__)
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Correct Serie A teams for 2025-26 season (matches etl_transfer_reconciliation.py)
SERIE_A_TEAMS_2025_26 = {
    'Atalanta', 'Bologna', 'Cagliari', 'Como', 'Fiorentina', 
    'Genoa', 'Inter', 'Juventus', 'Lazio', 'Lecce', 'Milan', 
    'Napoli', 'Parma', 'Roma', 'Torino', 'Udinese', 'Verona',
    # NEW 2025-26: Promoted from Serie B
    'Sassuolo', 'Pisa', 'Cremonese'
    # REMOVED 2025-26: Relegated to Serie B (Empoli, Venezia, Monza)
}

def normalize_name(name: str) -> str:
    """Normalize player name for matching (reused from etl_transfer_reconciliation.py)"""
    return name.lower().strip().replace("'", "").replace("-", " ")

def normalize_team(team: str) -> str:
    """Normalize team name for matching (reused from etl_transfer_reconciliation.py)"""
    team_mappings = {
        'hellas verona': 'verona',
        'ac milan': 'milan',
        'fc inter': 'inter',
        'internazionale': 'inter',
        'juventus fc': 'juventus',
        'as roma': 'roma',
        'ss lazio': 'lazio',
        'ssc napoli': 'napoli',
        'ac fiorentina': 'fiorentina',
        'atalanta bc': 'atalanta',
        'bologna fc': 'bologna',
        'torino fc': 'torino',
        'genoa cfc': 'genoa',
        'udinese calcio': 'udinese',
        'us lecce': 'lecce',
        'parma calcio': 'parma',
        'cagliari calcio': 'cagliari',
        'como 1907': 'como',
        # NEW 2025-26 promoted teams
        'sassuolo calcio': 'sassuolo',
        'pisa sc': 'pisa',
        'us cremonese': 'cremonese',
        'cremonese': 'cremonese'
    }
    normalized = team.lower().strip()
    return team_mappings.get(normalized, normalized)

def is_serie_a_team(team: str) -> bool:
    """Check if team is in Serie A 2025-26"""
    normalized = normalize_team(team)
    return any(normalize_team(sa_team) == normalized for sa_team in SERIE_A_TEAMS_2025_26)

def create_player_key(name: str, team: str) -> str:
    """Create unique key for player identification"""
    return f"{normalize_name(name)}@@{normalize_team(team)}"

def load_roster(roster_path: str) -> Tuple[List[Dict], Dict[str, Dict]]:
    """Load current roster and create lookup index"""
    try:
        with open(roster_path, "r", encoding="utf-8") as f:
            roster = json.load(f)
        
        # Create lookup index by player name (normalized)
        index = {}
        for player in roster:
            name = player.get('name', '').strip()
            if name:
                norm_name = normalize_name(name)
                index[norm_name] = player
        
        LOG.info(f"Loaded roster with {len(roster)} players")
        return roster, index
        
    except Exception as e:
        LOG.error(f"Failed to load roster from {roster_path}: {e}")
        return [], {}

def load_transfers(transfers_path: str) -> List[Dict]:
    """Load transfer data from JSONL file"""
    transfers = []
    try:
        with open(transfers_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    transfer = json.loads(line)
                    if (transfer.get("season") == "2025-26" and 
                        transfer.get("type") == "transfer"):
                        transfers.append(transfer)
        
        LOG.info(f"Loaded {len(transfers)} transfers for 2025-26 season")
        return transfers
        
    except Exception as e:
        LOG.error(f"Failed to load transfers from {transfers_path}: {e}")
        return []

def get_player_role_from_position(position: str) -> str:
    """Map position string to role (P/D/C/A)"""
    if not position:
        return "NA"
    
    pos_lower = position.lower().strip()
    
    # Goalkeepers
    if any(x in pos_lower for x in ['goal', 'keeper', 'portiere', 'gk']):
        return "P"
    
    # Defenders  
    if any(x in pos_lower for x in ['def', 'back', 'difensore', 'cb', 'lb', 'rb', 'fullback']):
        return "D"
    
    # Forwards/Attackers
    if any(x in pos_lower for x in ['forward', 'striker', 'attaccante', 'cf', 'lw', 'rw', 'wing']):
        return "A"
    
    # Midfielders (default for remaining)
    return "C"

def create_new_player_record(transfer: Dict) -> Dict:
    """Create new player record from transfer data"""
    name = transfer.get('player', '').strip()
    team = transfer.get('to_team', '').strip()
    position = transfer.get('position', '').strip()
    
    return {
        "name": name,
        "role": get_player_role_from_position(position) if position else "NA",
        "team": team,
        "birth_year": None,
        "price": None,
        "fantamedia": None,
        "appearances": 0,
        "source": f"apify_transfers_{transfer.get('source_date', '2025-09-23')}",
        "source_date": transfer.get('source_date', '2025-09-23'),
        "name_prev": None
    }

def apply_transfers_to_roster(roster_path: str, transfers_path: str, dry_run: bool = False) -> Dict:
    """
    Apply transfers to roster with safety features
    
    Returns:
        dict: Summary of changes made
    """
    # Load current data
    roster, player_index = load_roster(roster_path)
    transfers = load_transfers(transfers_path)
    
    if not roster:
        LOG.error("Cannot proceed without valid roster")
        return {"error": "Failed to load roster"}
    
    if not transfers:
        LOG.warning("No transfers to process")
        return {"transfers_processed": 0}
    
    # Track changes
    changes = {
        "players_added": 0,
        "players_moved": 0,
        "players_transferred_out": 0,
        "intra_serie_a_moves": 0,
        "skipped_duplicates": 0,
        "added_players": [],
        "moved_players": [],
        "transferred_out": []
    }
    
    new_players = []
    updated_roster = roster.copy()
    
    LOG.info(f"Processing {len(transfers)} transfers...")
    
    for transfer in transfers:
        player_name = transfer.get('player', '').strip()
        direction = transfer.get('direction', '').strip()
        to_team = transfer.get('to_team', '').strip()
        from_team = transfer.get('from_team', '').strip()
        
        if not player_name:
            continue
            
        norm_name = normalize_name(player_name)
        
        if direction == "in" and to_team:
            # Incoming transfer
            norm_to_team = normalize_team(to_team)
            
            if is_serie_a_team(to_team):
                # Check if player already exists in roster
                existing_player = player_index.get(norm_name)
                
                if existing_player:
                    # Update existing player's team
                    old_team = existing_player.get('team', '')
                    existing_player['team'] = to_team
                    changes["players_moved"] += 1
                    changes["moved_players"].append({
                        "name": player_name,
                        "from": old_team,
                        "to": to_team
                    })
                    LOG.info(f"[MOVE] {player_name}: {old_team} → {to_team}")
                    
                    if is_serie_a_team(old_team):
                        changes["intra_serie_a_moves"] += 1
                else:
                    # Add new player to roster
                    new_player = create_new_player_record(transfer)
                    new_player['team'] = to_team
                    new_players.append(new_player)
                    player_index[norm_name] = new_player  # Add to index for future lookups
                    changes["players_added"] += 1
                    changes["added_players"].append({
                        "name": player_name,
                        "team": to_team,
                        "role": new_player.get('role', 'NA')
                    })
                    LOG.info(f"[ADD] {player_name} → {to_team} (role: {new_player.get('role', 'NA')})")
        
        elif direction == "out" and from_team:
            # Outgoing transfer
            existing_player = player_index.get(norm_name)
            
            if existing_player and not to_team:
                # Player leaving Serie A (no destination team specified)
                # Mark as transferred out by removing from active roster
                if existing_player in updated_roster:
                    updated_roster.remove(existing_player)
                changes["players_transferred_out"] += 1
                changes["transferred_out"].append({
                    "name": player_name,
                    "from": from_team
                })
                LOG.info(f"[OUT] {player_name} left Serie A from {from_team}")
    
    # Combine original roster (minus transferred out) with new players
    final_roster = updated_roster + new_players
    
    # Remove duplicates based on normalized name
    seen_names = set()
    deduplicated_roster = []
    for player in final_roster:
        name = player.get('name', '').strip()
        if name:
            norm_name = normalize_name(name)
            if norm_name not in seen_names:
                seen_names.add(norm_name)
                deduplicated_roster.append(player)
            else:
                changes["skipped_duplicates"] += 1
    
    changes["final_roster_size"] = len(deduplicated_roster)
    changes["original_roster_size"] = len(roster)
    
    LOG.info(f"Transfer processing summary:")
    LOG.info(f"  Players added: {changes['players_added']}")
    LOG.info(f"  Players moved: {changes['players_moved']}")
    LOG.info(f"  Players transferred out: {changes['players_transferred_out']}")
    LOG.info(f"  Intra-Serie A moves: {changes['intra_serie_a_moves']}")
    LOG.info(f"  Duplicates skipped: {changes['skipped_duplicates']}")
    LOG.info(f"  Final roster size: {changes['final_roster_size']} (was {changes['original_roster_size']})")
    
    if dry_run:
        LOG.info("[DRY RUN] No changes written to file")
        return changes
    
    # Write results with backup and atomic operation
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{roster_path}_backup_{timestamp}"
    temp_path = f"{roster_path}.tmp"
    
    try:
        # Create backup
        shutil.copy2(roster_path, backup_path)
        LOG.info(f"Backup created: {backup_path}")
        
        # Write to temporary file
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(deduplicated_roster, f, indent=2, ensure_ascii=False)
        
        # Atomic rename
        shutil.move(temp_path, roster_path)
        LOG.info(f"Roster updated successfully: {roster_path}")
        
        changes["backup_path"] = backup_path
        
    except Exception as e:
        LOG.error(f"Failed to write updated roster: {e}")
        if os.path.exists(temp_path):
            os.remove(temp_path)
        changes["error"] = str(e)
    
    return changes

def main():
    """Main execution function"""
    roster_path = "season_roster.json"
    transfers_path = "data/apify_transfers_serie_a_combined_2025-26_20250923_221356.jsonl"
    
    if not os.path.exists(roster_path):
        LOG.error(f"Roster file not found: {roster_path}")
        return
    
    if not os.path.exists(transfers_path):
        LOG.error(f"Transfers file not found: {transfers_path}")
        return
    
    # Run dry run first
    LOG.info("=== DRY RUN ===")
    dry_results = apply_transfers_to_roster(roster_path, transfers_path, dry_run=True)
    
    if "error" in dry_results:
        LOG.error(f"Dry run failed: {dry_results['error']}")
        return
    
    # Ask for confirmation (in automated context, proceed)
    LOG.info("=== APPLYING TRANSFERS ===")
    results = apply_transfers_to_roster(roster_path, transfers_path, dry_run=False)
    
    if "error" in results:
        LOG.error(f"Transfer application failed: {results['error']}")
    else:
        LOG.info("Transfer application completed successfully")
    
    # Print summary
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()