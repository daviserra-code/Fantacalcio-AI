# routes.py - Enhanced routes with authentication and subscription management
from datetime import datetime
import json
import os
import logging
import stripe
from flask import session, request, jsonify, render_template, redirect, url_for, flash
from flask_login import current_user, login_user
from app import app, db
from flask_login import login_required, current_user
from models import User, UserLeague, Subscription
from league_rules_manager import LeagueRulesManager
from replit_auth import require_login, require_pro

# Configure logging
logger = logging.getLogger(__name__)

# Configure Stripe
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')

# Check if Stripe is properly configured
STRIPE_CONFIGURED = bool(
    os.environ.get('STRIPE_SECRET_KEY') and 
    os.environ.get('STRIPE_PUBLISHABLE_KEY')
)

def get_canonical_base_url(request):
    """
    Get the correct base URL - ALWAYS use HTTPS for all replit domains
    """
    # Get host from request
    host = request.headers.get('Host', request.environ.get('HTTP_HOST', ''))

    # If no host, try environment variables
    if not host:
        if os.environ.get('REPLIT_DEPLOYMENT') == '1':
            host = 'fanta-calcio-ai-daviserra3.replit.app'  # Force production domain
        else:
            domains = os.environ.get('REPLIT_DOMAINS')
            if domains:
                host = domains.split(',')[0]

    # ALWAYS use HTTPS for any replit domain
    if host and ('replit' in host or host.endswith('.repl.co')):
        return f"https://{host}", True

    # Fallback
    return f"https://{host or 'localhost:5000'}", True

# Authentication routes are now handled by auth.py blueprint

# Make session permanent
@app.before_request
def make_session_permanent():
    session.permanent = True

@app.route('/')
def home():
    """Home route - redirect to appropriate interface"""
    try:
        # Check if user is authenticated and redirect accordingly
        if current_user.is_authenticated:
            return redirect('/dashboard')
        else:
            # Show the main Fantasy Football AI interface
            lang = request.args.get("lang", "it")
            T = {
                "it": {
                    "title": "Fantasy Football Assistant",
                    "subtitle": "Consigli per asta, formazioni e strategie",
                    "participants": "Partecipanti",
                    "budget": "Budget",
                    "reset_chat": "Reset Chat",
                    "welcome": "Ciao! Sono qui per aiutarti con il fantacalcio.",
                    "send": "Invia",
                    "search_placeholder": "Cerca giocatori/club/metriche",
                    "all_roles": "Tutti",
                    "goalkeeper": "Portiere",
                    "defender": "Difensore",
                    "midfielder": "Centrocampista",
                    "forward": "Attaccante",
                }
            }
            return render_template('index.html', lang=lang, t=T.get(lang, T["it"]), user=None)
    except Exception as e:
        # Fallback to basic response
        return render_template('index.html')

@app.route('/index')
def index():
    """Alternative index route"""
    return render_template('index.html')


def _render_mobile_app_interface():
    """Render mobile app interface with authentication context"""
    from flask import request

    # Centralized translations
    T = {
        "it": {
            "title": "Fantasy Football Assistant",
            "subtitle": "Consigli per asta, formazioni e strategie",
            "participants": "Partecipanti",
            "budget": "Budget",
            "reset_chat": "Reset Chat",
            "welcome": "Ciao! Sono qui per aiutarti con il fantacalcio.",
            "send": "Invia",
            "search_placeholder": "Cerca giocatori/club/metriche",
            "all_roles": "Tutti",
            "goalkeeper": "Portiere",
            "defender": "Difensore",
            "midfielder": "Centrocampista",
            "forward": "Attaccante",
        }
    }

    lang = request.args.get("lang", "it")
    return render_template("index.html", 
                         lang=lang, 
                         t=T.get(lang, T["it"]), 
                         user=current_user if current_user.is_authenticated else None)

