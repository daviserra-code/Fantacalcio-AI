#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
setup_env.py - Interactive environment setup script

This script helps you configure your .env file by:
1. Checking for existing API keys in various locations
2. Prompting for missing credentials
3. Validating the configuration
"""

import os
import sys
import re
from pathlib import Path

def print_header(text):
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70 + "\n")

def print_step(num, text):
    print(f"\n{num}️⃣  {text}")
    print("-" * 60)

def read_env_file(path):
    """Read existing .env file and return dict of values"""
    env_vars = {}
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
    return env_vars

def check_existing_secrets():
    """Check for existing API keys in various locations"""
    print_step(1, "Searching for existing API keys...")
    
    found_keys = {}
    
    # Check if .env already exists
    env_path = Path('.env')
    if env_path.exists():
        print("✅ Found existing .env file")
        env_vars = read_env_file('.env')
        
        # Check each key
        for key in ['OPENAI_API_KEY', 'HUGGINGFACE_TOKEN', 'STRIPE_SECRET_KEY', 'APIFY_API_TOKEN']:
            value = env_vars.get(key, '')
            if value and value not in ['', 'your_openai_key_here', 'your_huggingface_token_here']:
                found_keys[key] = value
                print(f"   ✅ {key}: {value[:15]}...")
    
    return found_keys

def get_user_input(prompt, default='', required=False, masked=False):
    """Get user input with optional default and masking"""
    if default:
        prompt_text = f"{prompt} [{default}]: "
    else:
        prompt_text = f"{prompt}: "
    
    value = input(prompt_text).strip()
    
    if not value:
        value = default
    
    if required and not value:
        print("❌ This field is required!")
        return get_user_input(prompt, default, required, masked)
    
    return value

def generate_session_secret():
    """Generate a secure session secret"""
    import secrets
    return secrets.token_hex(32)

def validate_api_key(key, value):
    """Basic validation for API keys"""
    patterns = {
        'OPENAI_API_KEY': r'^sk-[a-zA-Z0-9\-_]+$',
        'HUGGINGFACE_TOKEN': r'^hf_[a-zA-Z0-9]+$',
        'STRIPE_SECRET_KEY': r'^sk_(test|live)_[a-zA-Z0-9]+$',
    }
    
    if key in patterns and value:
        return bool(re.match(patterns[key], value))
    return True

def create_env_file(config):
    """Create .env file with provided configuration"""
    template = f"""# FantaCalcio-AI Environment Configuration
# Generated: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

# ==================== DATABASE ====================
DATABASE_URL={config['DATABASE_URL']}
DB_PASSWORD={config['DB_PASSWORD']}

# ==================== SECURITY ====================
SESSION_SECRET={config['SESSION_SECRET']}

# ==================== AI SERVICES ====================
# OpenAI (REQUIRED)
OPENAI_API_KEY={config['OPENAI_API_KEY']}
OPENAI_MODEL={config['OPENAI_MODEL']}
OPENAI_TEMPERATURE={config['OPENAI_TEMPERATURE']}
OPENAI_MAX_TOKENS={config['OPENAI_MAX_TOKENS']}

# HuggingFace (REQUIRED)
HUGGINGFACE_TOKEN={config['HUGGINGFACE_TOKEN']}
HF_TOKEN={config['HUGGINGFACE_TOKEN']}

# ==================== STRIPE (OPTIONAL) ====================
STRIPE_SECRET_KEY={config.get('STRIPE_SECRET_KEY', '')}
STRIPE_PUBLISHABLE_KEY={config.get('STRIPE_PUBLISHABLE_KEY', '')}
STRIPE_WEBHOOK_SECRET={config.get('STRIPE_WEBHOOK_SECRET', '')}

# ==================== WEB SCRAPING (OPTIONAL) ====================
APIFY_API_TOKEN={config.get('APIFY_API_TOKEN', '')}

# ==================== APPLICATION SETTINGS ====================
ENVIRONMENT={config['ENVIRONMENT']}
LOG_LEVEL={config['LOG_LEVEL']}
HOST={config['HOST']}
PORT={config['PORT']}
APP_PORT={config['APP_PORT']}

# ==================== DATA PATHS ====================
ROSTER_JSON_PATH={config['ROSTER_JSON_PATH']}
CHROMA_PATH={config['CHROMA_PATH']}
CHROMA_DB_PATH={config['CHROMA_DB_PATH']}
CHROMA_COLLECTION_NAME={config['CHROMA_COLLECTION_NAME']}
AGE_INDEX_PATH={config['AGE_INDEX_PATH']}
AGE_OVERRIDES_PATH={config['AGE_OVERRIDES_PATH']}

# ==================== FEATURE FLAGS ====================
ENABLE_WEB_FALLBACK={config['ENABLE_WEB_FALLBACK']}
SEASON_FILTER={config['SEASON_FILTER']}
REF_YEAR={config['REF_YEAR']}

