# routes.py - Enhanced routes with authentication and subscription management
from datetime import datetime
import json
import os
import stripe
from flask import session, request, jsonify, render_template, redirect, url_for, flash
from flask_login import current_user, login_user
from app import app, db
from flask_login import login_required, current_user
from models import User, UserLeague, Subscription
from league_rules_manager import LeagueRulesManager
from replit_auth import require_login, require_pro

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

@app.route('/debug-auth')
def debug_auth():
    """Debug route to check authentication status"""
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
        info['is_admin_value'] = current_user.is_admin if hasattr(current_user, 'is_admin') else None
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Auth Debug</title>
        <style>
            body {{ font-family: monospace; padding: 20px; background: #f5f5f5; }}
            .info {{ background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
            pre {{ background: #eee; padding: 10px; border-radius: 4px; overflow-x: auto; }}
            h1 {{ color: #333; }}
            h2 {{ color: #666; }}
            a {{ color: #0066cc; text-decoration: none; padding: 8px 12px; background: #e7f3ff; border-radius: 4px; display: inline-block; margin: 5px; }}
            a:hover {{ background: #cce5ff; }}
            .status {{ font-size: 24px; margin: 10px 0; }}
            .success {{ color: green; }}
            .error {{ color: red; }}
        </style>
    </head>
    <body>
        <div class="info">
            <h1>🔍 Authentication Debug Info</h1>
            <div class="status">
                Status: <span class="{'success' if current_user.is_authenticated else 'error'}">
                    {'✅ LOGGED IN' if current_user.is_authenticated else '❌ NOT LOGGED IN'}
                </span>
            </div>
            <pre>{json.dumps(info, indent=2)}</pre>
        </div>
        
        <div class="info">
            <h2>🔧 Actions:</h2>
            <a href="/auth/login">🔑 Login</a>
            <a href="/auth/logout">🚪 Logout</a>
            <a href="/admin">🛡️ Try Admin Page</a>
            <a href="/dashboard">📊 Dashboard</a>
            <a href="/">🏠 Home</a>
        </div>
        
        <div class="info">
            <h2>📝 Instructions:</h2>
            <ol>
                <li>If you're NOT logged in, click "Login" first</li>
                <li>After logging in, refresh this page to see your user info</li>
                <li>If is_admin is TRUE, click "Try Admin Page"</li>
                <li>If is_admin is FALSE or NULL, run set_admin.py script</li>
            </ol>
        </div>
    </body>
    </html>
    """
    return html

@app.route('/debug-routes')
def debug_routes():
    """List all registered routes"""
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({
            'endpoint': rule.endpoint,
            'methods': ','.join(rule.methods),
            'path': str(rule)
        })
    
    # Sort by path
    routes.sort(key=lambda x: x['path'])
    
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Routes Debug</title>
        <style>
            body { font-family: monospace; padding: 20px; background: #f5f5f5; }
            table { background: white; width: 100%; border-collapse: collapse; }
            th, td { padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }
            th { background: #333; color: white; }
            tr:hover { background: #f0f0f0; }
            .admin { background: #ffe6e6; }
        </style>
    </head>
    <body>
        <h1>📋 Registered Routes</h1>
        <table>
            <tr>
                <th>Path</th>
                <th>Endpoint</th>
                <th>Methods</th>
            </tr>
    """
    
    for route in routes:
        row_class = 'admin' if 'admin' in route['path'].lower() else ''
        html += f"""
            <tr class="{row_class}">
                <td><a href="{route['path']}">{route['path']}</a></td>
                <td>{route['endpoint']}</td>
                <td>{route['methods']}</td>
            </tr>
        """
    
    html += """
        </table>
        <p style="margin-top: 20px;"><a href="/debug-auth">← Back to Auth Debug</a></p>
    </body>
    </html>
    """
    return html

@app.route('/simple-admin-test')
def simple_admin_test():
    """Simple test page with direct links"""
    return render_template('admin_test.html')
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

@app.route('/profile')
@login_required
def profile():
    """User profile page"""
    return render_template('profile.html', user=current_user)

@app.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    """Update user profile information"""
    try:
        current_user.first_name = request.form.get('first_name', '').strip()
        current_user.last_name = request.form.get('last_name', '').strip()
        
        # Update email only if changed and not already in use
        new_email = request.form.get('email', '').strip()
        if new_email and new_email != current_user.email:
            existing_user = User.query.filter_by(email=new_email).first()
            if existing_user:
                flash('Email already in use by another account', 'error')
                return redirect(url_for('profile'))
            current_user.email = new_email
        
        db.session.commit()
        flash('Profile updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating profile: {str(e)}', 'error')
    
    return redirect(url_for('profile'))

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


# ============================================================================
# PHASE 2A: ENHANCED PLAYER FILTERING & SEARCH
# ============================================================================

@app.route('/api/players/search/advanced', methods=['POST'])
@login_required
def search_players_advanced():
    """Advanced player search with multiple criteria"""
    from fantacalcio_assistant import FantacalcioAssistant
    import json
    
    try:
        filters = request.get_json() or {}
        
        # Extract filters with defaults
        roles = filters.get('roles', [])  # ['D', 'C']
        teams = filters.get('teams', [])  # ['Juventus', 'Inter']
        price_min = filters.get('price_min', 0)
        price_max = filters.get('price_max', 999)
        fantamedia_min = filters.get('fantamedia_min', 0)
        fantamedia_max = filters.get('fantamedia_max', 999)
        under21 = filters.get('under21', False)
        appearances_min = filters.get('appearances_min', 0)
        search_text = filters.get('search', '').strip().lower()
        
        # Load roster from FantacalcioAssistant
        assistant = FantacalcioAssistant()
        assistant._ensure_data_loaded()
        players = assistant.roster
        
        # Apply filters
        filtered = []
        current_year = 2025
        
        for player in players:
            # Role filter
            if roles and player.get('role') not in roles:
                continue
            
            # Team filter
            if teams and player.get('team') not in teams:
                continue
            
            # Price filter
            price = player.get('price', 0) or 0
            if price < price_min or price > price_max:
                continue
            
            # Fantamedia filter
            fm = player.get('fantamedia', 0) or 0
            if fm < fantamedia_min or fm > fantamedia_max:
                continue
            
            # Under 21 filter
            if under21:
                birth_year = player.get('birth_year')
                if not birth_year or (current_year - birth_year) > 21:
                    continue
            
            # Appearances filter
            appearances = player.get('appearances', 0) or 0
            if appearances < appearances_min:
                continue
            
            # Text search (fuzzy name matching)
            if search_text:
                name = (player.get('name') or '').lower()
                team = (player.get('team') or '').lower()
                if search_text not in name and search_text not in team:
                    continue
            
            # Calculate efficiency metric
            efficiency = round(fm / price * 100, 2) if price > 0 else 0
            
            # Add to filtered results with calculated fields
            player_result = {
                'name': player.get('name'),
                'role': player.get('role'),
                'team': player.get('team'),
                'price': price,
                'fantamedia': fm,
                'appearances': appearances,
                'birth_year': player.get('birth_year'),
                'efficiency': efficiency,
                'season': player.get('season', '2025-26')
            }
            
            filtered.append(player_result)
        
        # Sort by fantamedia descending (best players first)
        filtered.sort(key=lambda x: x.get('fantamedia', 0), reverse=True)
        
        # Limit results to prevent huge responses
        max_results = filters.get('limit', 100)
        limited_results = filtered[:max_results]
        
        return jsonify({
            'success': True,
            'count': len(filtered),
            'total_available': len(players),
            'showing': len(limited_results),
            'players': limited_results,
            'filters_applied': {
                'roles': roles,
                'teams': teams,
                'price_range': [price_min, price_max],
                'fantamedia_min': fantamedia_min,
                'under21': under21,
                'search_text': search_text
            }
        })
        
    except Exception as e:
        import traceback
        print(f"Error in advanced search: {e}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e),
            'count': 0,
            'players': []
        }), 500


@app.route('/api/players/quick-filters/<filter_name>')
@login_required
def quick_filter(filter_name):
    """Predefined quick filters for common searches"""
    
    # Define quick filter presets
    QUICK_FILTERS = {
        'best_value_defenders': {
            'roles': ['D'],
            'price_max': 30,
            'fantamedia_min': 20,
            'limit': 20
        },
        'under21_forwards': {
            'roles': ['A'],
            'under21': True,
            'appearances_min': 5,
            'limit': 20
        },
        'budget_midfielders': {
            'roles': ['C'],
            'price_max': 15,
            'fantamedia_min': 15,
            'limit': 20
        },
        'premium_players': {
            'price_min': 40,
            'fantamedia_min': 25,
            'limit': 20
        },
        'top_goalkeepers': {
            'roles': ['P'],
            'fantamedia_min': 20,
            'limit': 10
        },
        'bargain_hunters': {
            'price_max': 10,
            'fantamedia_min': 10,
            'limit': 30
        }
    }
    
    filter_config = QUICK_FILTERS.get(filter_name)
    if not filter_config:
        return jsonify({
            'success': False,
            'error': f'Filter "{filter_name}" not found',
            'available_filters': list(QUICK_FILTERS.keys())
        }), 404
    
    # Apply filter directly
    try:
        from fantacalcio_assistant import FantacalcioAssistant
        assistant = FantacalcioAssistant()
        # Ensure data is loaded
        assistant._ensure_data_loaded()
        all_players = assistant.roster
        
        # Apply filters
        filtered = all_players
        
        # Role filter
        if 'roles' in filter_config:
            filtered = [p for p in filtered if p.get('role') in filter_config['roles']]
        
        # Price filters
        if 'price_min' in filter_config:
            filtered = [p for p in filtered if (p.get('price') or 0) >= filter_config['price_min']]
        if 'price_max' in filter_config:
            filtered = [p for p in filtered if (p.get('price') or 0) <= filter_config['price_max']]
        
        # Fantamedia filter
        if 'fantamedia_min' in filter_config:
            filtered = [p for p in filtered if (p.get('fantamedia') or 0) >= filter_config['fantamedia_min']]
        
        # Under 21 filter
        if filter_config.get('under21'):
            filtered = [p for p in filtered if (p.get('age') or 99) < 21]
        
        # Appearances filter
        if 'appearances_min' in filter_config:
            filtered = [p for p in filtered if (p.get('appearances') or 0) >= filter_config['appearances_min']]
        
        # Calculate efficiency and sort
        for p in filtered:
            price = p.get('price') or 1
            fm = p.get('fantamedia') or 0
            p['efficiency'] = round(fm / price * 100, 2) if price > 0 else 0
        
        # Sort by efficiency descending
        filtered.sort(key=lambda x: x.get('efficiency', 0), reverse=True)
        
        # Limit results
        limit = filter_config.get('limit', 100)
        result_players = filtered[:limit]
        
        return jsonify({
            'success': True,
            'count': len(filtered),
            'total_available': len(all_players),
            'showing': len(result_players),
            'players': [{
                'name': p.get('name'),
                'role': p.get('role'),
                'team': p.get('team'),
                'price': p.get('price'),
                'fantamedia': p.get('fantamedia'),
                'efficiency': p.get('efficiency'),
                'age': p.get('age'),
                'appearances': p.get('appearances')
            } for p in result_players],
            'filter_name': filter_name
        })
    except Exception as e:
        print(f"Error in quick filter {filter_name}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/players/search')
@login_required
def players_search_page():
    """Player search page with advanced filtering"""
    return render_template('players_search.html', user=current_user)


@app.route('/api/players/compare', methods=['POST'])
@login_required
def compare_players():
    """Compare multiple players side by side with detailed statistics"""
    try:
        from fantacalcio_assistant import FantacalcioAssistant
        
        data = request.get_json() or {}
        player_names = data.get('players', [])
        
        if not player_names or len(player_names) < 2:
            return jsonify({
                'success': False,
                'error': 'Seleziona almeno 2 giocatori da confrontare'
            }), 400
        
        if len(player_names) > 4:
            return jsonify({
                'success': False,
                'error': 'Puoi confrontare massimo 4 giocatori alla volta'
            }), 400
        
        # Load data
        assistant = FantacalcioAssistant()
        assistant._ensure_data_loaded()
        all_players = assistant.roster
        
        # Find players by name (case-insensitive)
        comparison_data = []
        not_found = []
        
        for name in player_names:
            player = next((p for p in all_players if p.get('name', '').lower() == name.lower()), None)
            if player:
                # Calculate additional metrics
                price = player.get('price') or 1
                fm = player.get('fantamedia') or 0
                efficiency = round(fm / price * 100, 2) if price > 0 else 0
                
                # Calculate percentile rankings
                all_prices = [p.get('price') or 0 for p in all_players if p.get('price')]
                all_fms = [p.get('fantamedia') or 0 for p in all_players if p.get('fantamedia')]
                all_appearances = [p.get('appearances') or 0 for p in all_players if p.get('appearances')]
                
                price_percentile = calculate_percentile(player.get('price') or 0, all_prices)
                fm_percentile = calculate_percentile(fm, all_fms)
                appearances_percentile = calculate_percentile(player.get('appearances') or 0, all_appearances)
                
                comparison_data.append({
                    'name': player.get('name'),
                    'role': player.get('role'),
                    'team': player.get('team'),
                    'price': player.get('price'),
                    'fantamedia': fm,
                    'efficiency': efficiency,
                    'age': player.get('age'),
                    'appearances': player.get('appearances'),
                    'goals': player.get('goals', 0),
                    'assists': player.get('assists', 0),
                    'yellow_cards': player.get('yellow_cards', 0),
                    'red_cards': player.get('red_cards', 0),
                    'percentiles': {
                        'price': price_percentile,
                        'fantamedia': fm_percentile,
                        'appearances': appearances_percentile
                    }
                })
            else:
                not_found.append(name)
        
        if not comparison_data:
            return jsonify({
                'success': False,
                'error': f'Nessun giocatore trovato: {", ".join(not_found)}'
            }), 404
        
        # Calculate comparative metrics
        response = {
            'success': True,
            'count': len(comparison_data),
            'players': comparison_data,
            'not_found': not_found,
            'averages': {
                'price': round(sum(p['price'] or 0 for p in comparison_data) / len(comparison_data), 1),
                'fantamedia': round(sum(p['fantamedia'] for p in comparison_data) / len(comparison_data), 1),
                'efficiency': round(sum(p['efficiency'] for p in comparison_data) / len(comparison_data), 1),
                'age': round(sum(p['age'] or 0 for p in comparison_data) / len(comparison_data), 1) if all(p.get('age') for p in comparison_data) else None,
                'appearances': round(sum(p['appearances'] or 0 for p in comparison_data) / len(comparison_data), 1)
            }
        }
        
        return jsonify(response)
        
    except Exception as e:
        print(f"Error in player comparison: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


def calculate_percentile(value, all_values):
    """Calculate percentile rank of a value in a list"""
    if not all_values or value is None:
        return 0
    sorted_values = sorted(all_values)
    rank = sum(1 for v in sorted_values if v <= value)
    return round((rank / len(sorted_values)) * 100, 1)


@app.route('/players/compare')
@login_required
def players_compare_page():
    """Player comparison page"""
    # Get player names from query params
    players = request.args.getlist('players')
    return render_template('players_compare.html', user=current_user, initial_players=players)