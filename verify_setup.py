#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
verify_setup.py - Verify FantaCalcio-AI setup and dependencies

Checks:
- Environment variables
- Database connectivity
- Python dependencies
- Required files and directories
- API keys validity
"""

import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
LOG = logging.getLogger(__name__)

def check_env_vars():
    """Check required environment variables"""
    LOG.info("\n" + "=" * 60)
    LOG.info("🔍 Checking Environment Variables")
    LOG.info("=" * 60)
    
    required_vars = {
        'DATABASE_URL': 'Database connection string',
        'SESSION_SECRET': 'Session security key',
        'OPENAI_API_KEY': 'OpenAI API access',
    }
    
    optional_vars = {
        'HUGGINGFACE_TOKEN': 'HuggingFace embeddings',
        'STRIPE_SECRET_KEY': 'Stripe payments (Pro features)',
        'APIFY_API_TOKEN': 'Apify web scraping',
    }
    
    issues = []
    
    # Check required
    for var, description in required_vars.items():
        value = os.environ.get(var)
        if not value:
            LOG.error(f"❌ {var}: Missing - {description}")
            issues.append(var)
        elif var == 'SESSION_SECRET' and len(value) < 16:
            LOG.warning(f"⚠️  {var}: Too short (should be 32+ chars)")
            issues.append(var)
        else:
            masked = value[:8] + '...' if len(value) > 8 else '***'
            LOG.info(f"✅ {var}: Set ({masked})")
    
    # Check optional
    LOG.info("\nOptional variables:")
    for var, description in optional_vars.items():
        value = os.environ.get(var)
        if value:
            masked = value[:8] + '...' if len(value) > 8 else '***'
            LOG.info(f"✅ {var}: Set ({masked}) - {description}")
        else:
            LOG.info(f"⚪ {var}: Not set - {description}")
    
    return len(issues) == 0


def check_database():
    """Check database connectivity"""
    LOG.info("\n" + "=" * 60)
    LOG.info("🗄️  Checking Database Connection")
    LOG.info("=" * 60)
    
    try:
        from app import app, db
        from sqlalchemy import text
        
        with app.app_context():
            # Test connection
            result = db.session.execute(text('SELECT version()')).fetchone()
            LOG.info(f"✅ Connected to PostgreSQL")
            LOG.info(f"   Version: {result[0][:60]}...")
            
            # Check tables
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            
            required_tables = ['users', 'user_leagues', 'subscriptions']
            missing_tables = [t for t in required_tables if t not in tables]
            
            if missing_tables:
                LOG.warning(f"⚠️  Missing tables: {', '.join(missing_tables)}")
                LOG.info("   Run: python init_db.py")
                return False
            else:
                LOG.info(f"✅ All required tables exist: {', '.join(required_tables)}")
            
            # Check record counts
            from models import User, UserLeague
            user_count = User.query.count()
            league_count = UserLeague.query.count()
            
            LOG.info(f"📊 Current data:")
            LOG.info(f"   Users: {user_count}")
            LOG.info(f"   Leagues: {league_count}")
            
            return True
            
    except ImportError as e:
        LOG.error(f"❌ Import error: {e}")
        LOG.error("   Check if all dependencies are installed")
        return False
    except Exception as e:
        LOG.error(f"❌ Database connection failed: {e}")
        LOG.error("   Check DATABASE_URL and ensure PostgreSQL is running")
        return False


def check_dependencies():
    """Check Python dependencies"""
    LOG.info("\n" + "=" * 60)
    LOG.info("📦 Checking Python Dependencies")
    LOG.info("=" * 60)
    
    required_packages = [
        ('flask', 'Flask'),
        ('sqlalchemy', 'SQLAlchemy'),
        ('openai', 'OpenAI'),
        ('chromadb', 'ChromaDB'),
        ('sentence_transformers', 'Sentence Transformers'),
    ]
    
    missing = []
    
    for module_name, package_name in required_packages:
        try:
            __import__(module_name)
            LOG.info(f"✅ {package_name}")
        except ImportError:
            LOG.error(f"❌ {package_name} not installed")
            missing.append(package_name)
    
    if missing:
        LOG.error(f"\nMissing packages: {', '.join(missing)}")
        LOG.error("Run: pip install -r requirements.txt")
        return False
    
    return True


def check_files():
    """Check required files and directories"""
    LOG.info("\n" + "=" * 60)
    LOG.info("📁 Checking Files and Directories")
    LOG.info("=" * 60)
    
    required_dirs = [
        ('chroma_db', 'ChromaDB vector store'),
        ('cache', 'Cache directory'),
        ('data', 'Data files'),
        ('templates', 'HTML templates'),
        ('static', 'Static assets'),
    ]
    
    important_files = [
        ('season_roster.json', 'Player roster database', False),
        ('requirements.txt', 'Python dependencies', True),
        ('config.py', 'Configuration', True),
        ('app.py', 'Flask application', True),
        ('main.py', 'Entry point', True),
    ]
    
    # Check directories
    for dir_name, description in required_dirs:
        if os.path.isdir(dir_name):
            LOG.info(f"✅ {dir_name}/ - {description}")
        else:
            LOG.warning(f"⚠️  {dir_name}/ missing - {description}")
            try:
                os.makedirs(dir_name, exist_ok=True)
                LOG.info(f"   Created {dir_name}/")
            except Exception as e:
                LOG.error(f"   Failed to create: {e}")
    
    # Check files
    LOG.info("\nImportant files:")
    missing_critical = []
    
    for file_name, description, critical in important_files:
        if os.path.isfile(file_name):
            size = os.path.getsize(file_name)
            LOG.info(f"✅ {file_name} - {description} ({size:,} bytes)")
        else:
            symbol = "❌" if critical else "⚪"
            LOG.warning(f"{symbol} {file_name} - {description} (missing)")
            if critical:
                missing_critical.append(file_name)
    
    if missing_critical:
        LOG.error(f"\nCritical files missing: {', '.join(missing_critical)}")
        return False
    
    return True


def check_chromadb():
    """Check ChromaDB setup"""
    LOG.info("\n" + "=" * 60)
    LOG.info("🧠 Checking ChromaDB")
    LOG.info("=" * 60)
    
    try:
        from knowledge_manager import KnowledgeManager
        
        km = KnowledgeManager()
        
        if hasattr(km, 'collection'):
            count = km.collection.count()
            LOG.info(f"✅ ChromaDB initialized")
            LOG.info(f"   Documents: {count}")
            
            if count == 0:
                LOG.warning("⚠️  ChromaDB is empty")
                LOG.info("   Run: python ingest_cli.py (to populate knowledge base)")
        else:
            LOG.warning("⚠️  ChromaDB collection not initialized")
            return False
        
        return True
        
    except Exception as e:
        LOG.error(f"❌ ChromaDB error: {e}")
        return False


def check_apis():
    """Check API keys validity"""
    LOG.info("\n" + "=" * 60)
    LOG.info("🔑 Checking API Keys")
    LOG.info("=" * 60)
    
    # Check OpenAI
    openai_key = os.environ.get('OPENAI_API_KEY')
    if openai_key and openai_key.startswith('sk-'):
        LOG.info("✅ OpenAI API key format valid")
    elif openai_key:
        LOG.warning("⚠️  OpenAI API key format unusual")
    else:
        LOG.error("❌ OpenAI API key not set")
    
    # Check HuggingFace
    hf_token = os.environ.get('HUGGINGFACE_TOKEN')
    if hf_token and hf_token.startswith('hf_'):
        LOG.info("✅ HuggingFace token format valid")
    elif hf_token:
        LOG.warning("⚠️  HuggingFace token format unusual")
    else:
        LOG.info("⚪ HuggingFace token not set (optional)")
    
    # Check Stripe
    stripe_key = os.environ.get('STRIPE_SECRET_KEY')
    if stripe_key:
        if stripe_key.startswith('sk_test_'):
            LOG.info("✅ Stripe key set (TEST mode)")
        elif stripe_key.startswith('sk_live_'):
            LOG.info("✅ Stripe key set (LIVE mode)")
        else:
            LOG.warning("⚠️  Stripe key format unusual")
    else:
        LOG.info("⚪ Stripe key not set (Pro features disabled)")
    
    return True


def main():
    """Run all verification checks"""
    LOG.info("\n" + "=" * 70)
    LOG.info("🔧 FantaCalcio-AI Setup Verification")
    LOG.info("=" * 70)
    
    checks = [
        ("Environment Variables", check_env_vars),
        ("Python Dependencies", check_dependencies),
        ("Files and Directories", check_files),
        ("Database Connection", check_database),
        ("ChromaDB", check_chromadb),
        ("API Keys", check_apis),
    ]
    
    results = {}
    
    for name, check_func in checks:
        try:
            results[name] = check_func()
        except Exception as e:
            LOG.error(f"❌ {name} check failed with error: {e}")
            results[name] = False
    
    # Summary
    LOG.info("\n" + "=" * 70)
    LOG.info("📋 Verification Summary")
    LOG.info("=" * 70)
    
    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        LOG.info(f"{status} - {name}")
    
    all_passed = all(results.values())
    
    LOG.info("\n" + "=" * 70)
    if all_passed:
        LOG.info("🎉 All checks passed! You're ready to go!")
        LOG.info("=" * 70)
        LOG.info("\nNext steps:")
        LOG.info("  1. Start the app: python main.py")
        LOG.info("  2. Visit: http://localhost:5000")
        LOG.info("  3. Register or login with test account")
        LOG.info("\nOr with Docker:")
        LOG.info("  1. docker-compose up -d")
        LOG.info("  2. Visit: http://localhost:5000")
    else:
        LOG.error("⚠️  Some checks failed. Please fix the issues above.")
        LOG.info("=" * 70)
        LOG.info("\nCommon fixes:")
        LOG.info("  - Missing env vars: Copy .env.example to .env and configure")
        LOG.info("  - Database issues: Run python init_db.py")
        LOG.info("  - Missing packages: pip install -r requirements.txt")
    
    LOG.info("")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
