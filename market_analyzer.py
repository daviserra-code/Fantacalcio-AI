
import time
from datetime import datetime, timedelta
from typing import Dict, List
import json

class MarketAnalyzer:
    def __init__(self):
        self.price_history = {}
        self.market_trends = {}
    
    def track_price_change(self, player_name: str, old_price: int, new_price: int):
        """Track price changes for market analysis"""
        if player_name not in self.price_history:
            self.price_history[player_name] = []
        
        self.price_history[player_name].append({
            'timestamp': datetime.now().isoformat(),
            'price': new_price,
            'change': new_price - old_price
        })
    
    def get_hot_players(self, hours: int = 24) -> List[Dict]:
        """Get players with most price increases"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        hot_players = []
        
        for player, history in self.price_history.items():
            recent_changes = [
                h for h in history 
                if datetime.fromisoformat(h['timestamp']) > cutoff_time
            ]
            
            if recent_changes:
                total_change = sum(h['change'] for h in recent_changes)
                if total_change > 0:
                    hot_players.append({
                        'player': player,
                        'price_increase': total_change,
                        'transactions': len(recent_changes)
                    })
        
        return sorted(hot_players, key=lambda x: x['price_increase'], reverse=True)
    
    def suggest_market_timing(self, player_name: str) -> str:
        """Suggest optimal timing for player acquisition"""
        if player_name not in self.price_history:
            return "Nessun dato storico disponibile"
        
        recent_trend = self.price_history[player_name][-5:]
        if len(recent_trend) < 2:
            return "Dati insufficienti per analisi"
        
        avg_change = sum(h['change'] for h in recent_trend) / len(recent_trend)
        
        if avg_change > 2:
            return f"⚠️ Prezzo in salita rapida (+{avg_change:.1f}/transazione). Considera di puntare ora."
        elif avg_change < -1:
            return f"📉 Prezzo in calo (-{abs(avg_change):.1f}/transazione). Aspetta ancora."
        else:
            return "📊 Prezzo stabile. Momento neutro per puntare."
