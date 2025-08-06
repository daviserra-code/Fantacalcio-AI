
import statistics
from typing import List, Dict, Any
from fantacalcio_data import Player, SAMPLE_PLAYERS

class PlayerAnalytics:
    def __init__(self):
        self.players = SAMPLE_PLAYERS
        
    def get_player_efficiency_score(self, player: Player) -> float:
        """Calculate efficiency score: fantamedia per credit spent"""
        if player.price == 0:
            return 0
        return round(player.fantamedia / player.price * 100, 2)
    
    def get_role_statistics(self, role: str) -> Dict[str, Any]:
        """Get comprehensive statistics for a role"""
        role_players = [p for p in self.players if p.role == role]
        if not role_players:
            return {}
        
        fantamedias = [p.fantamedia for p in role_players]
        prices = [p.price for p in role_players]
        
        return {
            'count': len(role_players),
            'avg_fantamedia': round(statistics.mean(fantamedias), 2),
            'median_fantamedia': round(statistics.median(fantamedias), 2),
            'std_fantamedia': round(statistics.stdev(fantamedias) if len(fantamedias) > 1 else 0, 2),
            'avg_price': round(statistics.mean(prices), 2),
            'median_price': round(statistics.median(prices), 2),
            'top_performers': sorted(role_players, key=lambda x: x.fantamedia, reverse=True)[:3],
            'best_value': sorted(role_players, key=self.get_player_efficiency_score, reverse=True)[:3]
        }
    
    def suggest_formation_optimization(self, budget: int, league_type: str = "Classic") -> Dict[str, Any]:
        """Suggest optimal formation based on budget and league type"""
        budget_distribution = {
            "Classic": {"P": 0.15, "D": 0.30, "C": 0.35, "A": 0.20},
            "Mantra": {"P": 0.12, "D": 0.28, "C": 0.40, "A": 0.20},
            "Draft": {"P": 0.20, "D": 0.25, "C": 0.30, "A": 0.25}
        }
        
        distribution = budget_distribution.get(league_type, budget_distribution["Classic"])
        
        suggestions = {}
        for role, percentage in distribution.items():
            role_budget = int(budget * percentage)
            role_stats = self.get_role_statistics(role)
            affordable_players = [p for p in self.players if p.role == role and p.price <= role_budget]
            
            suggestions[role] = {
                'budget': role_budget,
                'recommended_players': sorted(affordable_players, key=lambda x: x.fantamedia, reverse=True)[:5],
                'stats': role_stats
            }
        
        return suggestions
    
    def get_injury_risk_analysis(self, player: Player) -> Dict[str, Any]:
        """Analyze injury risk based on appearances"""
        max_appearances = 38  # Serie A games
        appearance_rate = player.appearances / max_appearances if max_appearances > 0 else 0
        
        if appearance_rate >= 0.9:
            risk_level = "Basso"
            risk_score = 1
        elif appearance_rate >= 0.75:
            risk_level = "Medio-Basso"
            risk_score = 2
        elif appearance_rate >= 0.6:
            risk_level = "Medio"
            risk_score = 3
        elif appearance_rate >= 0.4:
            risk_level = "Medio-Alto"
            risk_score = 4
        else:
            risk_level = "Alto"
            risk_score = 5
        
        return {
            'risk_level': risk_level,
            'risk_score': risk_score,
            'appearance_rate': round(appearance_rate * 100, 1),
            'games_missed': max_appearances - player.appearances,
            'recommendation': self._get_risk_recommendation(risk_score)
        }
    
    def _get_risk_recommendation(self, risk_score: int) -> str:
        recommendations = {
            1: "Giocatore molto affidabile, investimento sicuro",
            2: "Buona scelta, rischio contenuto",
            3: "Valuta alternative, rischio moderato",
            4: "Sconsigliato come titolare fisso",
            5: "Alto rischio, considera solo come scommessa"
        }
        return recommendations.get(risk_score, "Analisi non disponibile")

