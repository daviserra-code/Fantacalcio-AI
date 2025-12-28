"""
Debug script to check if user is logged in and has admin access
"""
import os
import sys

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env file BEFORE importing app
import config

from flask import Flask
from app import app
from models import User

@app.route('/debug-auth')
def debug_auth():
    """Debug route to check authentication"""
    from flask_login import current_user
    
    info = {
        'is_authenticated': current_user.is_authenticated,
        'is_anonymous': current_user.is_anonymous,
    }
    
    if current_user.is_authenticated:
        info['user_id'] = current_user.id
        info['username'] = current_user.username
        info['email'] = current_user.email
        info['is_admin'] = getattr(current_user, 'is_admin', 'ATTRIBUTE NOT FOUND')
        info['has_is_admin_attr'] = hasattr(current_user, 'is_admin')
    
    return f"""
    <html>
    <head><title>Auth Debug</title></head>
    <body style="font-family: monospace; padding: 20px;">
        <h1>Authentication Debug Info</h1>
        <pre>{str(info)}</pre>
        <hr>
        <h2>Actions:</h2>
        <ul>
            <li><a href="/auth/login">Login</a></li>
            <li><a href="/admin">Try Admin Page</a></li>
            <li><a href="/">Home</a></li>
        </ul>
    </body>
    </html>
    """

if __name__ == "__main__":
    print("Debug route added at /debug-auth")
    print("Start your app and visit: http://127.0.0.1:5000/debug-auth")
