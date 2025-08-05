
from fantacalcio_data import Player
from typing import List, Dict, Tuple
import itertools

class FormationOptimizer:
    def __init__(self):
        self.formations = {
            "3-4-3": {"D": 3, "C": 4, "A": 3},
            "3-5-2": {"D": 3, "C": 5, "A": 2},
            "4-3-3": {"D": 4, "C": 3, "A": 3},
            "4-4-2": {"D": 4, "C": 4, "A": 2},
            "4-5-1": {"D": 4, "C": 5, "A": 1},
            "5-3-2": {"D": 5, "C": 3, "A": 2},
            "5-4-1": {"D": 5, "C": 4, "A": 1}
        }
    
    def optimize_lineup(self, available_players: List[Player], formation: str = "3-5-2") -> Dict:
        """Find optimal lineup for given formation"""
        if formation not in self.formations:
            formation = "3-5-2"
        
        requirements = self.formations[formation]
        
        # Separate players by role
        players_by_role = {"P": [], "D": [], "C": [], "A": []}
        for player in available_players:
            if player.role in players_by_role:
                players_by_role[player.role].append(player)
        
        # Sort players by fantamedia (descending)
        for role in players_by_role:
            players_by_role[role].sort(key=lambda p: p.fantamedia, reverse=True)
        
        # Select best players for each role
        optimal_lineup = {}
        total_fantamedia = 0
        
        # Always need 1 goalkeeper
        if players_by_role["P"]:
            optimal_lineup["P"] = [players_by_role["P"][0]]
            total_fantamedia += players_by_role["P"][0].fantamedia
        
        # Select field players based on formation
        for role in ["D", "C", "A"]:
            needed = requirements[role]
            available = players_by_role[role][:needed]
            optimal_lineup[role] = available
            total_fantamedia += sum(p.fantamedia for p in available)
        
        return {
            "formation": formation,
            "lineup": optimal_lineup,
            "total_fantamedia": round(total_fantamedia, 2),
            "captain_suggestion": self._suggest_captain(optimal_lineup)
        }
    
    def _suggest_captain(self, lineup: Dict) -> Player:
        """Suggest best captain based on consistency and fantamedia"""
        all_field_players = []
        for role in ["D", "C", "A"]:
            all_field_players.extend(lineup.get(role, []))
        
        if not all_field_players:
            return None
        
        # Weight by fantamedia and appearances (consistency)
        best_captain = max(all_field_players, 
                          key=lambda p: p.fantamedia * (p.appearances / 38))
        return best_captain
    
    def compare_formations(self, available_players: List[Player]) -> List[Dict]:
        """Compare all formations and return ranked results"""
        results = []
        for formation in self.formations:
            result = self.optimize_lineup(available_players, formation)
            results.append(result)
        
        return sorted(results, key=lambda x: x["total_fantamedia"], reverse=True)
