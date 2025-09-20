# main.py - Main application entry point with authentication
import os
import logging

# Set up environment variable defaults
if 'SESSION_SECRET' not in os.environ:
    os.environ['SESSION_SECRET'] = 'dev-session-secret-12345'

try:
    from app import app
    from replit_auth import init_login_manager
    
    # Initialize Flask-Login
    init_login_manager(app)
    
    import routes  # noqa: F401
    import web_interface  # noqa: F401
    
    if __name__ == "__main__":
        app.run(host="0.0.0.0", port=5000, debug=True)
except ImportError as e:
    logging.error(f"Import error: {e}")
    # Fallback to original web interface
    from web_interface import app
    if __name__ == "__main__":
        app.run(host="0.0.0.0", port=5000, debug=True)