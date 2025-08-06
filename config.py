
import os
from typing import Dict, Any

class AppConfig:
    """Centralized configuration management"""
    
    def __init__(self):
        self.config = self._load_default_config()
        self._load_env_overrides()
    
    def _load_default_config(self) -> Dict[str, Any]:
        return {
            # AI Configuration
            'openai_model_primary': 'gpt-4',
            'openai_model_secondary': 'gpt-4o-mini',
            'max_tokens': 500,
            'temperature': 0.3,
            'response_cache_size': 50,
            
            # Rate Limiting
            'rate_limit_requests': 60,
            'rate_limit_window': 60,
            
            # Search and Analytics
            'search_cache_expiry': 300,
            'max_search_results': 20,
            'max_conversation_history': 6,
            
            # Features
            'enable_voice_input': True,
            'enable_real_time_updates': True,
            'enable_advanced_analytics': True,
            'enable_fixture_tracking': True,
            
            # League Defaults
            'default_league_type': 'Classic',
            'default_participants': 8,
            'default_budget': 500,
            
            # UI/UX
            'theme': 'dark',
            'language': 'it',
            'mobile_optimized': True
        }
    
    def _load_env_overrides(self):
        """Load configuration overrides from environment variables"""
        env_mappings = {
            'OPENAI_MODEL_PRIMARY': 'openai_model_primary',
            'OPENAI_MODEL_SECONDARY': 'openai_model_secondary',
            'MAX_TOKENS': ('max_tokens', int),
            'TEMPERATURE': ('temperature', float),
            'RATE_LIMIT_REQUESTS': ('rate_limit_requests', int),
            'DEFAULT_LEAGUE_TYPE': 'default_league_type',
            'ENABLE_VOICE_INPUT': ('enable_voice_input', bool),
            'THEME': 'theme'
        }
        
        for env_key, config_key in env_mappings.items():
            env_value = os.environ.get(env_key)
            if env_value:
                if isinstance(config_key, tuple):
                    key, converter = config_key
                    try:
                        self.config[key] = converter(env_value)
                    except ValueError:
                        continue
                else:
                    self.config[config_key] = env_value
    
    def get(self, key: str, default=None):
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any):
        self.config[key] = value
    
    def to_dict(self) -> Dict[str, Any]:
        return self.config.copy()

# Global config instance
app_config = AppConfig()

