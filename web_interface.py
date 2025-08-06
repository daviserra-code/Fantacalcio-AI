from flask import Flask, render_template, request, jsonify, session
from fantacalcio_data import League, AuctionHelper, SAMPLE_PLAYERS
from config import app_config
import json
import os
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FantacalcioAssistant at startup
try:
    from main import FantacalcioAssistant
    logger.info("FantacalcioAssistant imported successfully")
    # Initialize assistant immediately
    assistant = FantacalcioAssistant()
    logger.info("FantacalcioAssistant initialized successfully at startup")
except Exception as e:
    logger.warning(f"Failed to import/initialize FantacalcioAssistant: {e}")
    FantacalcioAssistant = None
    assistant = None

# Multilingual support
TRANSLATIONS = {
    'it': {
        'title': 'Assistente Fantacalcio Pro',
        'subtitle': 'Il tuo consulente per vincere il fantacalcio',
        'modes': {
            'classic': 'Classic',
            'mantra': 'Mantra', 
            'draft': 'Draft',
            'superscudetto': 'Superscudetto'
        },
        'historical': 'Statistiche Storiche',
        'search_placeholder': 'Cerca giocatore, squadra o campionato...',
        'participants': 'Partecipanti',
        'budget': 'Budget',
        'reset_chat': 'Reset Chat',
        'send': 'Invia',
        'welcome': 'Ciao! Sono il tuo assistente fantacalcio professionale.',
        'loading': 'Elaborando risposta...',
        'filters': 'Filtri',
        'all_roles': 'Tutti i ruoli',
        'goalkeeper': 'Portieri',
        'defender': 'Difensori', 
        'midfielder': 'Centrocampisti',
        'forward': 'Attaccanti'
    },
    'en': {
        'title': 'Fantasy Football Pro Assistant',
        'subtitle': 'Your consultant to win fantasy football',
        'modes': {
            'classic': 'Classic',
            'mantra': 'Mantra',
            'draft': 'Draft', 
            'superscudetto': 'Superscudetto'
        },
        'historical': 'Historical Stats',
        'search_placeholder': 'Search player, team or league...',
        'participants': 'Participants',
        'budget': 'Budget',
        'reset_chat': 'Reset Chat',
        'send': 'Send',
        'welcome': 'Hello! I am your professional fantasy football assistant.',
        'loading': 'Processing response...',
        'filters': 'Filters',
        'all_roles': 'All roles',
        'goalkeeper': 'Goalkeepers',
        'defender': 'Defenders',
        'midfielder': 'Midfielders', 
        'forward': 'Forwards'
    }
}

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'fantacalcio_secret_key_2024')

# Add request logging middleware
@app.before_request
def log_request_info():
    logger.info(f"Request: {request.method} {request.path} from {request.remote_addr}")

# Simple in-memory cache for performance
search_cache = {}
CACHE_EXPIRY = app_config.get('search_cache_expiry', 300)

# Simple rate limiting
rate_limit_storage = {}
RATE_LIMIT_REQUESTS = app_config.get('rate_limit_requests', 60)
RATE_LIMIT_WINDOW = app_config.get('rate_limit_window', 60)

def check_rate_limit(ip_address):
    """Simple rate limiting check"""
    now = datetime.now().timestamp()

    if ip_address not in rate_limit_storage:
        rate_limit_storage[ip_address] = []

    # Clean old requests
    rate_limit_storage[ip_address] = [
        req_time for req_time in rate_limit_storage[ip_address]
        if now - req_time < RATE_LIMIT_WINDOW
    ]

    # Check if under limit
    if len(rate_limit_storage[ip_address]) >= RATE_LIMIT_REQUESTS:
        return False

    # Add current request
    rate_limit_storage[ip_address].append(now)
    return True

@app.route('/health')
def health():
    return {
        'status': 'healthy', 
        'timestamp': datetime.now().isoformat(),
        'port': os.environ.get('PORT', 5000), 
        'assistant_available': FantacalcioAssistant is not None,
        'cache_size': len(search_cache)
    }, 200

@app.route('/metrics')
def metrics():
    """Basic metrics endpoint for monitoring"""
    cache_stats = assistant.get_cache_stats() if assistant else {}

    return {
        'uptime': 'running',
        'assistant_status': 'available' if assistant else 'not_initialized',
        'search_cache_entries': len(search_cache),
        'sample_players_count': len(SAMPLE_PLAYERS),
        'assistant_cache_stats': cache_stats
    }, 200

@app.route('/ping')
def ping():
    return 'pong', 200

