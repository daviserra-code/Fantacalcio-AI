# ml_predictor.py - Machine Learning predictions for player performance
import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
import joblib
import os

LOG = logging.getLogger("ml_predictor")

class PlayerPerformancePredictor:
    """ML model for predicting player fantasy points"""
    
    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.feature_names = []
        self.model_path = '/app/ml_models/performance_predictor.joblib'
        self.scaler_path = '/app/ml_models/scaler.joblib'
        
        # Try to load existing model
        self._load_model()
    
    def train(self, historical_data: pd.DataFrame):
        """
        Train the ML model on historical data
        
        Expected columns:
        - player_name, role, team, opponent_team
        - fantamedia_last_5, fantamedia_season, appearances
        - goals_last_5, assists_last_5
        - opponent_difficulty (1-5)
        - home_away (0=away, 1=home)
        - target_points (actual points scored)
        """
        LOG.info(f"Training model on {len(historical_data)} samples...")
        
        # Feature engineering
        X = self._engineer_features(historical_data)
        y = historical_data['target_points'].values
        
        # Train-test split
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )
        
        # Scale features
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Train Random Forest
        self.model = RandomForestRegressor(
            n_estimators=100,
            max_depth=10,
            min_samples_split=10,
            random_state=42,
            n_jobs=-1
        )
        
        self.model.fit(X_train_scaled, y_train)
        
        # Evaluate
        train_score = self.model.score(X_train_scaled, y_train)
        test_score = self.model.score(X_test_scaled, y_test)
        
        LOG.info(f"Model trained - Train R²: {train_score:.3f}, Test R²: {test_score:.3f}")
        
        # Save model
        self._save_model()
        
        return {
            'train_score': train_score,
            'test_score': test_score,
            'feature_importance': self._get_feature_importance()
        }
    
    def predict(self, player_features: Dict) -> Dict:
        """
        Predict fantasy points for a single player
        
        Args:
            player_features: Dictionary with player stats and match context
        
        Returns:
            Prediction with confidence interval
        """
        if self.model is None:
            # If no trained model, use rule-based prediction for demo
            LOG.warning("No trained model available, using rule-based prediction")
            return self._rule_based_predict(player_features)
        
        # Convert to DataFrame for feature engineering
        df = pd.DataFrame([player_features])
        X = self._engineer_features(df)
        X_scaled = self.scaler.transform(X)
        
        # Predict
        prediction = float(self.model.predict(X_scaled)[0])
        
        # Calculate confidence from tree predictions
        tree_predictions = [float(tree.predict(X_scaled)[0]) for tree in self.model.estimators_]
        std = float(np.std(tree_predictions))
        confidence = float(max(0, min(100, 100 - (std * 10))))  # Convert to 0-100 scale
        
        return {
            'predicted_fantamedia': round(prediction, 2),
            'confidence': round(confidence / 100, 2),  # Return 0-1 scale
            'confidence_interval': {
                'lower': round(prediction - std, 2),
                'upper': round(prediction + std, 2)
            },
            'explanation': self._explain_prediction(player_features, prediction)
        }
    
    def predict_batch(self, players_data: List[Dict]) -> List[Dict]:
        """Predict for multiple players"""
        predictions = []
        
        for player_data in players_data:
            pred = self.predict(player_data)
            pred['player_name'] = player_data.get('player_name', 'Unknown')
            pred['role'] = player_data.get('role', 'C')
            predictions.append(pred)
        
        return sorted(predictions, key=lambda x: x['predicted_points'], reverse=True)
    
    def _engineer_features(self, df: pd.DataFrame) -> np.ndarray:
        """Extract and engineer features from raw data"""
        features = []
        self.feature_names = []
        
        # Recent form
        features.append(df['fantamedia_last_5'].values)
        self.feature_names.append('fantamedia_last_5')
        
        # Season average
        features.append(df['fantamedia_season'].values)
        self.feature_names.append('fantamedia_season')
        
        # Reliability (appearances)
        features.append(df['appearances'].values / 38)  # Normalize to 0-1
        self.feature_names.append('appearances_ratio')
        
        # Recent productivity
        features.append(df['goals_last_5'].values)
        self.feature_names.append('goals_last_5')
        
        features.append(df['assists_last_5'].values)
        self.feature_names.append('assists_last_5')
        
        # Opponent difficulty
        features.append(df['opponent_difficulty'].values)
        self.feature_names.append('opponent_difficulty')
        
        # Home/Away
        features.append(df['home_away'].values)
        self.feature_names.append('home_away')
        
        # Role encoding (one-hot)
        for role in ['P', 'D', 'C', 'A']:
            features.append((df['role'] == role).astype(int).values)
            self.feature_names.append(f'role_{role}')
        
        return np.column_stack(features)
    
    def _get_feature_importance(self) -> Dict[str, float]:
        """Get feature importance from trained model"""
        if self.model is None or not self.feature_names:
            return {}
        
        importances = self.model.feature_importances_
        return {
            name: round(float(importance), 3)
            for name, importance in zip(self.feature_names, importances)
        }
    
    def _explain_prediction(self, features: Dict, prediction: float) -> str:
        """Generate human-readable explanation"""
        explanations = []
        
        # Form analysis
        recent_form = features.get('fantamedia_last_5', 0)
        if recent_form > 7:
            explanations.append("🔥 In ottima forma recente")
        elif recent_form < 5.5:
            explanations.append("⚠️ Forma recente deludente")
        
        # Home advantage
        if features.get('home_away', 0) == 1:
            explanations.append("🏠 Gioca in casa (+0.5 punti)")
        
        # Opponent difficulty
        difficulty = features.get('opponent_difficulty', 3)
        if difficulty <= 2:
            explanations.append("✅ Avversario abbordabile")
        elif difficulty >= 4:
            explanations.append("🛡️ Avversario difficile")
        
        # Recent productivity
        goals = features.get('goals_last_5', 0)
        if goals >= 2:
            explanations.append(f"⚽ {goals} gol nelle ultime 5")
        
        return " | ".join(explanations) if explanations else "Predizione basata su dati storici"
    
    def _save_model(self):
        """Save trained model to disk"""
        try:
            os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
            joblib.dump(self.model, self.model_path)
            joblib.dump(self.scaler, self.scaler_path)
            LOG.info(f"Model saved to {self.model_path}")
        except Exception as e:
            LOG.error(f"Failed to save model: {e}")
    
    def _load_model(self):
        """Load pre-trained model from disk"""
        try:
            if os.path.exists(self.model_path) and os.path.exists(self.scaler_path):
                self.model = joblib.load(self.model_path)
                self.scaler = joblib.load(self.scaler_path)
                LOG.info("Pre-trained model loaded successfully")
        except Exception as e:
            LOG.warning(f"Could not load model: {e}")
            self.model = None
    
    def _rule_based_predict(self, features: Dict) -> Dict:
        """Simple rule-based prediction when ML model is not available"""
        # Extract features with defaults
        fantamedia = features.get('fantamedia', 6.0)
        age = features.get('age', 26)
        goals = features.get('goals', 0)
        assists = features.get('assists', 0)
        minutes = features.get('minutes_played', 1500)
        
        # Base prediction on fantamedia
        predicted = fantamedia
        
        # Adjust for age (peak performance 24-28)
        if 24 <= age <= 28:
            predicted += 0.3
        elif age < 22:
            predicted -= 0.2
        elif age > 32:
            predicted -= 0.4
        
        # Adjust for productivity
        if goals > 10:
            predicted += 0.5
        if assists > 5:
            predicted += 0.3
        
        # Adjust for playing time
        if minutes < 1000:
            predicted -= 0.5
        elif minutes > 2500:
            predicted += 0.3
        
        # Calculate confidence based on data availability
        confidence = min(0.85, 0.5 + (minutes / 3000) * 0.35)
        
        return {
            'predicted_fantamedia': round(predicted, 2),
            'confidence': round(confidence, 2),  # Already 0-1 scale
            'confidence_interval': {
                'lower': round(predicted - 1.0, 2),
                'upper': round(predicted + 1.0, 2)
            },
            'explanation': f"Predizione basata su fantamedia {fantamedia}, età {age}, {goals}G+{assists}A in {minutes}' giocati",
            'model_type': 'rule_based',
            'note': 'Modello ML in training - usando predizioni rule-based'
        }

