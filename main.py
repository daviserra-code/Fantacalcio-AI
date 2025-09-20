# main.py - Main application entry point with authentication
import os
import logging

# Set up environment variable defaults for development only
def is_production():
    """Check if running in production environment"""
    return (os.getenv("REPLIT_DEPLOYMENT") == "1" or 
            os.getenv("ENVIRONMENT") == "production" or
            os.getenv("PORT") is not None)

if not is_production() and 'SESSION_SECRET' not in os.environ:
    os.environ['SESSION_SECRET'] = 'dev-session-secret-12345'
    logging.warning("Using development SESSION_SECRET. Set SESSION_SECRET environment variable for production.")

try:
    from app import app
    from replit_auth import init_login_manager
    
    # Initialize Flask-Login
    init_login_manager(app)
    
    import routes  # noqa: F401
    import web_interface  # noqa: F401
    
    if __name__ == "__main__":
        # Production-safe configuration
        port = int(os.getenv("PORT", 5000))
        debug = not is_production()
        
        if is_production():
            logging.info(f"Starting production server on port {port}")
            if 'SESSION_SECRET' not in os.environ:
                raise ValueError("SESSION_SECRET environment variable must be set for production deployment")
        else:
            logging.info(f"Starting development server on port {port} with debug={debug}")
        
        app.run(host="0.0.0.0", port=port, debug=debug)
except ImportError as e:
    logging.error(f"Import error: {e}")
    # Fallback to original web interface
    from web_interface import app
    if __name__ == "__main__":
        # Production-safe configuration for fallback
        port = int(os.getenv("PORT", 5000))
        debug = not is_production()
        
        if is_production():
            logging.info(f"Starting fallback production server on port {port}")
            if 'SESSION_SECRET' not in os.environ:
                raise ValueError("SESSION_SECRET environment variable must be set for production deployment")
        else:
            logging.info(f"Starting fallback development server on port {port} with debug={debug}")
        
        app.run(host="0.0.0.0", port=port, debug=debug)