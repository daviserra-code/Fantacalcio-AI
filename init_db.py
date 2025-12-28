#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
init_db.py - Database initialization script for FantaCalcio-AI

This script:
1. Creates all database tables
2. Sets up proper indexes
3. Creates an admin user for testing (optional)
4. Verifies database connectivity

Usage:
    python init_db.py
    python init_db.py --create-admin  # Also creates test admin user
"""

import os
import sys
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
LOG = logging.getLogger(__name__)

def init_database(create_admin=False):
    """Initialize the database with all required tables"""
    
    LOG.info("=" * 60)
    LOG.info("FantaCalcio-AI Database Initialization")
    LOG.info("=" * 60)
    
    # Check environment variables
    LOG.info("\n1️⃣  Checking environment variables...")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        LOG.error("❌ DATABASE_URL environment variable not set!")
        LOG.error("   Please set it in your .env file")
        LOG.error("   Example: DATABASE_URL=postgresql://user:pass@localhost:5432/fantacalcio_db")
        return False
    
    # Mask password in log
    safe_url = database_url.split('@')[1] if '@' in database_url else database_url
    LOG.info(f"   ✅ Database URL configured: ...@{safe_url}")
    
    session_secret = os.environ.get("SESSION_SECRET")
    if not session_secret:
        LOG.warning("   ⚠️  SESSION_SECRET not set - using development default")
    else:
        LOG.info(f"   ✅ Session secret configured ({len(session_secret)} chars)")
    
    # Import app and models
    LOG.info("\n2️⃣  Importing Flask application...")
    try:
        from app import app, db
        from models import User, UserLeague, Subscription, OAuth
        LOG.info("   ✅ Flask app and models imported successfully")
    except Exception as e:
        LOG.error(f"   ❌ Failed to import: {e}")
        return False
    
    # Test database connection
    LOG.info("\n3️⃣  Testing database connection...")
    try:
        with app.app_context():
            from sqlalchemy import text
            result = db.session.execute(text('SELECT version()')).fetchone()
            LOG.info(f"   ✅ Connected to PostgreSQL")
            LOG.info(f"      Version: {result[0][:50]}...")
    except Exception as e:
        LOG.error(f"   ❌ Database connection failed: {e}")
        LOG.error("   Make sure PostgreSQL is running and credentials are correct")
        return False
    
    # Create tables
    LOG.info("\n4️⃣  Creating database tables...")
    try:
        with app.app_context():
            # Drop all tables (use with caution!)
            # Uncomment the next line if you want to reset everything
            # db.drop_all()
            # LOG.info("   ⚠️  Dropped all existing tables")
            
            # Create all tables
            db.create_all()
            LOG.info("   ✅ Created tables:")
            LOG.info("      - users")
            LOG.info("      - user_leagues")
            LOG.info("      - subscriptions")
            LOG.info("      - o_auth (for OAuth tokens)")
            
            # Verify tables exist
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            LOG.info(f"\n   📋 Database contains {len(tables)} tables: {', '.join(tables)}")
    except Exception as e:
        LOG.error(f"   ❌ Table creation failed: {e}")
        return False
    
    # Create admin user if requested
    if create_admin:
        LOG.info("\n5️⃣  Creating admin user...")
        try:
            with app.app_context():
                # Check if admin already exists
                admin = User.query.filter_by(username='admin').first()
                if admin:
                    LOG.info("   ⚠️  Admin user already exists, skipping creation")
                else:
                    admin = User(
                        username='admin',
                        email='admin@fantacalcio.local',
                        first_name='Admin',
                        last_name='User',
                        is_active=True
                    )
                    admin.set_password('admin123')  # Change this in production!
                    
                    db.session.add(admin)
                    db.session.commit()
                    
                    LOG.info("   ✅ Admin user created:")
                    LOG.info("      Username: admin")
                    LOG.info("      Password: admin123")
                    LOG.info("      Email: admin@fantacalcio.local")
                    LOG.info("      ⚠️  CHANGE THIS PASSWORD IMMEDIATELY!")
        except Exception as e:
            LOG.error(f"   ❌ Admin user creation failed: {e}")
            return False
    
    # Create test user for development
    LOG.info("\n6️⃣  Creating test user...")
    try:
        with app.app_context():
            # Check if test user already exists
            test_user = User.query.filter_by(username='testuser').first()
            if test_user:
                LOG.info("   ⚠️  Test user already exists, skipping creation")
            else:
                test_user = User(
                    username='testuser',
                    email='test@fantacalcio.local',
                    first_name='Test',
                    last_name='User',
                    is_active=True
                )
                test_user.set_password('testpass123')
                
                db.session.add(test_user)
                db.session.commit()
                
                LOG.info("   ✅ Test user created:")
                LOG.info("      Username: testuser")
                LOG.info("      Password: testpass123")
                LOG.info("      Email: test@fantacalcio.local")
    except Exception as e:
        LOG.error(f"   ❌ Test user creation failed: {e}")
        # Don't fail the whole process for this
    
    # Create test league for test user
    LOG.info("\n7️⃣  Creating test league...")
    try:
        with app.app_context():
            test_user = User.query.filter_by(username='testuser').first()
            if test_user:
                # Check if league already exists
                existing_league = UserLeague.query.filter_by(
                    user_id=test_user.id,
                    league_name='Test League'
                ).first()
                
                if existing_league:
                    LOG.info("   ⚠️  Test league already exists, skipping creation")
                else:
                    import json
                    test_league_rules = {
                        "league_info": {
                            "name": "Test League",
                            "season": "2024-25",
                            "participants": 8
                        },
                        "budget_rules": {
                            "total_budget": 500,
                            "currency": "crediti"
                        }
                    }
                    
                    test_league = UserLeague(
                        user_id=test_user.id,
                        league_name='Test League',
                        league_data=json.dumps(test_league_rules)
                    )
                    
                    db.session.add(test_league)
                    db.session.commit()
                    
                    LOG.info("   ✅ Test league created for testuser")
    except Exception as e:
        LOG.error(f"   ❌ Test league creation failed: {e}")
        # Don't fail the whole process for this
    
    # Final verification
    LOG.info("\n8️⃣  Final verification...")
    try:
        with app.app_context():
            user_count = User.query.count()
            league_count = UserLeague.query.count()
            
            LOG.info(f"   ✅ Database initialized successfully!")
            LOG.info(f"      Users: {user_count}")
            LOG.info(f"      Leagues: {league_count}")
    except Exception as e:
        LOG.error(f"   ❌ Verification failed: {e}")
        return False
    
    LOG.info("\n" + "=" * 60)
    LOG.info("✅ Database initialization complete!")
    LOG.info("=" * 60)
    LOG.info("\nYou can now:")
    LOG.info("  1. Start the app: python main.py")
    LOG.info("  2. Visit: http://localhost:5000")
    LOG.info("  3. Register a new user or login with testuser/testpass123")
    LOG.info("\n")
    
    return True


def show_current_status():
    """Show current database status"""
    LOG.info("=" * 60)
    LOG.info("Current Database Status")
    LOG.info("=" * 60)
    
    try:
        from app import app, db
        from models import User, UserLeague, Subscription
        
        with app.app_context():
            from sqlalchemy import text
            
            # Connection info
            result = db.session.execute(text('SELECT version()')).fetchone()
            LOG.info(f"\n📊 PostgreSQL Version:")
            LOG.info(f"   {result[0][:60]}...")
            
            # Table counts
            user_count = User.query.count()
            league_count = UserLeague.query.count()
            subscription_count = Subscription.query.count()
            
            LOG.info(f"\n📈 Record Counts:")
            LOG.info(f"   Users: {user_count}")
            LOG.info(f"   Leagues: {league_count}")
            LOG.info(f"   Subscriptions: {subscription_count}")
            
            # List users
            if user_count > 0:
                LOG.info(f"\n👥 Users:")
                users = User.query.all()
                for user in users:
                    LOG.info(f"   - {user.username} ({user.email}) - Active: {user.is_active}")
            
            LOG.info("\n" + "=" * 60)
    except Exception as e:
        LOG.error(f"❌ Failed to get status: {e}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Initialize FantaCalcio-AI database')
    parser.add_argument('--create-admin', action='store_true', help='Create admin user')
    parser.add_argument('--status', action='store_true', help='Show current database status')
    parser.add_argument('--reset', action='store_true', help='Reset database (WARNING: deletes all data!)')
    
    args = parser.parse_args()
    
    if args.status:
        show_current_status()
    elif args.reset:
        response = input("⚠️  WARNING: This will DELETE ALL DATA. Are you sure? (yes/no): ")
        if response.lower() == 'yes':
            LOG.info("Resetting database...")
            from app import app, db
            with app.app_context():
                db.drop_all()
                LOG.info("✅ All tables dropped")
            init_database(create_admin=args.create_admin)
        else:
            LOG.info("Reset cancelled")
    else:
        success = init_database(create_admin=args.create_admin)
        sys.exit(0 if success else 1)