@app.route('/dashboard')
@login_required
def dashboard():
    """Dashboard for logged-in users"""
    user_leagues = current_user.leagues if current_user.is_authenticated else []
    return render_template('dashboard.html', 
                         user=current_user, 
                         leagues=user_leagues,
                         is_pro=current_user.is_pro if current_user.is_authenticated else False)

@app.route('/landing')
def landing():
    """Landing page for new users"""
    lang = request.args.get("lang", "it")
    T = {
        "it": {
            "title": "Fantasy Football Assistant",
            "subtitle": "Consigli per asta, formazioni e strategie"
        }
    }
    return render_template("landing.html", lang=lang, t=T.get(lang, T["it"]))

@app.route('/auth-status')
def auth_status():
    """Debug route to check authentication status"""
    return jsonify({
        'authenticated': current_user.is_authenticated,
        'user_id': current_user.id if current_user.is_authenticated else None,
        'is_pro': current_user.is_pro if current_user.is_authenticated else False
    })

@app.route('/stripe-status')
def stripe_status():
    """Debug route to check Stripe configuration"""
    secret_key = os.environ.get('STRIPE_SECRET_KEY', '')
    webhook_secret = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
    publishable_key = os.environ.get('STRIPE_PUBLISHABLE_KEY', '')

    # Test Stripe API connection
    stripe_api_test = {'connected': False, 'error': None}
    if secret_key:
        try:
            # Test basic Stripe API call
            test_customer = stripe.Customer.list(limit=1)
            stripe_api_test['connected'] = True
            stripe_api_test['test_call'] = 'SUCCESS - Customer.list() worked'
        except stripe.error.AuthenticationError as e:
            stripe_api_test['error'] = f'Authentication failed: {str(e)}'
        except stripe.error.APIConnectionError as e:
            stripe_api_test['error'] = f'API connection failed: {str(e)}'
        except Exception as e:
            stripe_api_test['error'] = f'Unexpected error: {str(e)}'

    return jsonify({
        'stripe_configured': STRIPE_CONFIGURED,
        'configuration_details': {
            'secret_key': {
                'configured': bool(secret_key),
                'starts_with_sk': secret_key.startswith('sk_') if secret_key else False,
                'length': len(secret_key) if secret_key else 0,
                'environment': 'test' if secret_key.startswith('sk_test_') else 'live' if secret_key.startswith('sk_live_') else 'unknown'
            },
            'publishable_key': {
                'configured': bool(publishable_key),
                'starts_with_pk': publishable_key.startswith('pk_') if publishable_key else False,
                'length': len(publishable_key) if publishable_key else 0,
                'environment': 'test' if publishable_key.startswith('pk_test_') else 'live' if publishable_key.startswith('pk_live_') else 'unknown'
            },
            'webhook_secret': {
                'configured': bool(webhook_secret),
                'starts_with_whsec': webhook_secret.startswith('whsec_') if webhook_secret else False,
                'length': len(webhook_secret) if webhook_secret else 0
            }
        },
        'stripe_api_test': stripe_api_test,
        'stripe_api_key_set': bool(stripe.api_key),
        'deployment_urls': {
            'webhook': f"{get_canonical_base_url(request)[0]}/webhook/stripe",
            'current_request_base': request.url_root,
            'success_url': f"{get_canonical_base_url(request)[0]}/subscription-success",
            'cancel_url': f"{get_canonical_base_url(request)[0]}/upgrade"
        },
        'troubleshooting': {
            'keys_match_environment': (
                secret_key.startswith('sk_test_') and publishable_key.startswith('pk_test_')
            ) or (
                secret_key.startswith('sk_live_') and publishable_key.startswith('pk_live_')
            ) if secret_key and publishable_key else False,
            'recommended_actions': [
                'Ensure all keys are from the same Stripe environment (test/live)',
                'Test webhook endpoint accessibility',
                'Verify webhook events are configured in Stripe Dashboard'
            ]
        }
    })

