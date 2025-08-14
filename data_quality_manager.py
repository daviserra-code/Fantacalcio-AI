
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Data Quality Manager - Comprehensive tool for managing obsolete and incorrect data
"""

import json
import sqlite3
from typing import Dict, List, Any
from corrections_manager import CorrectionsManager

# Import the correct FantacalcioAssistant
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fantacalcio_assistant import FantacalcioAssistant

class DataQualityManager:
    def __init__(self):
        self.corrections_manager = CorrectionsManager()
        self.assistant = FantacalcioAssistant()
        
        # Known problematic data for 2024-25 season
        self.obsolete_players = {
            "Samir Handanovic": {"reason": "Retired/not playing", "replacement": None},
            "Wojciech Szczesny": {"reason": "Transferred/not in Serie A", "replacement": None},
            "Gianluigi Donnarumma": {"reason": "Plays for PSG, not Serie A", "replacement": None},
            "Marco Silvestri": {"reason": "Not first choice/outdated data", "replacement": None},
            "Milan Skriniar": {"reason": "Plays for PSG, not Serie A", "replacement": None},
            "Davide Calabria": {"reason": "Outdated/inconsistent data", "replacement": None}
        }
        
        self.team_updates = {
            "Alvaro Morata": "Como",
            "Khvicha Kvaratskhelia": "PSG",  # Transferred out of Serie A
        }
        
        # Current Serie A 2024-25 teams
        self.current_serie_a = {
            "Atalanta", "Bologna", "Cagliari", "Como", "Empoli", "Fiorentina",
            "Genoa", "Inter", "Juventus", "Lazio", "Lecce", "Milan",
            "Monza", "Napoli", "Parma", "Roma", "Torino", "Udinese",
            "Venezia", "Verona"
        }
    
    def clean_obsolete_data(self):
        """Remove all known obsolete players"""
        print("🧹 Cleaning obsolete player data...")
        
        removed_count = 0
        for player_name, info in self.obsolete_players.items():
            try:
                result = self.corrections_manager.remove_player(player_name, info["reason"])
                print(f"✅ {result}")
                removed_count += 1
            except Exception as e:
                print(f"❌ Failed to remove {player_name}: {e}")
        
        print(f"\n📊 Removed {removed_count} obsolete players")
        return removed_count
    
    def update_team_transfers(self):
        """Update known team transfers"""
        print("🔄 Updating team transfers...")
        
        updated_count = 0
        for player_name, new_team in self.team_updates.items():
            try:
                # Check if new team is Serie A
                if new_team in self.current_serie_a:
                    result = self.corrections_manager.update_player_team(player_name, "Previous Team", new_team)
                    print(f"✅ {result}")
                else:
                    # If transferred outside Serie A, remove
                    result = self.corrections_manager.remove_player(player_name, f"Transferred to {new_team} (non-Serie A)")
                    print(f"🚫 {result}")
                updated_count += 1
            except Exception as e:
                print(f"❌ Failed to update {player_name}: {e}")
        
        print(f"\n📊 Updated {updated_count} player transfers")
        return updated_count
    
    def filter_non_serie_a_teams(self):
        """Identify and mark non-Serie A players for removal"""
        print("🏟️ Filtering non-Serie A teams...")
        
        all_players = self.assistant._collect_all_players()
        non_serie_a_count = 0
        
        for player in all_players:
            team = player.get("team", "").strip()
            player_name = player.get("name", "").strip()
            
            if team and player_name:
                # Normalize team name for comparison
                team_normalized = team.lower().replace(" ", "").replace("-", "")
                serie_a_normalized = {t.lower().replace(" ", "").replace("-", "") for t in self.current_serie_a}
                
                if team_normalized not in serie_a_normalized:
                    try:
                        self.corrections_manager.remove_player(player_name, f"Non-Serie A team: {team}")
                        print(f"🚫 Removed {player_name} (plays for {team})")
                        non_serie_a_count += 1
                    except Exception as e:
                        print(f"❌ Failed to remove {player_name}: {e}")
        
        print(f"\n📊 Filtered {non_serie_a_count} non-Serie A players")
        return non_serie_a_count
    
    def validate_data_integrity(self):
        """Validate and report on data integrity issues"""
        print("🔍 Validating data integrity...")
        
        all_players = self.assistant._collect_all_players()
        issues = {
            "missing_price": [],
            "missing_fantamedia": [],
            "invalid_roles": [],
            "suspicious_names": []
        }
        
        valid_roles = {"P", "D", "C", "A"}
        
        for player in all_players:
            name = player.get("name", "").strip()
            price = player.get("price")
            fantamedia = player.get("fantamedia")
            role = player.get("role", "").strip().upper()
            
            if not price:
                issues["missing_price"].append(name)
            
            if not fantamedia:
                issues["missing_fantamedia"].append(name)
            
            if role not in valid_roles:
                issues["invalid_roles"].append(f"{name} (role: {role})")
            
            # Check for suspicious names
            if len(name) < 3 or any(char.isdigit() for char in name):
                issues["suspicious_names"].append(name)
        
        # Report issues
        print("\n📋 Data Integrity Report:")
        for issue_type, players in issues.items():
            if players:
                print(f"• {issue_type.replace('_', ' ').title()}: {len(players)} players")
                if len(players) <= 10:  # Show first 10
                    for player in players[:10]:
                        print(f"  - {player}")
                else:
                    print(f"  - {players[0]} (and {len(players)-1} others)")
        
        return issues
    
    def run_comprehensive_cleanup(self):
        """Run all cleanup operations"""
        print("🚀 Starting comprehensive data cleanup...\n")
        
        # Get initial stats
        initial_report = self.assistant.get_data_quality_report()
        print(f"📊 Initial stats: {initial_report['roster_stats']['total_players']} total players")
        
        # Run cleanup operations
        removed = self.clean_obsolete_data()
        updated = self.update_team_transfers()
        filtered = self.filter_non_serie_a_teams()
        
        # Validate remaining data
        issues = self.validate_data_integrity()
        
        # Get final stats
        final_report = self.assistant.get_data_quality_report()
        
        print(f"\n🎯 Cleanup Summary:")
        print(f"• Obsolete players removed: {removed}")
        print(f"• Team transfers updated: {updated}")
        print(f"• Non-Serie A players filtered: {filtered}")
        print(f"• Final player count: {final_report['roster_stats']['total_players']}")
        print(f"• Data completeness: {final_report['roster_stats']['data_completeness']}%")
        
        return {
            "removed": removed,
            "updated": updated,
            "filtered": filtered,
            "final_stats": final_report
        }

def main():
    manager = DataQualityManager()
    
    print("Data Quality Manager - Fantasy Football Assistant")
    print("=" * 50)
    
    while True:
        print("\nChoose an option:")
        print("1. Run comprehensive cleanup")
        print("2. Clean obsolete players only")
        print("3. Update team transfers only")
        print("4. Filter non-Serie A teams only")
        print("5. Validate data integrity")
        print("6. Get data quality report")
        print("0. Exit")
        
        choice = input("\nEnter your choice (0-6): ").strip()
        
        if choice == "0":
            print("👋 Goodbye!")
            break
        elif choice == "1":
            manager.run_comprehensive_cleanup()
        elif choice == "2":
            manager.clean_obsolete_data()
        elif choice == "3":
            manager.update_team_transfers()
        elif choice == "4":
            manager.filter_non_serie_a_teams()
        elif choice == "5":
            manager.validate_data_integrity()
        elif choice == "6":
            report = manager.assistant.get_data_quality_report()
            print(f"\n📊 Current Data Quality Report:")
            print(json.dumps(report, indent=2))
        else:
            print("❌ Invalid choice. Please try again.")

if __name__ == "__main__":
    main()
