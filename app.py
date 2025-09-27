# app.py - Main Flask application with custom authentication
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_socketio import SocketIO
from sqlalchemy.orm import DeclarativeBase
import os
from werkzeug.middleware.proxy_fix import ProxyFix
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class Base(DeclarativeBase):
    pass

# Initialize Flask app
app = Flask(__name__, template_folder="templates", static_folder="static", static_url_path="/static")
app.secret_key = os.environ.get("SESSION_SECRET")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1) # needed for url_for to generate with https

# Database configuration
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    'pool_pre_ping': True,
    "pool_recycle": 300,
}

# No need to call db.init_app(app) here, it's already done in the constructor.
db = SQLAlchemy(app, model_class=Base)

# Initialize SocketIO for real-time functionality
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Initialize LiveMatchTracker for real-time statistics
from live_match_tracker import LiveMatchTracker
live_tracker = LiveMatchTracker(socketio)

# Register WebSocket handlers
from websocket_handlers import register_websocket_handlers
register_websocket_handlers(socketio)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    from models import User
    try:
        # Try to convert to int first (for regular users)
        user_id_int = int(user_id)
        return User.query.get(user_id_int)
    except ValueError:
        # If it's not an integer (like 'pro_test_user_456'), it's invalid session data
        # Return None to force logout and clear invalid session
        logging.warning(f"Invalid user_id in session: {user_id}. Clearing session.")
        return None

# Import and register blueprints
try:
    from site_blueprint import site_bp
    app.register_blueprint(site_bp)
    logger.info("Site blueprint registered")
except Exception as e:
    logger.error(f"Failed to register site blueprint: {e}")

try:
    from auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')
    logger.info("Auth blueprint registered")
except Exception as e:
    logger.error(f"Failed to register auth blueprint: {e}")
    # Create a minimal auth blueprint as fallback
    from flask import Blueprint
    fallback_auth_bp = Blueprint('auth', __name__)

    @fallback_auth_bp.route('/login')
    def login():
        return "Authentication system temporarily unavailable"

    app.register_blueprint(fallback_auth_bp, url_prefix='/auth')
    logger.info("Fallback auth blueprint registered")

# Add readiness check endpoint for deployment monitoring
@app.route('/ready')
def readiness_check():
    """Readiness check endpoint for deployment monitoring"""
    try:
        # Check database connection
        from sqlalchemy import text
        db.session.execute(text('SELECT 1'))
        return {"status": "ready", "timestamp": str(datetime.now())}, 200
    except Exception as e:
        return {"status": "not ready", "error": str(e), "timestamp": str(datetime.now())}, 503

# Create tables
# Need to put this in module-level to make it work with Gunicorn.
with app.app_context():
    try:
        # Only create tables if they don't exist (don't drop existing data)
        db.create_all()
        logger.info("Database tables created/verified successfully")

        # Verify the tables were created correctly
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        logger.info(f"Database tables available: {tables}")

        # Check users table columns and their specifications
        if 'users' in tables:
            columns_info = inspector.get_columns('users')
            columns = [col['name'] for col in columns_info]
            logger.info(f"Users table columns: {columns}")

            # Check if password_hash column has correct size
            password_hash_col = next((col for col in columns_info if col['name'] == 'password_hash'), None)
            schema_needs_update = False

            if password_hash_col:
                # Check if the column size is too small for modern password hashes
                col_type_str = str(password_hash_col['type'])
                logger.info(f"password_hash column type: {col_type_str}")
                if 'VARCHAR(128)' in col_type_str or col_type_str == 'VARCHAR':
                    logger.warning("password_hash column is too small, needs update to VARCHAR(256)")
                    schema_needs_update = True

            required_columns = ['id', 'username', 'email', 'password_hash']
            missing_columns = [col for col in required_columns if col not in columns]

            if missing_columns or schema_needs_update:
                if missing_columns:
                    logger.error(f"Missing required columns in users table: {missing_columns}")
                if schema_needs_update:
                    logger.info("Schema update needed for password_hash column size")

                logger.info("Recreating tables due to schema issues...")
                db.drop_all()
                db.create_all()
                logger.info("Database tables recreated successfully")
            else:
                logger.info("Users table schema is correct")

    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        # Continue running even if database fails