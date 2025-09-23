# app.py - Main Flask application with custom authentication
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
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
app = Flask(__name__, template_folder="templates", static_folder="static")
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

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))

# Register blueprints
from site_blueprint import site_bp
from auth import auth_bp

app.register_blueprint(site_bp)
app.register_blueprint(auth_bp, url_prefix='/auth')
logging.info("Site blueprint registered")
logging.info("Auth blueprint registered")

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
        # Drop and recreate tables to ensure schema consistency
        db.drop_all()
        db.create_all()
        logger.info("Database tables recreated successfully")

        # Verify the tables were created correctly
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        logger.info(f"Database tables available: {tables}")

        # Check users table columns
        if 'users' in tables:
            columns = [col['name'] for col in inspector.get_columns('users')]
            logger.info(f"Users table columns: {columns}")

            required_columns = ['id', 'username', 'email', 'password_hash']
            missing_columns = [col for col in required_columns if col not in columns]
            if missing_columns:
                logger.error(f"Missing required columns in users table: {missing_columns}")
            else:
                logger.info("Users table schema is correct")

    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        # Continue running even if database fails