
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from typing import Dict, List, Tuple
import json

class AdvancedAnalytics:
    def __init__(self, knowledge_manager):
        self.km = knowledge_manager
        self.models = {}
        
    def predict_player_performance(self, player_name: str, next_matches: int = 5) -> Dict:
        """Predict player performance for upcoming matches"""
        player_data = self.get_player_historical_data(player_name)
        
        if not player_data:
            return {'error': 'Player data not found'}
        
        # Feature engineering
        features = self.extract_features(player_data)
        
        # Predict fantasy points
        model = self.get_or_train_model('fantasy_points')
        predictions = model.predict([features])[0]
        
        # Calculate confidence intervals
        confidence = self.calculate_confidence(player_data, predictions)
        
        return {
            'player': player_name,
            'predicted_points': round(predictions, 2),
            'confidence': confidence,
            'trend': self.analyze_trend(player_data),
            'recommendation': self.generate_recommendation(predictions, confidence)
        }
    
    def analyze_market_trends(self, role: str = None) -> Dict:
        """Analyze fantasy market trends"""
        players_data = self.km.get_all_players()
        
        trends = {
            'rising_stars': [],
            'falling_stars': [],
            'undervalued': [],
            'overvalued': [],
            'injury_risks': []
        }
        
        for player in players_data:
            if role and player.get('role') != role:
                continue
                
            trend_score = self.calculate_trend_score(player)
            value_ratio = self.calculate_value_ratio(player)
            
            if trend_score > 0.7:
                trends['rising_stars'].append(player)
            elif trend_score < -0.7:
                trends['falling_stars'].append(player)
                
            if value_ratio > 1.2:
                trends['undervalued'].append(player)
            elif value_ratio < 0.8:
                trends['overvalued'].append(player)
        
        return trends
    
    def optimize_formation(self, available_players: List[Dict], budget: int, formation: str) -> Dict:
        """AI-powered formation optimization"""
        formation_map = {
            '3-5-2': {'D': 3, 'C': 5, 'A': 2, 'P': 1},
            '4-3-3': {'D': 4, 'C': 3, 'A': 3, 'P': 1},
            '4-4-2': {'D': 4, 'C': 4, 'A': 2, 'P': 1},
            '3-4-3': {'D': 3, 'C': 4, 'A': 3, 'P': 1}
        }
        
        required = formation_map.get(formation, formation_map['3-5-2'])
        
        # Use genetic algorithm for optimization
        best_team = self.genetic_optimization(available_players, required, budget)
        
        return {
            'formation': formation,
            'team': best_team,
            'total_cost': sum(p['price'] for p in best_team),
            'predicted_points': sum(self.predict_player_performance(p['name'])['predicted_points'] for p in best_team),
            'optimization_score': self.calculate_team_score(best_team)
        }
    
    def get_player_historical_data(self, player_name: str) -> List[Dict]:
        """Get historical performance data"""
        # Implementation depends on your data structure
        return []
    
    def extract_features(self, player_data: List[Dict]) -> List[float]:
        """Extract ML features from player data"""
        if not player_data:
            return [0] * 10
        
        # Example features
        recent_avg = np.mean([p.get('fantamedia', 0) for p in player_data[-5:]])
        season_avg = np.mean([p.get('fantamedia', 0) for p in player_data])
        consistency = np.std([p.get('fantamedia', 0) for p in player_data])
        
        return [recent_avg, season_avg, consistency, len(player_data)]
    
    def get_or_train_model(self, model_type: str):
        """Get or train ML model"""
        if model_type not in self.models:
            # Simple model for demo - replace with actual training
            self.models[model_type] = LinearRegression()
            # Mock training data
            X = np.random.rand(100, 4)
            y = np.random.rand(100) * 10
            self.models[model_type].fit(X, y)
        
        return self.models[model_type]
    
    def calculate_confidence(self, player_data: List[Dict], prediction: float) -> float:
        """Calculate prediction confidence"""
        if not player_data:
            return 0.5
        
        consistency = 1 / (1 + np.std([p.get('fantamedia', 0) for p in player_data]))
        data_quality = min(len(player_data) / 20, 1)
        
        return (consistency + data_quality) / 2
    
    def analyze_trend(self, player_data: List[Dict]) -> str:
        """Analyze performance trend"""
        if len(player_data) < 3:
            return 'insufficient_data'
        
        recent = np.mean([p.get('fantamedia', 0) for p in player_data[-3:]])
        older = np.mean([p.get('fantamedia', 0) for p in player_data[:-3]])
        
        if recent > older * 1.1:
            return 'improving'
        elif recent < older * 0.9:
            return 'declining'
        else:
            return 'stable'
    
    def generate_recommendation(self, predicted_points: float, confidence: float) -> str:
        """Generate buy/sell/hold recommendation"""
        if confidence < 0.3:
            return 'hold - insufficient data'
        elif predicted_points > 7 and confidence > 0.7:
            return 'strong_buy'
        elif predicted_points > 6 and confidence > 0.6:
            return 'buy'
        elif predicted_points < 4:
            return 'sell'
        else:
            return 'hold'
    
    def calculate_trend_score(self, player: Dict) -> float:
        """Calculate trend score for market analysis"""
        # Mock implementation
        return np.random.uniform(-1, 1)
    
    def calculate_value_ratio(self, player: Dict) -> float:
        """Calculate value ratio (performance vs price)"""
        fantamedia = player.get('fantamedia', 0)
        price = player.get('price', 1)
        
        if price == 0:
            return 0
        
        return fantamedia / (price / 10)  # Normalize price
    
    def genetic_optimization(self, players: List[Dict], required: Dict, budget: int) -> List[Dict]:
        """Genetic algorithm for team optimization"""
        # Simplified implementation - return best value players for each position
        optimized_team = []
        remaining_budget = budget
        
        for role, count in required.items():
            role_players = [p for p in players if p.get('role') == role and p.get('price', 0) <= remaining_budget]
            role_players.sort(key=lambda x: self.calculate_value_ratio(x), reverse=True)
            
            for i in range(min(count, len(role_players))):
                if role_players[i]['price'] <= remaining_budget:
                    optimized_team.append(role_players[i])
                    remaining_budget -= role_players[i]['price']
        
        return optimized_team
    
    def calculate_team_score(self, team: List[Dict]) -> float:
        """Calculate overall team optimization score"""
        if not team:
            return 0
        
        total_value = sum(self.calculate_value_ratio(p) for p in team)
        return total_value / len(team)