class FixtureAnalyzer:
    """Analyze upcoming fixtures and difficulty"""
    
    def __init__(self):
        # Team strength ratings (1-5, 5=strongest)
        self.team_strength = {
            'Inter': 5, 'Napoli': 5, 'Juventus': 5, 'Milan': 4, 'Atalanta': 4,
            'Roma': 4, 'Lazio': 4, 'Fiorentina': 3, 'Bologna': 3, 'Torino': 3,
            'Udinese': 3, 'Genoa': 2, 'Lecce': 2, 'Verona': 2, 'Empoli': 2,
            'Como': 2, 'Parma': 2, 'Cagliari': 2, 'Monza': 2, 'Venezia': 1
        }
    
    def analyze_fixtures(self, team: str, next_n_matches: int = 5) -> Dict:
        """Analyze fixture difficulty for a team"""
        # TODO: Fetch real fixture data
        # For now, return mock data
        
        avg_difficulty = 3.0
        fixtures = []
        
        return {
            'team': team,
            'next_matches': next_n_matches,
            'avg_difficulty': avg_difficulty,
            'fixtures': fixtures,
            'recommendation': self._get_fixture_recommendation(avg_difficulty)
        }
    
    def _get_fixture_recommendation(self, difficulty: float) -> str:
        """Get recommendation based on fixture difficulty"""
        if difficulty <= 2.0:
            return "✅ Ottime partite in arrivo - Momento ideale per investire"
        elif difficulty <= 3.0:
            return "📊 Calendario nella media"
        elif difficulty <= 4.0:
            return "⚠️ Calendario impegnativo - Considera alternative"
        else:
            return "🛑 Calendario molto difficile - Evita per ora"

# Global predictor instance
_predictor_instance = None

def get_ml_predictor() -> PlayerPerformancePredictor:
    """Get or create ML predictor singleton"""
    global _predictor_instance
    if _predictor_instance is None:
        _predictor_instance = PlayerPerformancePredictor()
    return _predictor_instance
