#!/usr/bin/env python3
"""
Production WSGI entry point for Fantasy Football AI application.
Uses Waitress WSGI server for reliable production deployment.
"""
import os
import logging
import sys

# Configure logging first
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def is_production():
    """Check if running in production environment"""
    return (os.getenv("REPLIT_DEPLOYMENT") == "1" or 
            os.getenv("ENVIRONMENT") == "production" or
            os.getenv("PORT") is not None)

# Set up environment variable defaults for development only
if not is_production() and 'SESSION_SECRET' not in os.environ:
    os.environ['SESSION_SECRET'] = 'dev-session-secret-12345'
    logger.warning("Using development SESSION_SECRET. Set SESSION_SECRET environment variable for production.")

try:
    # Import the Flask app
    from app import app
    
    # Fix HTTPS detection for production - critical for Replit Auth
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    app.config.update(
        PREFERRED_URL_SCHEME='https',
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_SAMESITE='Lax'
    )
    
    # Initialize authentication if needed
    from replit_auth import init_login_manager
    if not hasattr(app, 'login_manager'):
        init_login_manager(app)
    
    # Import routes and web interface
    import routes  # noqa: F401
    import web_interface  # noqa: F401
    
    logger.info("Application imported successfully")
    
except ImportError as e:
    logger.error(f"Import error: {e}")
    # Fallback to web_interface app
    from web_interface import app
    logger.info("Using fallback web_interface app")

# Production validation
if is_production():
    if 'SESSION_SECRET' not in os.environ:
        raise ValueError("SESSION_SECRET environment variable must be set for production deployment")

# WSGI application object
application = app

def main():
    """Main entry point for production server"""
    from waitress import serve
    
    # Get port configuration - ensure it's properly set
    port = int(os.getenv("PORT", 5000))
    host = "0.0.0.0"
    
    # Validate port configuration
    if port <= 0 or port > 65535:
        logger.error(f"Invalid port configuration: {port}")
        port = 5000
    
    logger.info(f"Starting Waitress server on {host}:{port}")
    logger.info(f"Production mode: {is_production()}")
    logger.info(f"Environment PORT: {os.getenv('PORT', 'not set')}")
    logger.info("Health check available at /health")
    logger.info("Readiness check available at /ready")
    
    # Serve with Waitress - production WSGI server
    # Optimized for fast startup and reliable deployment
    serve(
        application,
        host=host,
        port=port,
        threads=2,  # Reduced for faster startup
        cleanup_interval=60,  # Increased for better resource management
        connection_limit=50,  # Reduced for faster startup
        channel_timeout=60,  # Reduced timeout for faster response
        max_request_body_size=5242880,  # 5MB max request size
        asyncore_use_poll=True,  # Better for production
        ident="FantasyFootballAI/1.0",  # Server identification
    )

if __name__ == "__main__":
    main()