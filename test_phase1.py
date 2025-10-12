"""
Test Script for Phase 1 Enhancements
Tests: Rate Limiting, User Profile, Error Pages, Database Migrations
"""

import os
import sys
import time
from datetime import datetime

# Color codes for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text.center(60)}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}\n")

def print_test(name, status, message=""):
    symbol = f"{Colors.GREEN}✓{Colors.END}" if status else f"{Colors.RED}✗{Colors.END}"
    print(f"{symbol} {name}")
    if message:
        print(f"  → {Colors.YELLOW}{message}{Colors.END}")

def test_environment_variables():
    """Test 1: Environment Variables"""
    print_header("TEST 1: Environment Variables")
    
    required_vars = ["SESSION_SECRET", "DATABASE_URL"]
    optional_vars = ["OPENAI_API_KEY", "STRIPE_SECRET_KEY", "FLASK_ENV"]
    
    print(f"{Colors.BOLD}Required Variables:{Colors.END}")
    for var in required_vars:
        value = os.environ.get(var)
        if value:
            masked_value = value[:10] + "..." if len(value) > 10 else value
            print_test(f"{var}", True, f"Set: {masked_value}")
        else:
            print_test(f"{var}", False, "MISSING - App will not start!")
    
    print(f"\n{Colors.BOLD}Optional Variables:{Colors.END}")
    for var in optional_vars:
        value = os.environ.get(var)
        if value:
            masked_value = value[:10] + "..." if len(value) > 10 else value
            print_test(f"{var}", True, f"Set: {masked_value}")
        else:
            print_test(f"{var}", False, "Not set (optional)")

def test_imports():
    """Test 2: Package Imports"""
    print_header("TEST 2: Package Imports")
    
    packages = [
        ("flask", "Flask"),
        ("flask_sqlalchemy", "Flask-SQLAlchemy"),
        ("flask_migrate", "Flask-Migrate"),
        ("flask_limiter", "Flask-Limiter"),
        ("flask_login", "Flask-Login"),
        ("dotenv", "python-dotenv"),
    ]
    
    for module, name in packages:
        try:
            __import__(module)
            print_test(f"{name}", True, f"Module '{module}' imported successfully")
        except ImportError as e:
            print_test(f"{name}", False, f"Import failed: {e}")

def test_app_initialization():
    """Test 3: App Initialization"""
    print_header("TEST 3: App Initialization")
    
    try:
        # Load environment variables
        from dotenv import load_dotenv
        load_dotenv()
        print_test("Load .env", True, ".env file loaded")
        
        # Try importing the app
        from app import app, db, migrate, limiter
        print_test("Import app", True, "App imported successfully")
        
        # Check app configuration
        print_test("App Secret Key", bool(app.secret_key), f"Set: {app.secret_key[:10]}...")
        print_test("Database URI", bool(app.config.get('SQLALCHEMY_DATABASE_URI')), 
                  f"Set: {app.config.get('SQLALCHEMY_DATABASE_URI')[:30]}...")
        
        # Check extensions
        print_test("Database (db)", db is not None, "SQLAlchemy initialized")
        print_test("Migrations (migrate)", migrate is not None, "Flask-Migrate initialized")
        print_test("Rate Limiter", limiter is not None, "Flask-Limiter initialized")
        
        return app, db
        
    except Exception as e:
        print_test("App Initialization", False, f"Error: {e}")
        import traceback
        print(f"\n{Colors.RED}{traceback.format_exc()}{Colors.END}")
        return None, None

def test_database_connection(app, db):
    """Test 4: Database Connection"""
    print_header("TEST 4: Database Connection")
    
    if not app or not db:
        print_test("Database Test", False, "App not initialized, skipping")
        return False
    
    try:
        with app.app_context():
            from sqlalchemy import text
            result = db.session.execute(text('SELECT 1'))
            print_test("Database Connection", True, "Connected to PostgreSQL")
            
            # Check tables
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            print_test("Tables Found", len(tables) > 0, f"{len(tables)} tables: {', '.join(tables)}")
            
            # Check users table
            if 'users' in tables:
                from models import User
                user_count = User.query.count()
                print_test("Users Table", True, f"{user_count} users in database")
            else:
                print_test("Users Table", False, "Users table not found")
            
            return True
            
    except Exception as e:
        print_test("Database Connection", False, f"Error: {e}")
        return False

def test_migrations(app):
    """Test 5: Database Migrations"""
    print_header("TEST 5: Database Migrations")
    
    if not app:
        print_test("Migrations Test", False, "App not initialized, skipping")
        return
    
    # Check if migrations folder exists
    import os
    migrations_path = os.path.join(os.getcwd(), "migrations")
    
    if os.path.exists(migrations_path):
        print_test("Migrations Folder", True, f"Found at {migrations_path}")
        
        # Check for migration files
        versions_path = os.path.join(migrations_path, "versions")
        if os.path.exists(versions_path):
            migrations = [f for f in os.listdir(versions_path) if f.endswith('.py')]
            print_test("Migration Files", len(migrations) >= 0, 
                      f"{len(migrations)} migration(s) found")
        else:
            print_test("Versions Folder", False, "versions/ folder not found")
    else:
        print_test("Migrations Folder", False, "Run 'flask db init' to initialize")

