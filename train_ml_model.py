# train_ml_model.py - Train ML model from season roster data
import json
import logging
import pandas as pd
import numpy as np
from ml_predictor import PlayerPerformancePredictor

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)

def generate_training_data_from_roster():
    """
    Generate synthetic training data from current season roster
    This simulates historical match performance for training
    """
    LOG.info("Loading season roster...")
    
    with open('season_roster.json', 'r', encoding='utf-8') as f:
        roster = json.load(f)
    
    training_samples = []
    
    for player in roster:
        # Skip players with insufficient data
        if not player.get('fantamedia') or player['fantamedia'] == 0:
            continue
        
        # Get player stats
        name = player['name']
        role = player['role']
        team = player['team']
        fantamedia = player['fantamedia']
        price = player.get('price', 10)
        birth_year = player.get('birth_year', 1995)
        age = 2025 - birth_year
        
        # Estimate goals/assists from fantamedia and role
        if role == 'A':
            goals = int(fantamedia / 20)  # Attackers: ~1 goal per 20 fantamedia
            assists = int(fantamedia / 40)
        elif role == 'C':
            goals = int(fantamedia / 40)
            assists = int(fantamedia / 30)
        elif role == 'D':
            goals = int(fantamedia / 60)
            assists = int(fantamedia / 50)
        else:  # P
            goals = 0
            assists = 0
        
        # Simulate appearances (estimate based on price)
        appearances = min(38, max(10, int(price * 2)))
        
        # Generate 4-6 synthetic match samples per player
        num_samples = np.random.randint(4, 7)
        
        for _ in range(num_samples):
            # Add realistic variance to fantamedia
            match_fantamedia = fantamedia + np.random.normal(0, 1.5)
            match_fantamedia = max(4.0, min(10.0, match_fantamedia))  # Clamp to realistic range
            
            # Simulate match context
            sample = {
                'player_name': name,
                'role': role,
                'team': team,
                'fantamedia_last_5': fantamedia + np.random.normal(0, 0.8),
                'fantamedia_season': fantamedia,
                'appearances': appearances,
                'goals_last_5': max(0, int(goals * 0.3 + np.random.normal(0, 1))),
                'assists_last_5': max(0, int(assists * 0.3 + np.random.normal(0, 0.8))),
                'opponent_difficulty': np.random.randint(1, 6),  # 1-5 scale
                'home_away': np.random.randint(0, 2),  # 0=away, 1=home
                'target_points': match_fantamedia  # What we want to predict
            }
            
            training_samples.append(sample)
    
    LOG.info(f"Generated {len(training_samples)} training samples from {len(roster)} players")
    
    return pd.DataFrame(training_samples)

def train_model():
    """Train the ML model"""
    LOG.info("Starting ML model training...")
    
    # Generate training data
    df = generate_training_data_from_roster()
    
    if len(df) < 100:
        LOG.error("Insufficient training data! Need at least 100 samples")
        return False
    
    LOG.info(f"Training data shape: {df.shape}")
    LOG.info(f"Target stats - Mean: {df['target_points'].mean():.2f}, Std: {df['target_points'].std():.2f}")
    LOG.info(f"Role distribution:\n{df['role'].value_counts()}")
    
    # Initialize and train predictor
    predictor = PlayerPerformancePredictor()
    
    try:
        results = predictor.train(df)
        
        LOG.info("=" * 60)
        LOG.info("✅ Model training completed!")
        LOG.info(f"Train R² Score: {results['train_score']:.3f}")
        LOG.info(f"Test R² Score: {results['test_score']:.3f}")
        LOG.info("\nTop 5 most important features:")
        
        feature_importance = results['feature_importance']
        sorted_features = sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)
        
        for feature, importance in sorted_features[:5]:
            LOG.info(f"  - {feature}: {importance:.3f}")
        
        LOG.info("=" * 60)
        
        # Test prediction
        LOG.info("\n🧪 Testing prediction on sample player...")
        test_sample = {
            'fantamedia_last_5': 6.5,
            'fantamedia_season': 6.8,
            'appearances': 20,
            'goals_last_5': 2,
            'assists_last_5': 1,
            'opponent_difficulty': 3,
            'home_away': 1,
            'role': 'A'
        }
        
        prediction = predictor.predict(test_sample)
        LOG.info(f"Sample prediction: {prediction}")
        
        return True
        
    except Exception as e:
        LOG.error(f"Training failed: {e}", exc_info=True)
        return False

if __name__ == '__main__':
    success = train_model()
    
    if success:
        print("\n✅ Model trained and saved successfully!")
        print("📁 Model saved to: /app/ml_models/performance_predictor.joblib")
        print("\nYou can now use ML Predictions in the app!")
    else:
        print("\n❌ Training failed. Check logs above.")
