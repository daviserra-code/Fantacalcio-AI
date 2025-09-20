# routes.py - Enhanced routes with authentication and subscription management
from datetime import datetime
import json
import os
import stripe
from flask import session, request, jsonify, render_template, redirect, url_for, flash
from flask_login import current_user
from app import app, db
from replit_auth import require_login, require_pro, make_replit_blueprint
from models import User, UserLeague, Subscription
from league_rules_manager import LeagueRulesManager

# Configure Stripe
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')

# Register authentication blueprint
app.register_blueprint(make_replit_blueprint(), url_prefix="/auth")

# Make session permanent
@app.before_request
def make_session_permanent():
    session.permanent = True

@app.route('/dashboard')
@require_login
def dashboard():
    """Dashboard for logged-in users"""
    user_leagues = current_user.leagues if current_user.is_authenticated else []
    return render_template('dashboard.html', 
                         user=current_user, 
                         leagues=user_leagues,
                         is_pro=current_user.is_pro if current_user.is_authenticated else False)

@app.route('/upgrade')
def upgrade_to_pro():
    """Upgrade to pro subscription page"""
    return render_template('upgrade.html')

@app.route('/create-checkout-session', methods=['POST'])
@require_login
def create_checkout_session():
    """Create Stripe checkout session for pro subscription"""
    try:
        # Use request.url_root for reliable domain
        base_url = request.url_root.rstrip('/')
        
        checkout_session = stripe.checkout.Session.create(
            customer_email=current_user.email,
            line_items=[
                {
                    'price_data': {
                        'currency': 'eur',
                        'product_data': {
                            'name': 'Fantasy Football Pro Subscription',
                            'description': 'Access to premium league management features',
                        },
                        'unit_amount': 999,  # €9.99 in cents
                        'recurring': {
                            'interval': 'month',
                        },
                    },
                    'quantity': 1,
                },
            ],
            mode='subscription',
            success_url=base_url + '/subscription-success',
            cancel_url=base_url + '/upgrade',
            metadata={
                'user_id': current_user.id
            }
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        flash(f'Error creating checkout session: {str(e)}', 'error')
        return redirect(url_for('upgrade_to_pro'))

@app.route('/subscription-success')
@require_login
def subscription_success():
    """Handle successful subscription"""
    return render_template('subscription_success.html')

@app.route('/webhook/stripe', methods=['POST'])
def stripe_webhook():
    """Handle Stripe webhooks for subscription updates"""
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, os.environ.get('STRIPE_WEBHOOK_SECRET', 'dev-webhook-secret')
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        return jsonify({'error': 'Invalid signature'}), 400
    
    event_type = event['type']
    event_data = event['data']['object']
    
    if event_type == 'checkout.session.completed':
        # Handle successful subscription signup
        user_id = event_data['metadata'].get('user_id')
        if user_id and event_data['mode'] == 'subscription':
            user = User.query.get(user_id)
            if user:
                # Get the subscription details from Stripe
                subscription_id = event_data['subscription']
                subscription = stripe.Subscription.retrieve(subscription_id)
                
                # Create subscription record
                new_subscription = Subscription(
                    user_id=user_id,
                    stripe_subscription_id=subscription_id,
                    status=subscription['status'],
                    current_period_start=datetime.fromtimestamp(subscription['current_period_start']),
                    current_period_end=datetime.fromtimestamp(subscription['current_period_end'])
                )
                db.session.add(new_subscription)
                
                # Update user
                user.is_pro = True
                user.stripe_customer_id = event_data['customer']
                user.pro_expires_at = datetime.fromtimestamp(subscription['current_period_end'])
                db.session.commit()
                
    elif event_type == 'customer.subscription.updated':
        # Handle subscription changes
        subscription_id = event_data['id']
        subscription_record = Subscription.query.filter_by(stripe_subscription_id=subscription_id).first()
        if subscription_record:
            subscription_record.status = event_data['status']
            subscription_record.current_period_end = datetime.fromtimestamp(event_data['current_period_end'])
            
            # Update user pro status
            user = subscription_record.user
            if user:
                user.is_pro = event_data['status'] == 'active'
                user.pro_expires_at = datetime.fromtimestamp(event_data['current_period_end'])
            
            db.session.commit()
            
    elif event_type == 'customer.subscription.deleted':
        # Handle subscription cancellation
        subscription_id = event_data['id']
        subscription_record = Subscription.query.filter_by(stripe_subscription_id=subscription_id).first()
        if subscription_record:
            subscription_record.status = 'canceled'
            
            # Downgrade user
            user = subscription_record.user
            if user:
                user.is_pro = False
                user.pro_expires_at = None
            
            db.session.commit()
    
    return jsonify({'status': 'success'})

# League management routes
@app.route('/api/leagues')
@require_login
def get_user_leagues():
    """Get all leagues for the current user"""
    leagues = []
    for league in current_user.leagues:
        league_data = json.loads(league.league_data) if league.league_data else {}
        leagues.append({
            'id': league.id,
            'name': league.league_name,
            'created_at': league.created_at.isoformat(),
            'updated_at': league.updated_at.isoformat(),
            'summary': league_data.get('league_info', {})
        })
    
    return jsonify({
        'leagues': leagues,
        'is_pro': current_user.is_pro,
        'can_create_more': current_user.is_pro or len(leagues) < 1  # Free users get 1 league
    })

@app.route('/api/leagues', methods=['POST'])
@require_login
@require_pro
def create_league():
    """Create a new league (Pro users only)"""
    data = request.get_json()
    league_name = data.get('name', '').strip()
    
    if not league_name:
        return jsonify({'error': 'League name is required'}), 400
    
    # Check if league name already exists for this user
    existing = UserLeague.query.filter_by(
        user_id=current_user.id, 
        league_name=league_name
    ).first()
    
    if existing:
        return jsonify({'error': 'A league with this name already exists'}), 400
    
    # Create league with default rules
    rules_manager = LeagueRulesManager()
    default_rules = rules_manager.get_rules()
    default_rules['league_info']['name'] = league_name
    
    # Apply any custom rules from request
    if 'base_rules' in data:
        default_rules.update(data['base_rules'])
    
    new_league = UserLeague(
        user_id=current_user.id,
        league_name=league_name,
        league_data=json.dumps(default_rules)
    )
    
    db.session.add(new_league)
    db.session.commit()
    
    return jsonify({
        'id': new_league.id,
        'name': new_league.league_name,
        'created_at': new_league.created_at.isoformat()
    }), 201

@app.route('/api/leagues/<int:league_id>')
@require_login
def get_league(league_id):
    """Get a specific league"""
    league = UserLeague.query.filter_by(
        id=league_id,
        user_id=current_user.id
    ).first()
    
    if not league:
        return jsonify({'error': 'League not found'}), 404
    
    league_data = json.loads(league.league_data) if league.league_data else {}
    
    return jsonify({
        'id': league.id,
        'name': league.league_name,
        'rules': league_data,
        'created_at': league.created_at.isoformat(),
        'updated_at': league.updated_at.isoformat()
    })

@app.route('/api/leagues/<int:league_id>', methods=['PUT'])
@require_login
@require_pro
def update_league(league_id):
    """Update league rules (Pro users only)"""
    league = UserLeague.query.filter_by(
        id=league_id,
        user_id=current_user.id
    ).first()
    
    if not league:
        return jsonify({'error': 'League not found'}), 404
    
    data = request.get_json()
    current_rules = json.loads(league.league_data) if league.league_data else {}
    
    # Update rules
    if 'rules' in data:
        current_rules.update(data['rules'])
        current_rules['league_info']['last_updated'] = datetime.now().isoformat()
        
        league.league_data = json.dumps(current_rules)
        league.updated_at = datetime.now()
        db.session.commit()
    
    return jsonify({'status': 'updated'})

@app.route('/api/leagues/<int:league_id>', methods=['DELETE'])
@require_login
@require_pro
def delete_league(league_id):
    """Delete a league (Pro users only)"""
    league = UserLeague.query.filter_by(
        id=league_id,
        user_id=current_user.id
    ).first()
    
    if not league:
        return jsonify({'error': 'League not found'}), 404
    
    db.session.delete(league)
    db.session.commit()
    
    return jsonify({'status': 'deleted'})

@app.route('/api/leagues/<int:league_id>/import', methods=['POST'])
@require_login
@require_pro
def import_league_rules(league_id):
    """Import rules from document for a specific league"""
    league = UserLeague.query.filter_by(
        id=league_id,
        user_id=current_user.id
    ).first()
    
    if not league:
        return jsonify({'error': 'League not found'}), 404
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Save uploaded file temporarily
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as temp_file:
        file.save(temp_file.name)
        
        # Create a temporary rules manager and import
        temp_rules_manager = LeagueRulesManager()
        success = temp_rules_manager.import_from_document(temp_file.name)
        
        if success:
            # Update league with imported rules
            imported_rules = temp_rules_manager.get_rules()
            imported_rules['league_info']['name'] = league.league_name
            imported_rules['league_info']['last_updated'] = datetime.now().isoformat()
            
            league.league_data = json.dumps(imported_rules)
            league.updated_at = datetime.now()
            db.session.commit()
            
            os.unlink(temp_file.name)  # Clean up temp file
            
            return jsonify({
                'success': True,
                'message': 'Rules imported successfully',
                'rules': imported_rules
            })
        else:
            os.unlink(temp_file.name)  # Clean up temp file
            return jsonify({'error': 'Failed to import rules from document'}), 400