@app.route('/demo-login')
def demo_login():
    """Demo login for testing (temporary)"""
    from datetime import datetime, timedelta

    # Use a fixed demo user ID to avoid database issues
    demo_user_id = 999999
    demo_email = "protest@fantacalcio.ai"

    # Try to get existing demo user or create one
    try:
        user = User.query.filter_by(id=demo_user_id).first()
        if not user:
            user = User.query.filter_by(email=demo_email).first()

        if not user:
            user = User(
                email=demo_email,
                username="pro_tester",
                first_name="Pro",
                last_name="Tester"
            )
            user.set_password("demo123")  # Set a password for the demo user
            db.session.add(user)
            db.session.commit()

        # Always ensure pro subscription exists for test user
        existing_subscription = Subscription.query.filter_by(user_id=user.id).first()
        if not existing_subscription:
            subscription = Subscription(
                user_id=user.id,
                stripe_subscription_id="pro_test_subscription",
                status="active",
                current_period_start=datetime.utcnow(),
                current_period_end=datetime.utcnow() + timedelta(days=365)
            )
            db.session.add(subscription)
            db.session.commit()

    except Exception as e:
        # If all else fails, create a simple in-memory user for login
        user = User()
        user.id = demo_user_id
        user.email = demo_email
        user.first_name = "Pro"
        user.last_name = "Tester"

    # Log in the demo user with explicit session configuration
    login_user(user, remember=True, duration=timedelta(hours=24))

    # Ensure session is properly saved
    session.permanent = True
    session['user_id'] = user.id
    session['demo_login'] = True

    print(f"✅ Demo login successful for {user.email} - Session ID: {session.get('_id', 'N/A')}")

    # Redirect to dashboard to see league features
    return redirect('/dashboard')

@app.route('/upgrade')
@login_required
def upgrade_to_pro():
    """Upgrade to pro subscription page - requires login"""
    # Check if user is already pro
    if current_user.is_pro:
        flash('You already have an active Pro subscription!', 'info')
        return redirect('/dashboard')

    return render_template('upgrade.html', user=current_user)

