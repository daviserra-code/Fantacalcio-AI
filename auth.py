
# auth.py - Custom authentication system
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, current_user, login_required
from urllib.parse import urlparse
from app import db, limiter
from models import User
from device_detector import DeviceDetector

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")  # Prevent brute force attacks
def login():
    """Login form and processing"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember_me = bool(request.form.get('remember_me'))
        
        if not username or not password:
            flash('Please provide both username and password', 'error')
            return render_template('auth/login.html')
        
        # Try to find user by username or email
        user = User.query.filter(
            (User.username == username) | (User.email == username)
        ).first()
        
        if user is None:
            print(f"Login failed: User '{username}' not found")
            flash('Invalid username/email or password', 'error')
            return render_template('auth/login.html')
        
        if not user.check_password(password):
            print(f"Login failed: Invalid password for user '{username}'")
            flash('Invalid username/email or password', 'error')
            return render_template('auth/login.html')
        
        if not user.is_active:
            flash('Your account has been deactivated', 'error')
            return render_template('auth/login.html')
        
        # Login successful
        login_user(user, remember=remember_me)
        flash(f'Welcome back, {user.first_name or user.username}!', 'success')
        
        # Redirect to next page or home
        next_page = request.args.get('next')
        if not next_page or urlparse(next_page).netloc != '':
            try:
                # Try to redirect to home page
                next_page = url_for('home')
            except:
                # Fallback to root
                next_page = '/'
        return redirect(next_page)
    
    return render_template('auth/login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per hour")  # Prevent spam registrations
def register():
    """Registration form and processing"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        password2 = request.form.get('password2', '')
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        
        # Validation
        errors = []
        
        if not username or len(username) < 3:
            errors.append('Username must be at least 3 characters long')
        
        if not email or '@' not in email:
            errors.append('Please provide a valid email address')
        
        if not password or len(password) < 6:
            errors.append('Password must be at least 6 characters long')
        
        if password != password2:
            errors.append('Passwords do not match')
        
        # Check if username already exists
        if User.query.filter_by(username=username).first():
            errors.append('Username already taken')
        
        # Check if email already exists
        if User.query.filter_by(email=email).first():
            errors.append('Email already registered')
        
        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('auth/register.html')
        
        # Create new user
        user = User(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name
        )
        user.set_password(password)
        
        try:
            db.session.add(user)
            db.session.commit()
            print(f"✅ User registered successfully: {username} ({email})")
            flash('Registration successful! You can now log in.', 'success')
            
            # Redirect to login page
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            print(f"❌ Registration failed for {username}: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # Provide more specific error messages
            error_msg = str(e).lower()
            if 'unique constraint' in error_msg or 'duplicate' in error_msg:
                if 'username' in error_msg:
                    flash('Username already taken. Please choose a different one.', 'error')
                elif 'email' in error_msg:
                    flash('Email already registered. Please use a different email.', 'error')
                else:
                    flash('Username or email already exists.', 'error')
            else:
                flash(f'Registration failed: {str(e)}', 'error')
            return render_template('auth/register.html')
    
    return render_template('auth/register.html')

@auth_bp.route('/logout')
@login_required
def logout():
    """Logout user"""
    logout_user()
    flash('You have been logged out.', 'info')
    try:
        return redirect(url_for('home'))
    except:
        return redirect('/')

@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """User profile page"""
    if request.method == 'POST':
        current_user.first_name = request.form.get('first_name', '').strip()
        current_user.last_name = request.form.get('last_name', '').strip()
        current_user.email = request.form.get('email', '').strip()
        
        # Check if password change is requested
        new_password = request.form.get('new_password', '')
        if new_password:
            if len(new_password) < 6:
                flash('Password must be at least 6 characters long', 'error')
                return render_template('auth/profile.html')
            
            current_password = request.form.get('current_password', '')
            if not current_user.check_password(current_password):
                flash('Current password is incorrect', 'error')
                return render_template('auth/profile.html')
            
            current_user.set_password(new_password)
            flash('Password updated successfully', 'success')
        
        try:
            db.session.commit()
            flash('Profile updated successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Update failed. Please try again.', 'error')
    
    return render_template('auth/profile.html')
