
from datetime import datetime, timedelta
from typing import Dict, List
import json

class InjuryPredictor:
    def __init__(self):
        self.risk_factors = {
            "age": {"threshold": 30, "weight": 0.3},
            "minutes": {"threshold": 2500, "weight": 0.4},
            "injury_history": {"weight": 0.5},
            "position_risk": {
                "P": 0.1, "D": 0.3, "C": 0.4, "A": 0.5
            }
        }
    
    def assess_injury_risk(self, player_data: Dict) -> Dict:
        """Assess injury risk for a player"""
        risk_score = 0
        risk_factors = []
        
        # Age factor
        age = player_data.get("age", 25)
        if age > 30:
            age_risk = min((age - 30) * 0.1, 0.5)
            risk_score += age_risk
            risk_factors.append(f"Età elevata ({age} anni)")
        
        # Minutes played factor
        minutes = player_data.get("minutes_played", 0)
        if minutes > 2500:
            minutes_risk = min((minutes - 2500) / 1000 * 0.2, 0.4)
            risk_score += minutes_risk
            risk_factors.append("Alto minutaggio")
        
        # Position risk
        position = player_data.get("role", "C")
        position_risk = self.risk_factors["position_risk"].get(position, 0.3)
        risk_score += position_risk
        
        # Recent injury history
        recent_injuries = player_data.get("recent_injuries", 0)
        if recent_injuries > 0:
            injury_risk = min(recent_injuries * 0.2, 0.6)
            risk_score += injury_risk
            risk_factors.append(f"{recent_injuries} infortuni recenti")
        
        risk_level = self._categorize_risk(risk_score)
        
        return {
            "player": player_data.get("name", "Unknown"),
            "risk_score": round(risk_score, 2),
            "risk_level": risk_level,
            "risk_factors": risk_factors,
            "recommendation": self._get_recommendation(risk_level)
        }
    
    def _categorize_risk(self, score: float) -> str:
        """Categorize risk based on score"""
        if score < 0.3:
            return "BASSO"
        elif score < 0.6:
            return "MEDIO"
        elif score < 0.8:
            return "ALTO"
        else:
            return "MOLTO ALTO"
    
    def _get_recommendation(self, risk_level: str) -> str:
        """Get recommendation based on risk level"""
        recommendations = {
            "BASSO": "✅ Giocatore affidabile, basso rischio infortuni",
            "MEDIO": "⚠️ Rischio moderato, considera alternative",
            "ALTO": "🚨 Alto rischio, investi con cautela",
            "MOLTO ALTO": "❌ Sconsigliato, troppo rischioso"
        }
        return recommendations.get(risk_level, "Valutazione non disponibile")
