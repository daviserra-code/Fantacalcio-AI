#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Transfer Reconciliation ETL Job
Updates player status and excludes players who transferred out of Serie A
"""

import json
import logging
import sqlite3
import requests
from datetime import datetime
from typing import Dict, List, Optional, Set
import os

LOG = logging.getLogger(__name__)

# Serie A teams whitelist 2025-26 season - players not in these teams are marked as transferred_out
SERIE_A_TEAMS = {
    'Atalanta', 'Bologna', 'Cagliari', 'Como', 'Fiorentina', 
    'Genoa', 'Inter', 'Juventus', 'Lazio', 'Lecce', 'Milan', 
    'Napoli', 'Parma', 'Roma', 'Torino', 'Udinese', 'Verona',
    # NEW 2025-26: Promoted from Serie B
    'Sassuolo', 'Pisa', 'Cremonese'
    # REMOVED 2025-26: Relegated to Serie B (Empoli, Venezia, Monza)
}

def normalize_name(name: str) -> str:
    """Normalize player name for matching"""
    return name.lower().strip().replace("'", "").replace("-", " ")

def normalize_team(team: str) -> str:
    """Normalize team name for matching"""
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

def create_canonical_key(name: str, team: str) -> str:
    """Create canonical key for player identification"""
    return f"{normalize_name(name)}@@{normalize_team(team)}"

class TransferReconciler:
    def __init__(self, db_path: str = "fantacalcio.db"):
        self.db_path = db_path
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'FantacalcioAssistant/1.0 (Educational Purpose)'
        })

    def load_current_roster(self) -> List[Dict]:
        """Load current season roster"""
        try:
            with open("season_roster.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            LOG.error(f"Failed to load season_roster.json: {e}")
            return []

    def initialize_player_data(self, roster: List[Dict]) -> None:
        """Initialize player identity and status tables from current roster"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            for player in roster:
                name = player.get('name', '').strip()
                team = player.get('team', '').strip()
                birth_year = player.get('birth_year')
                
                if not name or not team:
                    continue
                    
                canonical_key = create_canonical_key(name, team)
                
                # Insert or update player identity
                cursor.execute("""
                    INSERT OR REPLACE INTO player_identity 
                    (canonical_key, name, birth_year, team_history, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (canonical_key, name, birth_year, json.dumps([team])))
                
                # Determine status based on team
                normalized_team = normalize_team(team)
                is_serie_a = any(normalize_team(sa_team) == normalized_team for sa_team in SERIE_A_TEAMS)
                
                status = 'active' if is_serie_a else 'transferred_out'
                league = 'Serie A' if is_serie_a else 'Unknown'
                
                # Insert or update player status
                cursor.execute("""
                    INSERT OR REPLACE INTO player_status 
                    (canonical_key, current_team, current_league, status, last_verified)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (canonical_key, team, league, status))
                
            conn.commit()
            LOG.info(f"Initialized player data for {len(roster)} players")

    def check_known_transfers(self) -> Dict[str, Dict]:
        """Check for known transfers that need manual verification"""
        known_transfers = {
            'tijjani reijnders': {
                'from_team': 'Milan',
                'to_team': 'Manchester City',
                'to_league': 'Premier League',
                'transfer_date': '2025-06-01',
                'status': 'transferred_out'
            },
            # Add more known transfers here as needed
        }
        return known_transfers

    def apply_known_transfers(self) -> None:
        """Apply known transfers to update player status"""
        transfers = self.check_known_transfers()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            for player_name, transfer_info in transfers.items():
                # Find player by name (fuzzy matching)
                cursor.execute("""
                    SELECT canonical_key, name FROM player_identity 
                    WHERE LOWER(name) LIKE ?
                """, (f"%{player_name}%",))
                
                matches = cursor.fetchall()
                
                for canonical_key, full_name in matches:
                    # Update player status
                    cursor.execute("""
                        UPDATE player_status 
                        SET current_team = ?, current_league = ?, status = ?, last_verified = CURRENT_TIMESTAMP
                        WHERE canonical_key = ?
                    """, (transfer_info['to_team'], transfer_info['to_league'], 
                          transfer_info['status'], canonical_key))
                    
                    # Record transfer
                    cursor.execute("""
                        INSERT OR REPLACE INTO player_transfers 
                        (canonical_key, from_team, to_team, transfer_date, transfer_type, source, verified)
                        VALUES (?, ?, ?, ?, 'permanent', 'manual', TRUE)
                    """, (canonical_key, transfer_info['from_team'], transfer_info['to_team'], 
                          transfer_info['transfer_date']))
                    
                    LOG.info(f"Applied transfer: {full_name} -> {transfer_info['to_team']}")
            
            conn.commit()

    def get_transferred_players(self) -> List[str]:
        """Get list of players who transferred out of Serie A"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT pi.name, ps.current_team, ps.current_league
                FROM player_identity pi
                JOIN player_status ps ON pi.canonical_key = ps.canonical_key
                WHERE ps.status = 'transferred_out'
                ORDER BY pi.name
            """)
            return cursor.fetchall()

    def add_to_exclusions(self) -> None:
        """Add transferred players to the corrections exclusions system"""
        transferred_players = self.get_transferred_players()
        
        with sqlite3.connect("corrections.db") as conn:
            cursor = conn.cursor()
            
            for name, team, league in transferred_players:
                player_key = normalize_name(name)
                
                # Add to exclusions table if not already present
                cursor.execute("""
                    INSERT OR IGNORE INTO exclusions (player_key, player_name, team)
                    VALUES (?, ?, ?)
                """, (player_key, name, f"{team} ({league})"))
                
            conn.commit()
            LOG.info(f"Added {len(transferred_players)} transferred players to exclusions")

    def run_reconciliation(self) -> Dict:
        """Run complete transfer reconciliation process"""
        LOG.info("Starting transfer reconciliation...")
        
        roster = self.load_current_roster()
        if not roster:
            return {"error": "Failed to load roster"}
        
        # Initialize player data
        self.initialize_player_data(roster)
        
        # Apply known transfers
        self.apply_known_transfers()
        
        # Add to exclusions
        self.add_to_exclusions()
        
        # Get summary
        transferred_players = self.get_transferred_players()
        
        summary = {
            "total_players": len(roster),
            "transferred_out": len(transferred_players),
            "transferred_players": [{"name": name, "team": team, "league": league} 
                                   for name, team, league in transferred_players],
            "timestamp": datetime.now().isoformat()
        }
        
        LOG.info(f"Transfer reconciliation completed: {len(transferred_players)} players transferred out")
        return summary

def main():
    """Main function for running as standalone script"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    reconciler = TransferReconciler()
    result = reconciler.run_reconciliation()
    
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()