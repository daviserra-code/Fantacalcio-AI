from flask import Blueprint, render_template
from flask_login import login_required, current_user
from models import db
import logging

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__, template_folder='templates', static_folder='static', static_url_path='/static')

# Simple admin check (replace with your own logic)
def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        logger.info(f"Admin check: is_authenticated={current_user.is_authenticated}, is_admin={getattr(current_user, 'is_admin', False)}")
        if not current_user.is_authenticated or not getattr(current_user, 'is_admin', False):
            from flask import abort
            logger.warning(f"Admin access denied for user: {current_user.username if current_user.is_authenticated else 'anonymous'}")
            return abort(403)
        logger.info(f"Admin access granted for user: {current_user.username}")
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    logger.info("Admin dashboard accessed")
    # Example: fetch users and leagues (replace with your own models/logic)
    from models import User, UserLeague
    users = User.query.all()
    logger.info(f"Found {len(users)} users")
    leagues = UserLeague.query.all()
    logger.info(f"Found {len(leagues)} leagues")
    # Pass user and is_pro to match dashboard.html requirements
    return render_template('admin_dashboard.html', 
                         users=users, 
                         leagues=leagues,
                         user=current_user,
                         is_pro=current_user.is_pro if hasattr(current_user, 'is_pro') else False)

@admin_bp.route('/admin-test')
def admin_test():
    """Simple test route to verify blueprint is working"""
    logger.info("Admin test route accessed")
    return f"""
    <html>
    <head><title>Admin Test</title></head>
    <body style="font-family: monospace; padding: 20px;">
        <h1>✅ Admin Blueprint is Working!</h1>
        <p>If you can see this page, the admin blueprint is registered correctly.</p>
        <p>Current user: {current_user.username if current_user.is_authenticated else 'Not logged in'}</p>
        <p>Is admin: {current_user.is_admin if current_user.is_authenticated else 'N/A'}</p>
        <hr>
        <a href="/admin">Try accessing /admin</a> | 
        <a href="/debug-auth">Debug Auth</a> |
        <a href="/">Home</a>
    </body>
    </html>
    """

# API Routes for admin actions
@admin_bp.route('/admin/api/user/create', methods=['POST'])
@login_required
@admin_required
def create_user():
    """Create a new user"""
    from flask import request, jsonify
    from models import User
    from werkzeug.security import generate_password_hash
    logger.info("Create new user")
    
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('username') or not data.get('email') or not data.get('password'):
            return jsonify({'success': False, 'message': 'Username, email, and password are required'}), 400
        
        # Check if username already exists
        existing_user = User.query.filter_by(username=data['username']).first()
        if existing_user:
            return jsonify({'success': False, 'message': 'Username already exists'}), 400
        
        # Check if email already exists
        existing_email = User.query.filter_by(email=data['email']).first()
        if existing_email:
            return jsonify({'success': False, 'message': 'Email already exists'}), 400
        
        # Create new user
        new_user = User(
            username=data['username'],
            email=data['email'],
            password_hash=generate_password_hash(data['password']),
            is_admin=data.get('is_admin', False),
            is_active=data.get('is_active', True)
        )
        
        db.session.add(new_user)
        db.session.commit()
        logger.info(f"User {new_user.username} created successfully")
        
        return jsonify({'success': True, 'message': 'User created successfully', 'user_id': new_user.id})
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@admin_bp.route('/admin/api/user/<int:user_id>/admin', methods=['POST'])
@login_required
@admin_required
def update_user_admin(user_id):
    """Toggle admin status for a user"""
    from flask import request, jsonify
    from models import User
    logger.info(f"Update admin status for user {user_id}")
    
    try:
        data = request.get_json()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        user.is_admin = data.get('is_admin', False)
        db.session.commit()
        logger.info(f"User {user.username} admin status set to {user.is_admin}")
        
        return jsonify({'success': True, 'message': 'User updated'})
    except Exception as e:
        logger.error(f"Error updating user admin status: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@admin_bp.route('/admin/api/user/<int:user_id>/active', methods=['POST'])
@login_required
@admin_required
def update_user_active(user_id):
    """Toggle active status for a user"""
    from flask import request, jsonify
    from models import User
    logger.info(f"Update active status for user {user_id}")
    
    try:
        data = request.get_json()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        user.is_active = data.get('is_active', True)
        db.session.commit()
        logger.info(f"User {user.username} active status set to {user.is_active}")
        
        return jsonify({'success': True, 'message': 'User updated'})
    except Exception as e:
        logger.error(f"Error updating user active status: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@admin_bp.route('/admin/api/user/<int:user_id>/delete', methods=['DELETE'])
@login_required
@admin_required
def delete_user(user_id):
    """Delete a user"""
    from flask import jsonify
    from models import User
    logger.info(f"Delete user {user_id}")
    
    try:
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        # Don't allow deleting yourself
        if user.id == current_user.id:
            return jsonify({'success': False, 'message': 'Cannot delete your own account'}), 400
        
        username = user.username
        db.session.delete(user)
        db.session.commit()
        logger.info(f"User {username} deleted successfully")
        
        return jsonify({'success': True, 'message': 'User deleted'})
    except Exception as e:
        logger.error(f"Error deleting user: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