@app.route('/create-checkout-session', methods=['POST'])
@require_login
def create_checkout_session():
    """Create Stripe checkout session for pro subscription"""
    # Check individual Stripe configuration
    stripe_secret = os.environ.get('STRIPE_SECRET_KEY')
    stripe_publishable = os.environ.get('STRIPE_PUBLISHABLE_KEY')

    if not stripe_secret:
        flash('Stripe Secret Key not configured. Please contact support at daviserra@gmail.com for Pro access.', 'warning')
        return redirect(url_for('upgrade_to_pro'))

    if not stripe_publishable:
        flash('Stripe Publishable Key not configured. Please contact support at daviserra@gmail.com for Pro access.', 'warning')
        return redirect(url_for('upgrade_to_pro'))

    # Verify keys are from same environment
    if (stripe_secret.startswith('sk_test_') and not stripe_publishable.startswith('pk_test_')) or \
       (stripe_secret.startswith('sk_live_') and not stripe_publishable.startswith('pk_live_')):
        flash('Stripe keys mismatch - secret and publishable keys must be from same environment (test/live)', 'error')
        return redirect(url_for('upgrade_to_pro'))

    try:
        # Use centralized base URL helper
        base_url, _ = get_canonical_base_url(request)

        # Debug logging with more details
        print(f"🔄 Creating Stripe session for user: {current_user.email}")
        print(f"🌐 Base URL: {base_url}")
        print(f"🔑 Secret key environment: {'test' if stripe_secret.startswith('sk_test_') else 'live'}")
        print(f"📧 Customer email: {current_user.email}")
        print(f"🌍 Host header: {request.headers.get('Host', 'N/A')}")
        print(f"🔒 Proto header: {request.headers.get('X-Forwarded-Proto', 'N/A')}")
        print(f"🔗 Final base URL: {base_url}")
        print(f"🚀 HTTPS properly detected: {base_url.startswith('https')}")

        # Test Stripe connectivity first
        try:
            test_response = stripe.Customer.list(limit=1)
            print(f"✅ Stripe API connectivity verified - found {len(test_response.data)} customers")
        except Exception as conn_test:
            print(f"❌ Stripe API connectivity failed: {conn_test}")
            flash(f'Cannot connect to Stripe API: {str(conn_test)}', 'error')
            return redirect(url_for('upgrade_to_pro'))

        # Create checkout session with proper URLs
        checkout_session = stripe.checkout.Session.create(
            customer_email=current_user.email,
            line_items=[
                {
                    'price_data': {
                        'currency': 'eur',
                        'product_data': {
                            'name': 'FantacalcioAI Pro',
                            'description': 'Premium fantasy football management features',
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
            success_url=f"{base_url}/subscription-success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base_url}/upgrade",
            automatic_tax={'enabled': False},
            allow_promotion_codes=True,
            billing_address_collection='required',
            metadata={
                'user_id': str(current_user.id),
                'user_email': current_user.email
            }
        )

        print(f"✅ Stripe session created successfully: {checkout_session.id}")
        print(f"🔗 Success URL: {checkout_session.success_url}")
        print(f"🔗 Cancel URL: {checkout_session.cancel_url}")
        print(f"🔗 Redirecting to: {checkout_session.url}")

        return redirect(checkout_session.url, code=303)

    except stripe.error.InvalidRequestError as e:
        error_msg = f"Stripe Invalid Request: {str(e)}"
        print(f"❌ {error_msg}")
        flash(f'Invalid request to Stripe: {str(e)}', 'error')
        return redirect(url_for('upgrade_to_pro'))
    except stripe.error.AuthenticationError as e:
        error_msg = f"Stripe Authentication Error: {str(e)}"
        print(f"❌ {error_msg}")
        flash('Stripe authentication failed. Please check API keys.', 'error')
        return redirect(url_for('upgrade_to_pro'))
    except stripe.error.APIConnectionError as e:
        error_msg = f"Stripe API Connection Error: {str(e)}"
        print(f"❌ {error_msg}")
        flash(f'Cannot reach Stripe servers: {str(e)}. Please try again later.', 'error')
        return redirect(url_for('upgrade_to_pro'))
    except stripe.error.RateLimitError as e:
        error_msg = f"Stripe Rate Limit Error: {str(e)}"
        print(f"❌ {error_msg}")
        flash('Too many requests to Stripe. Please try again in a moment.', 'error')
        return redirect(url_for('upgrade_to_pro'))
    except Exception as e:
        error_msg = f"General Stripe error: {str(e)}"
        print(f"❌ {error_msg}")
        flash(f'Payment system error: {str(e)}. Please contact support at daviserra@gmail.com', 'error')
        return redirect(url_for('upgrade_to_pro'))

@app.route('/subscription-success')
@require_login
def subscription_success():
    """Handle successful subscription"""
    return render_template('subscription_success.html')

@app.route('/sync-subscription', methods=['POST'])
@require_login
def sync_subscription():
    """Manually sync subscription status from Stripe (fallback for missing webhooks)"""
    if not STRIPE_CONFIGURED:
        return jsonify({'error': 'Stripe not configured'}), 400

    try:
        # Get user's customer ID
        if not current_user.stripe_customer_id:
            return jsonify({'error': 'No Stripe customer found'}), 404

        # Fetch subscriptions from Stripe
        subscriptions = stripe.Subscription.list(
            customer=current_user.stripe_customer_id,
            status='all'
        )

        # Update user based on active subscriptions
        has_active = False
        for sub in subscriptions.data:
            if sub.status == 'active':
                has_active = True
                # Update or create subscription record
                subscription_record = Subscription.query.filter_by(
                    stripe_subscription_id=sub.id
                ).first()

                if not subscription_record:
                    subscription_record = Subscription(
                        user_id=current_user.id,
                        stripe_subscription_id=sub.id,
                        status=sub.status,
                        current_period_start=datetime.fromtimestamp(sub.current_period_start),
                        current_period_end=datetime.fromtimestamp(sub.current_period_end)
                    )
                    db.session.add(subscription_record)
                else:
                    subscription_record.status = sub.status
                    subscription_record.current_period_end = datetime.fromtimestamp(sub.current_period_end)

                current_user.pro_expires_at = datetime.fromtimestamp(sub.current_period_end)
                break

        current_user.is_pro = has_active
        db.session.commit()

        return jsonify({
            'status': 'synced',
            'is_pro': has_active,
            'expires_at': current_user.pro_expires_at.isoformat() if current_user.pro_expires_at else None
        })

    except Exception as e:
        print(f"Subscription sync error: {e}")
        return jsonify({'error': 'Sync failed'}), 500

@app.route('/webhook/stripe', methods=['GET', 'POST'])
def stripe_webhook():
    """Handle Stripe webhooks for subscription updates"""
    # Handle GET requests for webhook verification and testing
    if request.method == 'GET':
        # Use centralized base URL helper
        base_url, is_https_detected = get_canonical_base_url(request)
        proto = request.headers.get('X-Forwarded-Proto', 'http')
        webhook_url = f"{base_url}/webhook/stripe"

        return jsonify({
            'status': 'Stripe webhook endpoint active',
            'url': request.url,
            'method': 'GET',
            'stripe_configured': STRIPE_CONFIGURED,
            'environment': 'live' if os.environ.get('STRIPE_SECRET_KEY', '').startswith('sk_live_') else 'test',
            'stripe_keys': {
                'secret_key_configured': bool(os.environ.get('STRIPE_SECRET_KEY')),
                'publishable_key_configured': bool(os.environ.get('STRIPE_PUBLISHABLE_KEY')),
                'webhook_secret_configured': bool(os.environ.get('STRIPE_WEBHOOK_SECRET'))
            },
            'recommended_webhook_url': webhook_url,  # The field the user sees
            'webhook_url_for_stripe_dashboard': webhook_url,  # Alternative field name
            'is_https': is_https_detected,
            'detected_proto': proto,
            'x_forwarded_proto': request.headers.get('X-Forwarded-Proto', 'not_set'),
            'timestamp': datetime.utcnow().isoformat(),
            'message': 'Webhook endpoint is accessible and ready to receive Stripe events',
            'setup_instructions': {
                '1': "Add STRIPE_WEBHOOK_SECRET to Replit Secrets",
                '2': "Use this URL in Stripe Dashboard",
                '3': "Select events: checkout.session.completed, customer.subscription.updated, customer.subscription.deleted"
            }
        }), 200

    # Handle POST requests (actual webhooks)
    if not STRIPE_CONFIGURED:
        print(f"Webhook received but Stripe not configured - URL: {request.url}")
        return jsonify({'error': 'Stripe not configured'}), 400

    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')
    webhook_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')

    print(f"Webhook POST received at: {request.url}")
    print(f"Signature header present: {bool(sig_header)}")
    print(f"Webhook secret configured: {bool(webhook_secret)}")
    print(f"Request method: {request.method}")
    print(f"Request headers: {dict(request.headers)}")

    if not webhook_secret:
        print("ERROR: STRIPE_WEBHOOK_SECRET not configured!")
        return jsonify({'error': 'Webhook secret not configured', 'help': 'Set STRIPE_WEBHOOK_SECRET in Replit Secrets'}), 400

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        print(f"✅ Webhook verified successfully: {event['type']}")
    except ValueError as e:
        print(f"❌ Webhook error - Invalid payload: {e}")
        return jsonify({'error': 'Invalid payload'}), 400
    except stripe.error.SignatureVerificationError as e:
        print(f"❌ Webhook error - Invalid signature: {e}")
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
@login_required
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
@login_required
def create_league():
    """Create a new league (Pro users only)"""
    if not current_user.is_pro:
        return jsonify({'error': 'Pro subscription required'}), 403

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
@login_required
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

@app.route('/league/<int:league_id>')
@require_login
def league_detail(league_id):
    """Display league detail page"""
    league = UserLeague.query.filter_by(
        id=league_id,
        user_id=current_user.id
    ).first()

    if not league:
        flash('League not found', 'error')
        return redirect('/dashboard')

    league_data = json.loads(league.league_data) if league.league_data else {}

    return render_template('league_detail.html', 
                         league=league,
                         league_data=league_data,
                         user=current_user)

@app.route('/api/rules/summary')
def get_default_rules_summary():
    """Get default rules summary for reference"""
    rules_manager = LeagueRulesManager()
    return jsonify(rules_manager.get_rules_summary())

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
    file_extension = os.path.splitext(file.filename)[1].lower()

    with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
        file.save(temp_file.name)

        try:
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

                return jsonify({
                    'success': True,
                    'message': 'Rules imported successfully',
                    'rules': imported_rules
                })
            else:
                return jsonify({'error': 'Failed to import rules from document'}), 400

        except Exception as e:
            return jsonify({'error': f'Error processing document: {str(e)}'}), 400

        finally:
            # Clean up temp file
            try:
                os.unlink(temp_file.name)
            except:
                pass

# ============ NEW ENHANCED API ROUTES ============

@app.route('/api/cache/stats')
def api_cache_stats():
    """Get Redis cache statistics"""
    from cache_redis import get_redis_cache
    cache = get_redis_cache()
    return jsonify(cache.get_stats())

@app.route('/api/cache/clear', methods=['POST'])
@require_login
def api_cache_clear():
    """Clear cache (authenticated users only)"""
    from cache_redis import get_redis_cache
    cache = get_redis_cache()
    cleared = cache.clear_pattern("*")
    return jsonify({'cleared': cleared, 'message': 'Cache cleared successfully'})

@app.route('/api/team-builder', methods=['POST'])
@require_login
def api_team_builder():
    """AI-powered team builder with genetic algorithm"""
    try:
        from subscription_tiers import require_feature, track_feature_usage, has_feature
        from ai_team_builder import AITeamBuilder, Player
        import json
        import logging
        
        logger = logging.getLogger(__name__)
        logger.info("Team builder endpoint called")
        
        # Check if user has access to this feature
        if not has_feature('formation_suggestions'):
            logger.warning(f"User {current_user.id} tried to access team builder without permission")
            return jsonify({
                'error': 'feature_not_available',
                'message': 'Questa funzione richiede un abbonamento Pro o superiore.',
                'upgrade_url': '/upgrade'
            }), 403
        
        track_feature_usage('team_builder')
        
        data = request.json or {}
        budget = data.get('budget', 500)
        formation_str = data.get('formation', '3-5-2')
        objectives = data.get('objectives', {'performance': 0.5, 'value': 0.3, 'reliability': 0.2})
        
        logger.info(f"Raw request data: budget={budget}, formation={formation_str}, objectives={objectives}")
        logger.info(f"Types: formation type={type(formation_str)}, objectives type={type(objectives)}")
        
        logger.info(f"Building team: budget={budget}, formation={formation_str}")
        
        # Parse formation string to dict (e.g., "3-5-2" -> {P:1, D:3, C:5, A:2})
        formation_dict = {'P': 1}
        if isinstance(formation_str, str):
            parts = formation_str.split('-')
            if len(parts) == 3:
                formation_dict['D'] = int(parts[0])
                formation_dict['C'] = int(parts[1])
                formation_dict['A'] = int(parts[2])
        else:
            formation_dict = formation_str
        
        logger.info(f"Formation parsed: {formation_dict}")
        
        # Load roster from JSON file
        roster_path = 'season_roster.json'
        if not os.path.exists(roster_path):
            logger.error(f"Roster file not found: {roster_path}")
            return jsonify({'error': 'Roster non disponibile'}), 500
        
        with open(roster_path, 'r', encoding='utf-8') as f:
            roster_data = json.load(f)
        
        logger.info(f"Loaded {len(roster_data)} players from roster")
        
        # Convert to Player objects
        players = []
        for p in roster_data:
            try:
                players.append(Player(
                    name=p.get('name', 'Unknown'),
                    role=p.get('role', 'C'),
                    team=p.get('team', ''),
                    price=float(p.get('price', 1)),
                    fantamedia=float(p.get('fantamedia', 6.0)),
                    appearances=int(p.get('appearances', 0)),
                    goals=int(p.get('goals', 0)),
                    assists=int(p.get('assists', 0))
                ))
            except (ValueError, TypeError) as e:
                logger.warning(f"Skipping invalid player: {p.get('name', 'unknown')} - {str(e)}")
                continue
        
        if not players:
            logger.error("No valid players found after conversion")
            return jsonify({'error': 'Nessun giocatore disponibile'}), 500
        
        logger.info(f"Converted {len(players)} players successfully")
        
        builder = AITeamBuilder(players, budget)
        result = builder.build_optimal_team(formation_dict, objectives)
        
        logger.info(f"Team building successful: {len(result.get('team', []))} players selected")
        
        return jsonify(result), 200
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger = logging.getLogger(__name__)
        logger.error(f"TEAM BUILDER ERROR: {str(e)}")
        logger.error(f"Traceback:\n{error_trace}")
        return jsonify({
            'error': f'Errore durante la creazione del team: {str(e)}',
            'details': error_trace if app.debug else None
        }), 500

@app.route('/api/predictions', methods=['POST'])
@require_login
def api_predictions():
    """ML-powered performance predictions for a single player"""
    from subscription_tiers import has_feature, track_feature_usage, get_user_tier
    from ml_predictor import get_ml_predictor
    
    # Debug logging
    tier = get_user_tier()
    logger.info(f"ML Predictions called by: {current_user.email if current_user.is_authenticated else 'Anonymous'}")
    logger.info(f"User tier: {tier['name']}")
    logger.info(f"User is_pro: {current_user.is_pro if current_user.is_authenticated else 'N/A'}")
    logger.info(f"User pro_expires_at: {current_user.pro_expires_at if current_user.is_authenticated else 'N/A'}")
    logger.info(f"Has ml_predictions feature: {has_feature('ml_predictions')}")
    
    if not has_feature('ml_predictions'):
        return jsonify({
            'error': 'feature_not_available',
            'message': 'Le predizioni ML richiedono un abbonamento Elite.',
            'upgrade_url': '/upgrade'
        }), 403
    
    track_feature_usage('ml_predictions')
    
    data = request.json or {}
    player_features = data.get('player_features', {})
    
    try:
        predictor = get_ml_predictor()
        logger.info(f"Predictor loaded: {predictor is not None}, model: {predictor.model is not None if predictor else None}")
        logger.info(f"Player features: {player_features}")
        
        prediction = predictor.predict(player_features)
        logger.info(f"Prediction result: {prediction}")
        
        return jsonify(prediction)
    except Exception as e:
        logger.error(f"ML Prediction error: {e}", exc_info=True)
        return jsonify({'error': str(e), 'message': f'Errore ML: {str(e)}'}), 500

@app.route('/api/predictions/batch', methods=['POST'])
@require_login
def api_predictions_batch():
    """Batch predictions for multiple players"""
    from subscription_tiers import has_feature, track_feature_usage
    from ml_predictor import get_ml_predictor
    
    if not has_feature('ml_predictions'):
        return jsonify({
            'error': 'feature_not_available',
            'message': 'Le predizioni ML richiedono un abbonamento Elite.',
            'upgrade_url': '/upgrade'
        }), 403
    
    track_feature_usage('ml_predictions_batch')
    
    data = request.json or {}
    players_data = data.get('players', [])
    
    try:
        predictor = get_ml_predictor()
        predictions = predictor.predict_batch(players_data)
        return jsonify({'predictions': predictions})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/match-tracker/active')
def api_active_matches():
    """Get currently active matches"""
    from match_tracker_enhanced import get_match_tracker
    from live_matches_service import get_live_matches_service
    from datetime import datetime
    
    tracker = get_match_tracker()
    service = get_live_matches_service()
    
    # Try to fetch real live matches
    try:
        live_matches = service.get_live_matches()
        
        # Sync to tracker
        if live_matches:
            service.sync_to_tracker(tracker)
        
        # Get tracked matches
        matches = tracker.get_active_matches()
        
        # If no tracked matches but we have live matches from API, use those
        if not matches and live_matches:
            matches = live_matches
            
    except Exception as e:
        app.logger.error(f"Error fetching live matches: {e}")
        matches = tracker.get_active_matches()
    
    # If still no matches, check if it's matchday and provide info
    if not matches:
        # Serie A typically plays Friday 20:45, Saturday/Sunday 12:30, 15:00, 18:00, 20:45
        now = datetime.now()
        day = now.weekday()  # 0=Monday, 6=Sunday
        hour = now.hour
        
        # Check if it's likely matchday time
        is_matchday = False
        if day == 4 and hour >= 20:  # Friday evening
            is_matchday = True
        elif day == 5:  # Saturday
            is_matchday = True
        elif day == 6:  # Sunday
            is_matchday = True
            
        return jsonify({
            'matches': [],
            'message': 'Nessuna partita live al momento',
            'is_matchday': is_matchday,
            'next_check': 'Controlla durante i weekend per le partite di Serie A'
        })
    
    return jsonify({'matches': matches})

@app.route('/api/match-tracker/demo')
def api_demo_matches():
    """Get demo/mock matches for testing"""
    from match_tracker_enhanced import get_match_tracker
    import random
    
    # Create some realistic demo matches
    demo_teams = [
        ("Inter", "Milan"),
        ("Juventus", "Napoli"),
        ("Roma", "Lazio"),
        ("Atalanta", "Fiorentina"),
        ("Bologna", "Torino")
    ]
    
    tracker = get_match_tracker()
    demo_matches = []
    
    for idx, (home, away) in enumerate(demo_teams[:2]):  # Only 2 demo matches
        match_id = f"demo_{idx+1}"
        
        # Start tracking if not already
        if match_id not in tracker.active_matches:
            tracker.start_match(match_id, home, away)
            
            # Add some demo score and data
            match = tracker.active_matches[match_id]
            match['score'] = {
                'home': random.randint(0, 3),
                'away': random.randint(0, 2)
            }
            match['minute'] = random.randint(20, 80)
            match['status'] = 'live'
        
        # Get summary and ensure it exists
        summary = tracker.get_match_summary(match_id)
        if summary:
            demo_matches.append(summary)
        else:
            # Fallback to basic match info
            match = tracker.active_matches[match_id]
            demo_matches.append({
                'match_id': match_id,
                'home_team': home,
                'away_team': away,
                'score': match['score'],
                'minute': match['minute'],
                'status': 'live'
            })
    
    return jsonify({
        'matches': demo_matches,
        'note': 'Partite demo per test - non sono partite reali'
    })

@app.route('/api/match-tracker/<match_id>')
def api_match_summary(match_id):
    """Get match summary and current stats"""
    from match_tracker_enhanced import get_match_tracker
    import random
    
    # Handle demo request
    if match_id == "demo":
        return api_demo_matches()
    
    tracker = get_match_tracker()
    summary = tracker.get_match_summary(match_id)
    return jsonify(summary or {'error': 'Match not found'}), 200 if summary else 404

@app.route('/api/subscription/tier')
@require_login
def api_subscription_tier():
    """Get current user's subscription tier and features"""
    from subscription_tiers import get_user_tier, get_tier_comparison
    
    tier = get_user_tier()
    comparison = get_tier_comparison()
    
    return jsonify({
        'current_tier': tier,
        'all_tiers': comparison,
        'user': {
            'username': current_user.username,
            'is_pro': current_user.is_pro
        }
    })