# ==================== ETL CONFIGURATION ====================
ETL_CMD={config['ETL_CMD']}
"""
    
    with open('.env', 'w', encoding='utf-8') as f:
        f.write(template)
    
    print("✅ .env file created successfully!")

def main():
    print_header("FantaCalcio-AI Environment Setup")
    
    # Check for existing secrets
    existing_keys = check_existing_secrets()
    
    # Prepare configuration
    config = {
        'DATABASE_URL': 'postgresql://fantacalcio_user:fantacalcio2025secure!@postgres:5432/fantacalcio_db',
        'DB_PASSWORD': 'fantacalcio2025secure!',
        'SESSION_SECRET': generate_session_secret(),
        'OPENAI_MODEL': 'gpt-4o-mini',
        'OPENAI_TEMPERATURE': '0.20',
        'OPENAI_MAX_TOKENS': '600',
        'ENVIRONMENT': 'development',
        'LOG_LEVEL': 'INFO',
        'HOST': '0.0.0.0',
        'PORT': '5000',
        'APP_PORT': '5000',
        'ROSTER_JSON_PATH': '/app/season_roster.json',
        'CHROMA_PATH': '/app/chroma_db',
        'CHROMA_DB_PATH': '/app/chroma_db',
        'CHROMA_COLLECTION_NAME': 'fantacalcio_knowledge',
        'AGE_INDEX_PATH': '/app/data/age_index.cleaned.json',
        'AGE_OVERRIDES_PATH': '/app/data/age_overrides.json',
        'ENABLE_WEB_FALLBACK': 'false',
        'SEASON_FILTER': '2024-25',
        'REF_YEAR': '2025',
        'ETL_CMD': 'python etl_build_roster.py',
    }
    
    # Get required API keys
    print_step(2, "Configure API Keys")
    
    # OpenAI
    openai_key = existing_keys.get('OPENAI_API_KEY', '')
    if openai_key:
        use_existing = get_user_input(f"Use existing OpenAI key ({openai_key[:15]}...)? (y/n)", 'y')
        if use_existing.lower() != 'y':
            openai_key = ''
    
    if not openai_key:
        print("\n📝 OpenAI API Key (REQUIRED)")
        print("   Get from: https://platform.openai.com/api-keys")
        openai_key = get_user_input("Enter OpenAI API key", required=True)
    
    config['OPENAI_API_KEY'] = openai_key
    
    # HuggingFace
    hf_token = existing_keys.get('HUGGINGFACE_TOKEN', '')
    if hf_token:
        use_existing = get_user_input(f"Use existing HuggingFace token ({hf_token[:15]}...)? (y/n)", 'y')
        if use_existing.lower() != 'y':
            hf_token = ''
    
    if not hf_token:
        print("\n📝 HuggingFace Token (REQUIRED)")
        print("   Get from: https://huggingface.co/settings/tokens")
        hf_token = get_user_input("Enter HuggingFace token", required=True)
    
    config['HUGGINGFACE_TOKEN'] = hf_token
    
    # Optional: Stripe
    print_step(3, "Optional Services")
    setup_stripe = get_user_input("Configure Stripe for Pro subscriptions? (y/n)", 'n')
    if setup_stripe.lower() == 'y':
        config['STRIPE_SECRET_KEY'] = get_user_input("Stripe Secret Key")
        config['STRIPE_PUBLISHABLE_KEY'] = get_user_input("Stripe Publishable Key")
        config['STRIPE_WEBHOOK_SECRET'] = get_user_input("Stripe Webhook Secret")
    
    # Optional: Apify
    setup_apify = get_user_input("Configure Apify for web scraping? (y/n)", 'n')
    if setup_apify.lower() == 'y':
        config['APIFY_API_TOKEN'] = get_user_input("Apify API Token")
    
    # Create .env file
    print_step(4, "Creating .env file")
    create_env_file(config)
    
    # Summary
    print_header("Setup Complete! ✅")
    print("Your .env file has been created with the following:")
    print(f"  ✅ SESSION_SECRET: Generated securely")
    print(f"  ✅ OPENAI_API_KEY: {config['OPENAI_API_KEY'][:15]}...")
    print(f"  ✅ HUGGINGFACE_TOKEN: {config['HUGGINGFACE_TOKEN'][:15]}...")
    print(f"  ✅ Database: Pre-configured for Docker")
    
    print("\n🚀 Next Steps:")
    print("  1. Review .env file if needed: notepad .env")
    print("  2. Start Docker: docker-compose up -d")
    print("  3. Initialize database: docker-compose exec app python init_db.py")
    print("  4. Visit: http://localhost:5000")
    print("\n")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Setup cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        sys.exit(1)
