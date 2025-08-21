
import json
import os
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from document_parser import DocumentParser

LOG = logging.getLogger("league_rules_manager")

class LeagueRulesManager:
    def __init__(self, rules_file_path: str = "./data/league_rules.json"):
        self.rules_file_path = rules_file_path
        self.rules = self._load_rules()
        self._ensure_default_structure()
    
    def _load_rules(self) -> Dict[str, Any]:
        """Load rules from JSON file or create default structure"""
        if os.path.exists(self.rules_file_path):
            try:
                with open(self.rules_file_path, "r", encoding="utf-8") as f:
                    rules = json.load(f)
                LOG.info(f"[RulesManager] Loaded rules from {self.rules_file_path}")
                return rules
            except Exception as e:
                LOG.error(f"[RulesManager] Error loading rules: {e}")
        
        return self._get_default_rules()
    
    def _get_default_rules(self) -> Dict[str, Any]:
        """Get default league rules structure"""
        return {
            "league_info": {
                "name": "LEGA FANTATSS",
                "season": "2024-25",
                "participants": 8,
                "league_type": "Classic",
                "created_date": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat()
            },
            "roster_composition": {
                "portieri": 3,
                "difensori": 8,
                "centrocampisti": 8,
                "attaccanti": 6,
                "total_players": 25
            },
            "budget_rules": {
                "total_budget": 500,
                "currency": "crediti",
                "minimum_bid": 1,
                "bid_increment": 1
            },
            "auction_rules": {
                "auction_type": "Classic",
                "time_per_player": 120,
                "nomination_order": "snake",
                "max_same_team_players": 3,
                "bench_players": 7
            },
            "formation_rules": {
                "allowed_formations": [
                    "3-4-3", "3-5-2", "4-3-3", "4-4-2", "4-5-1", "5-3-2", "5-4-1"
                ],
                "default_formation": "3-5-2",
                "captain_multiplier": 2.0,
                "vice_captain_multiplier": 1.5
            },
            "scoring_system": {
                "fantamedia_base": True,
                "bonus_gol": 3,
                "bonus_assist": 1,
                "bonus_rigore_parato": 3,
                "bonus_rigore_sbagliato": -3,
                "bonus_autogol": -2,
                "bonus_espulsione": -1,
                "bonus_ammonizione": -0.5,
                "clean_sheet_portiere": 1,
                "clean_sheet_difensore": 1
            },
            "transfer_rules": {
                "transfer_windows": [
                    {"start": "2024-09-01", "end": "2024-09-15", "type": "Regular"},
                    {"start": "2025-01-15", "end": "2025-01-31", "type": "Winter"}
                ],
                "max_transfers_per_window": 3,
                "transfer_cost": 2,
                "free_transfers_per_season": 2
            },
            "playoff_rules": {
                "playoff_teams": 4,
                "playoff_format": "Single elimination",
                "playoff_start_gameweek": 35,
                "championship_weeks": [36, 37, 38]
            },
            "special_rules": {
                "injury_replacement": True,
                "covid_replacement": True,
                "postponed_match_policy": "Average of last 3 games",
                "technical_fouls": True
            },
            "penalties": {
                "late_formation": 2,
                "missing_formation": 10,
                "invalid_formation": 5,
                "roster_violation": 25
            },
            "custom_rules": {
                "notes": [
                    "Add your specific league rules here",
                    "These can be customized based on your PDF rules"
                ],
                "house_rules": [],
                "modifications": []
            }
        }
    
    def _ensure_default_structure(self):
        """Ensure all required sections exist in rules"""
        default_rules = self._get_default_rules()
        
        for section_key, section_value in default_rules.items():
            if section_key not in self.rules:
                self.rules[section_key] = section_value
                LOG.info(f"[RulesManager] Added missing section: {section_key}")
        
        # Update last_updated timestamp
        self.rules["league_info"]["last_updated"] = datetime.now().isoformat()
    
    def save_rules(self) -> bool:
        """Save rules to JSON file"""
        try:
            os.makedirs(os.path.dirname(self.rules_file_path), exist_ok=True)
            
            # Update timestamp
            self.rules["league_info"]["last_updated"] = datetime.now().isoformat()
            
            with open(self.rules_file_path, "w", encoding="utf-8") as f:
                json.dump(self.rules, f, indent=2, ensure_ascii=False)
            
            LOG.info(f"[RulesManager] Rules saved to {self.rules_file_path}")
            return True
        except Exception as e:
            LOG.error(f"[RulesManager] Error saving rules: {e}")
            return False
    
    def get_rules(self) -> Dict[str, Any]:
        """Get all rules"""
        return self.rules
    
    def get_section(self, section_name: str) -> Optional[Dict[str, Any]]:
        """Get a specific rules section"""
        return self.rules.get(section_name)
    
    def update_section(self, section_name: str, section_data: Dict[str, Any]) -> bool:
        """Update a specific rules section"""
        try:
            if section_name in self.rules:
                self.rules[section_name].update(section_data)
            else:
                self.rules[section_name] = section_data
            
            return self.save_rules()
        except Exception as e:
            LOG.error(f"[RulesManager] Error updating section {section_name}: {e}")
            return False
    
    def update_rule(self, section_name: str, rule_name: str, value: Any) -> bool:
        """Update a specific rule within a section"""
        try:
            if section_name not in self.rules:
                self.rules[section_name] = {}
            
            self.rules[section_name][rule_name] = value
            return self.save_rules()
        except Exception as e:
            LOG.error(f"[RulesManager] Error updating rule {section_name}.{rule_name}: {e}")
            return False
    
    def add_custom_rule(self, rule_description: str, rule_type: str = "house_rules") -> bool:
        """Add a custom rule"""
        try:
            if "custom_rules" not in self.rules:
                self.rules["custom_rules"] = {"house_rules": [], "modifications": [], "notes": []}
            
            if rule_type not in self.rules["custom_rules"]:
                self.rules["custom_rules"][rule_type] = []
            
            rule_entry = {
                "description": rule_description,
                "added_date": datetime.now().isoformat(),
                "active": True
            }
            
            self.rules["custom_rules"][rule_type].append(rule_entry)
            return self.save_rules()
        except Exception as e:
            LOG.error(f"[RulesManager] Error adding custom rule: {e}")
            return False
    
    def get_rules_summary(self) -> Dict[str, Any]:
        """Get a summary of key rules for display"""
        return {
            "league_name": self.rules.get("league_info", {}).get("name", "Unknown League"),
            "participants": self.rules.get("league_info", {}).get("participants", 0),
            "budget": self.rules.get("budget_rules", {}).get("total_budget", 500),
            "roster_size": self.rules.get("roster_composition", {}).get("total_players", 25),
            "formations": len(self.rules.get("formation_rules", {}).get("allowed_formations", [])),
            "transfer_windows": len(self.rules.get("transfer_rules", {}).get("transfer_windows", [])),
            "last_updated": self.rules.get("league_info", {}).get("last_updated", "Never")
        }
    
    def validate_formation(self, formation: str) -> bool:
        """Validate if a formation is allowed"""
        allowed = self.rules.get("formation_rules", {}).get("allowed_formations", [])
        return formation in allowed
    
    def get_scoring_rules(self) -> Dict[str, Any]:
        """Get scoring system rules"""
        return self.rules.get("scoring_system", {})
    
    def is_transfer_window_open(self, date_str: Optional[str] = None) -> bool:
        """Check if transfer window is currently open"""
        if date_str is None:
            date_str = datetime.now().isoformat()[:10]  # YYYY-MM-DD
        
        windows = self.rules.get("transfer_rules", {}).get("transfer_windows", [])
        for window in windows:
            if window["start"] <= date_str <= window["end"]:
                return True
        return False
    
    def import_from_document(self, file_path: str) -> bool:
        """Import rules from a document file (DOCX or TXT)"""
        try:
            parser = DocumentParser()
            result = parser.parse_file(file_path)
            
            if "error" in result:
                LOG.error(f"[RulesManager] Document parsing error: {result['error']}")
                return False
            
            structured_rules = result.get("structured_rules", {})
            
            # Update existing rules with parsed data
            for section_name, section_data in structured_rules.items():
                if section_data and section_name in self.rules:
                    # Merge with existing rules
                    if isinstance(self.rules[section_name], dict) and isinstance(section_data, dict):
                        self.rules[section_name].update(section_data)
                    else:
                        self.rules[section_name] = section_data
            
            # Add raw text to custom rules for reference
            raw_text = result.get("raw_text", "")
            if raw_text:
                if "document_import" not in self.rules:
                    self.rules["document_import"] = {}
                
                self.rules["document_import"] = {
                    "imported_at": datetime.now().isoformat(),
                    "source_file": os.path.basename(file_path),
                    "raw_content": raw_text[:2000] + ("..." if len(raw_text) > 2000 else "")  # Truncate for storage
                }
            
            # Save updated rules
            success = self.save_rules()
            if success:
                LOG.info(f"[RulesManager] Successfully imported rules from {file_path}")
            
            return success
            
        except Exception as e:
            LOG.error(f"[RulesManager] Error importing document: {e}")
            return False

    def export_rules_txt(self) -> str:
        """Export rules as formatted text for easy reading"""
        lines = []
        lines.append(f"🏆 {self.rules['league_info']['name']} - Regolamento")
        lines.append("=" * 50)
        lines.append("")
        
        # League Info
        lines.append("📋 INFORMAZIONI LEGA")
        info = self.rules["league_info"]
        lines.append(f"Stagione: {info.get('season', 'N/D')}")
        lines.append(f"Partecipanti: {info.get('participants', 'N/D')}")
        lines.append(f"Tipo: {info.get('league_type', 'Classic')}")
        lines.append("")
        
        # Budget
        lines.append("💰 BUDGET E ASTA")
        budget = self.rules["budget_rules"]
        lines.append(f"Budget totale: {budget.get('total_budget', 500)} {budget.get('currency', 'crediti')}")
        lines.append(f"Rilancio minimo: {budget.get('minimum_bid', 1)} {budget.get('currency', 'crediti')}")
        lines.append("")
        
        # Roster
        lines.append("👥 COMPOSIZIONE ROSA")
        roster = self.rules["roster_composition"]
        lines.append(f"Portieri: {roster.get('portieri', 3)}")
        lines.append(f"Difensori: {roster.get('difensori', 8)}")
        lines.append(f"Centrocampisti: {roster.get('centrocampisti', 8)}")
        lines.append(f"Attaccanti: {roster.get('attaccanti', 6)}")
        lines.append(f"Totale giocatori: {roster.get('total_players', 25)}")
        lines.append("")
        
        # Formations
        lines.append("⚽ FORMAZIONI CONSENTITE")
        formations = self.rules.get("formation_rules", {}).get("allowed_formations", [])
        lines.append(", ".join(formations))
        lines.append("")
        
        # Scoring
        lines.append("🎯 SISTEMA DI PUNTEGGIO")
        scoring = self.rules["scoring_system"]
        for key, value in scoring.items():
            if key != "fantamedia_base":
                lines.append(f"{key.replace('_', ' ').title()}: {value}")
        lines.append("")
        
        # Custom Rules
        custom = self.rules.get("custom_rules", {})
        if custom.get("house_rules"):
            lines.append("🏠 REGOLE PERSONALIZZATE")
            for rule in custom["house_rules"]:
                if isinstance(rule, dict):
                    lines.append(f"- {rule.get('description', rule)}")
                else:
                    lines.append(f"- {rule}")
            lines.append("")
        
        return "\n".join(lines)