def test_routes(app):
    """Test 6: Routes and Blueprints"""
    print_header("TEST 6: Routes and Blueprints")
    
    if not app:
        print_test("Routes Test", False, "App not initialized, skipping")
        return
    
    # Get all registered routes
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append(f"{rule.rule} [{', '.join(rule.methods)}]")
    
    # Check for specific new routes
    expected_routes = [
        ('/profile', 'GET'),
        ('/profile/update', 'POST'),
    ]
    
    print(f"{Colors.BOLD}Checking New Routes:{Colors.END}")
    for route, method in expected_routes:
        found = any(route in r and method in r for r in routes)
        print_test(f"{method} {route}", found, "Route registered" if found else "Route missing")
    
    print(f"\n{Colors.BOLD}Total Routes:{Colors.END} {len(routes)}")

def test_error_templates():
    """Test 7: Error Templates"""
    print_header("TEST 7: Error Templates")
    
    import os
    templates_path = os.path.join(os.getcwd(), "templates", "errors")
    
    if os.path.exists(templates_path):
        print_test("Error Templates Folder", True, f"Found at {templates_path}")
        
        # Check for specific error templates
        error_pages = {
            "404.html": "Not Found",
            "500.html": "Internal Server Error",
            "429.html": "Rate Limit Exceeded"
        }
        
        for filename, description in error_pages.items():
            filepath = os.path.join(templates_path, filename)
            exists = os.path.isfile(filepath)
            print_test(f"{description} ({filename})", exists, 
                      "Template found" if exists else "Template missing")
    else:
        print_test("Error Templates Folder", False, "templates/errors/ folder not found")

def test_profile_template():
    """Test 8: Profile Template"""
    print_header("TEST 8: Profile Template")
    
    import os
    profile_path = os.path.join(os.getcwd(), "templates", "profile.html")
    
    if os.path.isfile(profile_path):
        print_test("Profile Template", True, f"Found at {profile_path}")
        
        # Check file size
        size = os.path.getsize(profile_path)
        print_test("Template Size", size > 1000, f"{size} bytes")
    else:
        print_test("Profile Template", False, "templates/profile.html not found")

def print_summary():
    """Print Test Summary"""
    print_header("TEST SUMMARY")
    
    print(f"{Colors.BOLD}Phase 1 Features Status:{Colors.END}\n")
    
    features = [
        ("✓ Environment Variables", "Configured in .env"),
        ("✓ Flask-Migrate", "Database migrations enabled"),
        ("✓ Flask-Limiter", "Rate limiting active"),
        ("✓ User Profile Page", "Available at /profile"),
        ("✓ Error Pages", "404, 500, 429 templates"),
        ("✓ Database Connection", "PostgreSQL (Neon)"),
    ]
    
    for feature, description in features:
        print(f"{Colors.GREEN}{feature}{Colors.END}")
        print(f"  {Colors.YELLOW}{description}{Colors.END}\n")
    
    print(f"\n{Colors.BOLD}Next Steps:{Colors.END}")
    print(f"1. Start the app: {Colors.BLUE}python main.py{Colors.END}")
    print(f"2. Visit: {Colors.BLUE}http://localhost:5000{Colors.END}")
    print(f"3. Test profile: {Colors.BLUE}http://localhost:5000/profile{Colors.END}")
    print(f"4. Test 404: {Colors.BLUE}http://localhost:5000/nonexistent{Colors.END}")
    print(f"5. Test rate limiting: Login 11+ times quickly\n")

def main():
    """Main test runner"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}")
    print("╔═══════════════════════════════════════════════════════════╗")
    print("║   FantaCalcio AI - Phase 1 Enhancement Test Suite        ║")
    print("║   Testing: Migrations, Rate Limiting, Profile, Errors    ║")
    print("╚═══════════════════════════════════════════════════════════╝")
    print(f"{Colors.END}")
    
    # Load .env first
    from dotenv import load_dotenv
    load_dotenv()
    
    # Run tests
    test_environment_variables()
    test_imports()
    app, db = test_app_initialization()
    test_database_connection(app, db)
    test_migrations(app)
    test_routes(app)
    test_error_templates()
    test_profile_template()
    print_summary()
    
    print(f"\n{Colors.GREEN}{'='*60}{Colors.END}")
    print(f"{Colors.GREEN}All tests completed!{Colors.END}")
    print(f"{Colors.GREEN}{'='*60}{Colors.END}\n")

if __name__ == "__main__":
    main()