@app.route('/')
def index():
    # Initialize session
    if 'session_id' not in session:
        session['session_id'] = os.urandom(16).hex()
        session.permanent = True
        logger.info(f"New session created: {session['session_id']}")

    lang = request.args.get('lang', 'it')
    if lang not in TRANSLATIONS:
        lang = 'it'
    session['lang'] = lang

    # Track page view
    logger.info(f"Page view: {session['session_id']}, lang: {lang}")

    return render_template('index.html', lang=lang, t=TRANSLATIONS[lang])

@app.route('/api/chat', methods=['POST'])
def chat():
    global assistant
    start_time = datetime.now()

    # Rate limiting check
    client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
    if not check_rate_limit(client_ip):
        logger.warning(f"Rate limit exceeded for IP: {client_ip}")
        return jsonify({'error': 'Too many requests. Please slow down.'}), 429

    try:
        if assistant is None:
            if FantacalcioAssistant is None:
                logger.error("FantacalcioAssistant not available")
                return jsonify({'error': 'Assistant service is temporarily unavailable. Please try again later.'}), 503
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid JSON data'}), 400

        message = data.get('message', '').strip()
        context = data.get('context', {})
        lang = session.get('lang', 'it')

        if not message:
            return jsonify({'error': 'Message required'}), 400

        # Enhanced context with session info
        context.update({
            'language': lang,
            'session_id': session.get('session_id', 'anonymous'),
            'timestamp': datetime.now().isoformat(),
            'user_agent': request.headers.get('User-Agent', ''),
        })

        logger.info(f"Processing chat message: {message[:50]}...")
        response = assistant.get_response(message, context)

        # Log response time
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"Chat response generated in {elapsed:.2f}s")

        # Get cache statistics for performance monitoring
        cache_stats = assistant.get_cache_stats() if assistant else {}

        return jsonify({
            'response': response,
            'response_time': elapsed,
            'timestamp': datetime.now().isoformat(),
            'cache_stats': cache_stats
        })

    except Exception as e:
        logger.error(f"Chat endpoint error: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred. Please try again.'}), 500

@app.route('/api/reset', methods=['POST'])
def reset_chat():
    global assistant
    if assistant is None:
        return jsonify({'message': 'Chat already reset'})
    message = assistant.reset_conversation()
    return jsonify({'message': message})

@app.route('/api/search', methods=['POST'])
def search_players():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid JSON data'}), 400

        query = data.get('query', '').lower().strip()
        role_filter = data.get('role', 'all')
        sort_by = data.get('sort', 'fantamedia')  # fantamedia, price, name

        if not query:
            return jsonify({'results': [], 'total': 0}), 200

        # Check cache first
        cache_key = f"{query}_{role_filter}_{sort_by}"
        now = datetime.now().timestamp()

        if cache_key in search_cache:
            cached_result, cached_time = search_cache[cache_key]
            if now - cached_time < CACHE_EXPIRY:
                logger.info(f"Returning cached search result for: {query}")
                return jsonify(cached_result)

        # Filter players based on search query and role
        results = []
        for player in SAMPLE_PLAYERS:
            match_name = query in player.name.lower()
            match_team = query in player.team.lower()
            match_role = role_filter == 'all' or player.role == role_filter

            if (match_name or match_team) and match_role:
                results.append({
                    'name': player.name,
                    'team': player.team,
                    'role': player.role,
                    'fantamedia': player.fantamedia,
                    'appearances': player.appearances,
                    'price': player.price
                })

        # Sort results
        if sort_by == 'fantamedia':
            results.sort(key=lambda x: x['fantamedia'], reverse=True)
        elif sort_by == 'price':
            results.sort(key=lambda x: x['price'], reverse=True)
        elif sort_by == 'name':
            results.sort(key=lambda x: x['name'])

        response_data = {
            'results': results[:20],  # Limit to top 20 results
            'total': len(results),
            'query': query,
            'cached': False
        }

        # Cache the result
        search_cache[cache_key] = (response_data, now)

        logger.info(f"Search completed: {query} - {len(results)} results")
        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        return jsonify({'error': 'Search failed. Please try again.'}), 500

@app.route('/api/league-setup', methods=['POST'])
def setup_league():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid JSON data'}), 400

        league_type = data.get('type', 'Classic')
        participants = int(data.get('participants', 8))
        budget = int(data.get('budget', 500))

        # Validate inputs
        if participants < 4 or participants > 20:
            return jsonify({'error': 'Participants must be between 4 and 20'}), 400
        if budget < 100 or budget > 2000:
            return jsonify({'error': 'Budget must be between 100 and 2000 credits'}), 400

        league = League(league_type, participants, budget)

        # Add strategic recommendations based on league setup
        recommendations = get_league_recommendations(league_type, participants, budget)

        response_data = {
            'league': {
                'type': league.league_type,
                'participants': league.participants,
                'budget': league.budget,
                'rules': league.rules
            },
            'recommendations': recommendations,
            'setup_timestamp': datetime.now().isoformat()
        }

        logger.info(f"League setup: {league_type} with {participants} participants and {budget} budget")
        return jsonify(response_data)

    except Exception as e:
        logger.error(f"League setup error: {str(e)}")
        return jsonify({'error': 'League setup failed. Please check your inputs.'}), 500

def get_league_recommendations(league_type, participants, budget):
    """Generate strategic recommendations based on league configuration"""
    recommendations = []

    if league_type == "Classic":
        recommendations.append("Focus on consistent players with high fantamedia")
        recommendations.append("Prioritize penalty takers and clean sheet defenders")

    elif league_type == "Mantra":
        recommendations.append("Invest heavily in creative midfielders for assist bonuses")
        recommendations.append("Defensive midfielders from strong teams get clean sheet bonuses")

    elif league_type == "Draft":
        recommendations.append("Take the best available player regardless of position early")
        recommendations.append("Stream defenses and goalkeepers based on fixtures")

    if budget >= 750:
        recommendations.append("High budget allows for premium players in every position")
    elif budget <= 400:
        recommendations.append("Focus on value picks and avoid the most expensive stars")

    if participants >= 12:
        recommendations.append("Deep leagues require more research on backup players")

    return recommendations

if __name__ == '__main__':
    try:
        port = int(os.environ.get('PORT', 80)) # Use port 80 for deployment or PORT env var
        debug_mode = os.environ.get('DEBUG', 'False').lower() == 'true'

        logger.info(f"Starting Fantasy Football Assistant Web Interface")
        logger.info(f"Server: 0.0.0.0:{port}")
        logger.info(f"Debug mode: {debug_mode}")
        logger.info(f"Assistant available: {FantacalcioAssistant is not None}")
        logger.info(f"Health check: http://0.0.0.0:{port}/health")
        logger.info(f"Metrics: http://0.0.0.0:{port}/metrics")

        # Set session configuration
        app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour

        app.run(
            host='0.0.0.0', 
            port=port, 
            debug=debug_mode, 
            threaded=True,
            use_reloader=False  # Prevent double startup in development
        )
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        raise


@app.route('/api/config', methods=['GET'])
def get_config():
    """Get client-safe configuration"""
    return jsonify({
        'features': {
            'voice_input': app_config.get('enable_voice_input', True),
            'real_time_updates': app_config.get('enable_real_time_updates', True),
            'advanced_analytics': app_config.get('enable_advanced_analytics', True)
        },
        'ui': {
            'theme': app_config.get('theme', 'dark'),
            'language': app_config.get('language', 'it')
        }
    })

@app.route('/api/analytics', methods=['POST'])
def track_analytics():
    """Simple analytics endpoint"""
    try:
        data = request.get_json()
        event_type = data.get('event', 'page_view')
        event_data = data.get('data', {})

        # Log analytics event
        logger.info(f"Analytics: {event_type} - {json.dumps(event_data)}")

        return jsonify({'status': 'tracked'}), 200
    except Exception as e:
        logger.error(f"Analytics error: {str(e)}")
        return jsonify({'error': 'Tracking failed'}), 500

@app.route('/api/player-analysis/<player_name>', methods=['GET'])
def get_player_analysis(player_name):
    """Get detailed player analysis"""
    try:
        from player_analytics import PlayerAnalytics
        from fantacalcio_data import SAMPLE_PLAYERS

        # Find player
        player = next((p for p in SAMPLE_PLAYERS if p.name.lower() == player_name.lower()), None)
        if not player:
            return jsonify({'error': 'Player not found'}), 404

        analytics = PlayerAnalytics()

        analysis = {
            'player': {
                'name': player.name,
                'team': player.team,
                'role': player.role,
                'fantamedia': player.fantamedia,
                'price': player.price,
                'appearances': player.appearances
            },
            'efficiency_score': analytics.get_player_efficiency_score(player),
            'injury_risk': analytics.get_injury_risk_analysis(player),
            'role_comparison': analytics.get_role_statistics(player.role)
        }

        return jsonify(analysis)

    except Exception as e:
        logger.error(f"Player analysis error: {str(e)}")
        return jsonify({'error': 'Analysis failed'}), 500

@app.route('/api/formation-optimizer', methods=['POST'])
def optimize_formation():
    """Get optimal formation suggestions"""
    try:
        from player_analytics import PlayerAnalytics

        data = request.get_json()
        budget = data.get('budget', 500)
        league_type = data.get('league_type', 'Classic')

        analytics = PlayerAnalytics()
        suggestions = analytics.suggest_formation_optimization(budget, league_type)

        return jsonify({
            'budget': budget,
            'league_type': league_type,
            'suggestions': suggestions,
            'total_budget_used': sum(s['budget'] for s in suggestions.values())
        })

    except Exception as e:
        logger.error(f"Formation optimization error: {str(e)}")
        return jsonify({'error': 'Optimization failed'}), 500

@app.route('/api/fixtures', methods=['GET'])
def get_fixtures():
    """Get upcoming fixtures and recommendations"""
    try:
        from match_tracker import MatchTracker

        tracker = MatchTracker()
        recommendations = tracker.get_gameweek_recommendations()

        return jsonify({
            'gameweek_recommendations': recommendations,
            'updated_at': datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Fixtures error: {str(e)}")
        return jsonify({'error': 'Fixtures data unavailable'}), 500

@app.route('/api/player-fixtures/<player_name>/<team>', methods=['GET'])
def get_player_fixtures(player_name, team):
    """Get fixture analysis for a specific player"""
    try:
        from match_tracker import MatchTracker

        tracker = MatchTracker()
        analysis = tracker.get_player_fixture_analysis(player_name, team)

        return jsonify(analysis)

    except Exception as e:
        logger.error(f"Player fixtures error: {str(e)}")
        return jsonify({'error': 'Fixture analysis failed'}), 500

@app.route('/api/user-analytics', methods=['GET'])
def get_user_analytics():
    """Get user analytics dashboard data"""
    try:
        session_id = session.get('session_id', 'anonymous')

        # Mock analytics data - in production this would come from database
        analytics_data = {
            'session_id': session_id,
            'most_searched_players': [
                {'name': 'Osimhen', 'searches': 15, 'team': 'Napoli'},
                {'name': 'Vlahovic', 'searches': 12, 'team': 'Juventus'},
                {'name': 'Lautaro', 'searches': 10, 'team': 'Inter'}
            ],
            'favorite_positions': [
                {'position': 'A', 'percentage': 35},
                {'position': 'C', 'percentage': 30},
                {'position': 'D', 'percentage': 25},
                {'position': 'P', 'percentage': 10}
            ],
            'league_preferences': {
                'Classic': 45,
                'Mantra': 25,
                'Draft': 20,
                'Superscudetto': 10
            },
            'budget_distribution': {
                'low': 20,    # <400 credits
                'medium': 60, # 400-700 credits
                'high': 20    # >700 credits
            },
            'performance_metrics': {
                'avg_response_time': 2.3,
                'cache_hit_rate': 78.5,
                'successful_queries': 142
            }
        }

        return jsonify(analytics_data)

    except Exception as e:
        logger.error(f"User analytics error: {str(e)}")
        return jsonify({'error': 'Analytics data unavailable'}), 500

@app.route('/api/mobile-config', methods=['GET'])
def get_mobile_config():
    """Get mobile-optimized configuration"""
    try:
        user_agent = request.headers.get('User-Agent', '').lower()
        is_mobile = any(device in user_agent for device in ['mobile', 'android', 'iphone', 'ipad'])

        mobile_config = {
            'is_mobile': is_mobile,
            'touch_optimized': is_mobile,
            'reduced_animations': is_mobile,
            'compact_layout': is_mobile,
            'swipe_gestures': is_mobile,
            'pull_to_refresh': is_mobile,
            'haptic_feedback': is_mobile and 'iphone' in user_agent,
            'recommended_features': {
                'voice_input': is_mobile,
                'quick_actions': True,
                'favorites': True,
                'offline_mode': is_mobile
            }
        }

        return jsonify(mobile_config)

    except Exception as e:
        logger.error(f"Mobile config error: {str(e)}")
        return jsonify({'error': 'Mobile config failed'}), 500



@app.route('/api/player-comparison', methods=['POST'])
def compare_players():
    """Compare multiple players side by side"""
    try:
        data = request.get_json()
        if not data or 'players' not in data:
            return jsonify({'error': 'Player list required'}), 400

        player_names = data.get('players', [])
        if len(player_names) < 2 or len(player_names) > 4:
            return jsonify({'error': 'Compare 2-4 players only'}), 400

        from fantacalcio_data import SAMPLE_PLAYERS

        comparison_data = []
        for name in player_names:
            player = next((p for p in SAMPLE_PLAYERS if p.name.lower() == name.lower()), None)
            if player:
                comparison_data.append({
                    'name': player.name,
                    'team': player.team,
                    'role': player.role,
                    'fantamedia': player.fantamedia,
                    'price': player.price,
                    'appearances': player.appearances,
                    'value_ratio': round(player.fantamedia / player.price * 100, 2) if player.price > 0 else 0,
                    'games_per_season': round(player.appearances / 38 * 100, 1)
                })

        if not comparison_data:
            return jsonify({'error': 'No valid players found'}), 404

        return jsonify({
            'comparison': comparison_data,
            'metrics': {
                'best_value': max(comparison_data, key=lambda x: x['value_ratio'])['name'],
                'highest_fantamedia': max(comparison_data, key=lambda x: x['fantamedia'])['name'],
                'most_reliable': max(comparison_data, key=lambda x: x['appearances'])['name']
            }
        })

    except Exception as e:
        logger.error(f"Player comparison error: {str(e)}")
        return jsonify({'error': 'Comparison failed'}), 500

@app.route('/api/performance-charts/<chart_type>', methods=['GET'])
def get_performance_charts(chart_type):
    """Get chart data for data visualization"""
    try:
        from fantacalcio_data import SAMPLE_PLAYERS

        if chart_type == 'fantamedia_by_role':
            role_data = {}
            for player in SAMPLE_PLAYERS:
                if player.role not in role_data:
                    role_data[player.role] = []
                role_data[player.role].append(player.fantamedia)

            chart_data = {
                'type': 'bar',
                'data': {
                    'labels': list(role_data.keys()),
                    'datasets': [{
                        'label': 'Media Fantamedia per Ruolo',
                        'data': [round(sum(values)/len(values), 2) for values in role_data.values()],
                        'backgroundColor': ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4']
                    }]
                }
            }

        elif chart_type == 'price_distribution':
            price_ranges = {'0-20': 0, '21-30': 0, '31-40': 0, '40+': 0}
            for player in SAMPLE_PLAYERS:
                if player.price <= 20:
                    price_ranges['0-20'] += 1
                elif player.price <= 30:
                    price_ranges['21-30'] += 1
                elif player.price <= 40:
                    price_ranges['31-40'] += 1
                else:
                    price_ranges['40+'] += 1

            chart_data = {
                'type': 'pie',
                'data': {
                    'labels': list(price_ranges.keys()),
                    'datasets': [{
                        'label': 'Distribuzione Prezzi',
                        'data': list(price_ranges.values()),
                        'backgroundColor': ['#FF9F43', '#26de81', '#2d98da', '#a55eea']
                    }]
                }
            }

        elif chart_type == 'value_efficiency':
            efficiency_data = []
            for player in SAMPLE_PLAYERS:
                if player.price > 0:
                    efficiency = player.fantamedia / player.price
                    efficiency_data.append({
                        'x': player.price,
                        'y': player.fantamedia,
                        'r': efficiency * 10,
                        'name': player.name
                    })

            chart_data = {
                'type': 'bubble',
                'data': {
                    'datasets': [{
                        'label': 'Efficienza Prezzo/Fantamedia',
                        'data': efficiency_data[:20],  # Limit to top 20
                        'backgroundColor': '#45B7D1'
                    }]
                }
            }

        else:
            return jsonify({'error': 'Invalid chart type'}), 400

        return jsonify(chart_data)

    except Exception as e:
        logger.error(f"Chart data error: {str(e)}")
        return jsonify({'error': 'Chart generation failed'}), 500

@app.route('/api/export-data', methods=['POST'])
def export_data():
    """Export user data in various formats"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Export parameters required'}), 400

        export_type = data.get('type', 'csv')
        data_type = data.get('data_type', 'players')

        if data_type == 'players':
            from fantacalcio_data import SAMPLE_PLAYERS

            if export_type == 'csv':
                import csv
                import io

                output = io.StringIO()
                writer = csv.writer(output)
                writer.writerow(['Name', 'Team', 'Role', 'Fantamedia', 'Price', 'Appearances'])

                for player in SAMPLE_PLAYERS:
                    writer.writerow([player.name, player.team, player.role, 
                                   player.fantamedia, player.price, player.appearances])

                return jsonify({
                    'format': 'csv',
                    'data': output.getvalue(),
                    'filename': f'fantacalcio_players_{datetime.now().strftime("%Y%m%d")}.csv'
                })

        return jsonify({'error': 'Export type not supported'}), 400

    except Exception as e:
        logger.error(f"Export error: {str(e)}")
        return jsonify({'error': 'Export failed'}), 500

@app.errorhandler(404)
def not_found(error):
    logger.warning(f"404 error: {request.path}")
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"500 error: {str(error)}")
    return jsonify({'error': 'Internal server error'}), 500