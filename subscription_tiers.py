# subscription_tiers.py - Enhanced subscription tier management
import logging
from datetime import datetime, timedelta
from typing import Optional
from flask_login import current_user
from functools import wraps
from flask import jsonify, request

LOG = logging.getLogger("subscription_tiers")

class SubscriptionTier:
    """Subscription tier definitions"""
    
    FREE = {
        'name': 'Free',
        'price': 0,
        'queries_per_hour': 10,
        'queries_per_day': 50,
        'features': {
            'basic_chat': True,
            'player_search': True,
            'basic_stats': True,
            'formation_suggestions': False,
            'advanced_analytics': False,
            'live_tracking': False,
            'historical_data': False,
            'ml_predictions': False,
            'priority_support': False,
            'league_chat': False,
            'export_data': False,
            'custom_rules': False
        }
    }
    
    PRO = {
        'name': 'Pro',
        'price': 9.99,
        'currency': 'EUR',
        'queries_per_hour': None,  # Unlimited
        'queries_per_day': None,
        'features': {
            'basic_chat': True,
            'player_search': True,
            'basic_stats': True,
            'formation_suggestions': True,
            'advanced_analytics': True,
            'live_tracking': True,
            'historical_data': True,
            'ml_predictions': False,
            'priority_support': False,
            'league_chat': True,
            'export_data': True,
            'custom_rules': True
        }
    }
    
    ELITE = {
        'name': 'Elite',
        'price': 19.99,
        'currency': 'EUR',
        'queries_per_hour': None,
        'queries_per_day': None,
        'features': {
            'basic_chat': True,
            'player_search': True,
            'basic_stats': True,
            'formation_suggestions': True,
            'advanced_analytics': True,
            'live_tracking': True,
            'historical_data': True,
            'ml_predictions': True,
            'priority_support': True,
            'league_chat': True,
            'export_data': True,
            'custom_rules': True,
            'api_access': True,
            'white_label': True
        }
    }

def get_user_tier() -> dict:
    """Get current user's subscription tier"""
    if not current_user.is_authenticated:
        return SubscriptionTier.FREE
    
    # Grant Elite access to admin users
    if hasattr(current_user, 'is_admin') and current_user.is_admin:
        return SubscriptionTier.ELITE
    
    if current_user.is_pro:
        # For testing/admin: if email is admin, grant Elite access
        if hasattr(current_user, 'email') and current_user.email == 'admin@fantacalcio.ai':
            return SubscriptionTier.ELITE
        
        # All other pro users get PRO tier
        return SubscriptionTier.PRO
    
    return SubscriptionTier.FREE

def has_feature(feature_name: str) -> bool:
    """Check if current user has access to a feature"""
    tier = get_user_tier()
    return tier['features'].get(feature_name, False)

def require_feature(feature_name: str, message: str = None):
    """Decorator to require specific feature access"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not has_feature(feature_name):
                tier = get_user_tier()
                default_message = f"Questa funzione richiede un abbonamento {SubscriptionTier.PRO['name']} o superiore."
                
                return jsonify({
                    'error': 'feature_not_available',
                    'message': message or default_message,
                    'current_tier': tier['name'],
                    'required_feature': feature_name,
                    'upgrade_url': '/upgrade'
                }), 403
            
            return func(*args, **kwargs)
        return wrapper
    return decorator

def check_rate_limit() -> tuple[bool, Optional[dict]]:
    """Check if user is within rate limits"""
    tier = get_user_tier()
    
    # Pro/Elite users have unlimited queries
    if tier['name'] in ['Pro', 'Elite']:
        return True, None
    
    # Free tier rate limiting
    # This is a simplified version - in production, use Redis for tracking
    # For now, the existing rate_limiter.py handles this
    
    hourly_limit = tier['queries_per_hour']
    daily_limit = tier['queries_per_day']
    
    return True, {
        'hourly_limit': hourly_limit,
        'daily_limit': daily_limit,
        'remaining_hourly': hourly_limit,  # TODO: Track actual usage
        'remaining_daily': daily_limit
    }

def get_tier_comparison() -> list:
    """Get comparison of all tiers for pricing page"""
    return [
        {
            'tier': 'Free',
            'price': '€0',
            'period': 'sempre gratis',
            'features': [
                '10 domande all\'ora',
                'Ricerca giocatori base',
                'Statistiche essenziali',
                'Rosa completa Serie A'
            ],
            'limitations': [
                'No formazioni AI',
                'No tracking live',
                'No dati storici'
            ]
        },
        {
            'tier': 'Pro',
            'price': '€9.99',
            'period': 'al mese',
            'popular': True,
            'features': [
                '✨ Domande illimitate',
                '🤖 Formazioni AI ottimizzate',
                '📊 Analytics avanzate',
                '📈 Tracking partite live',
                '📜 Dati storici 5 anni',
                '💬 Chat leghe private',
                '📥 Export dati CSV/PDF',
                '⚙️ Regole personalizzate'
            ],
            'limitations': []
        },
        {
            'tier': 'Elite',
            'price': '€19.99',
            'period': 'al mese',
            'features': [
                '🌟 Tutto di Pro, più:',
                '🧠 Predizioni ML avanzate',
                '🎯 Raccomandazioni personalizzate',
                '⚡ Supporto prioritario',
                '🔌 Accesso API',
                '🏷️ White-label opzionale',
                '📞 Consulenza telefonica'
            ],
            'limitations': []
        }
    ]

def track_feature_usage(feature_name: str):
    """Track feature usage for analytics"""
    if not current_user.is_authenticated:
        return
    
    # TODO: Implement feature usage tracking in database
    # This helps understand which features drive conversions
    LOG.info(f"Feature usage: {feature_name} by user {current_user.id} (tier: {get_user_tier()['name']})")

def send_upgrade_prompt(feature_name: str) -> dict:
    """Generate upgrade prompt for locked features"""
    tier = get_user_tier()
    
    prompts = {
        'formation_suggestions': {
            'title': '🤖 Formazioni AI non disponibili',
            'message': 'Ottieni formazioni ottimizzate con intelligenza artificiale!',
            'benefit': 'L\'AI analizza 557 giocatori e trova la miglior combinazione per il tuo budget.',
            'cta': 'Passa a Pro per sbloccare'
        },
        'live_tracking': {
            'title': '📈 Live Match Tracking',
            'message': 'Segui le partite in tempo reale con aggiornamenti istantanei!',
            'benefit': 'Vedi i punti fantacalcio dei tuoi giocatori minuto per minuto.',
            'cta': 'Attiva il tracking live con Pro'
        },
        'ml_predictions': {
            'title': '🧠 Predizioni Machine Learning',
            'message': 'Predizioni basate su 5 anni di dati storici!',
            'benefit': 'Scopri quali giocatori performeranno meglio nelle prossime giornate.',
            'cta': 'Passa a Elite per le predizioni ML'
        }
    }
    
    return prompts.get(feature_name, {
        'title': 'Feature Pro/Elite',
        'message': 'Questa funzione richiede un abbonamento Pro o Elite.',
        'cta': 'Scopri i vantaggi'
    })
