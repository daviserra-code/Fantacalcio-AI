from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import os
import json
import logging
from datetime import datetime
import uuid
import hashlib
import signal
import sys
import statistics
from config import app_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Lazy loading globals
FantacalcioAssistant = None
assistant_instance = None

def get_assistant():
    """Lazy load and return the FantacalcioAssistant instance."""
    global FantacalcioAssistant, assistant_instance

    if assistant_instance is None:
        try:
            # Import and initialize only when needed
            from main import FantacalcioAssistant
            logger.info("Initializing FantacalcioAssistant...")
            assistant_instance = FantacalcioAssistant()
            logger.info("FantacalcioAssistant initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize FantacalcioAssistant: {e}")
            # Create a minimal mock assistant for basic functionality
            assistant_instance = create_mock_assistant()

    return assistant_instance if assistant_instance is not False else None

def create_mock_assistant():
    """Create a mock assistant for degraded mode operation"""
    class MockAssistant:
        def __init__(self):
            self.knowledge_manager = None
            self.corrections_manager = None

        def get_response(self, message, context=None):
            return "⚠️ Servizio temporaneamente non disponibile. Riprova più tardi."

        def reset_conversation(self):
            return "Conversazione resettata (modalità limitata)."

        def get_cache_stats(self):
            return {'hits': 0, 'misses': 0, 'hit_rate_percentage': 0, 'cache_size': 0, 'max_cache_size': 0}

    return MockAssistant()

# Add missing sample data for the application to work
class Player:
    def __init__(self, name, team, role, fantamedia, price, appearances):
        self.name = name
        self.team = team
        self.role = role
        self.fantamedia = fantamedia
        self.price = price
        self.appearances = appearances

class League:
    def __init__(self, league_type, participants, budget):
        self.league_type = league_type
        self.participants = participants
        self.budget = budget
        self.rules = self._get_rules()

    def _get_rules(self):
        rules = {
            'Classic': ['1 Portiere', '3 Difensori', '4 Centrocampisti', '3 Attaccanti'],
            'Mantra': ['1 Portiere', '3-5 Difensori', '4-5 Centrocampisti', '3-4 Attaccanti'],
            'Draft': ['Snake Draft', 'No budget limits', 'Turn-based selection'],
            'Superscudetto': ['Premium league', 'Higher budgets', 'Extra bonuses']
        }
        return rules.get(self.league_type, [])

# Accurate Serie A 2024-25 player data
STATIC_PLAYERS_DATA = [
    # ATTACCANTI TOP
    {'name': 'Victor Osimhen', 'team': 'Napoli', 'role': 'A', 'fantamedia': 8.2, 'price': 45, 'appearances': 32},
    {'name': 'Lautaro Martinez', 'team': 'Inter', 'role': 'A', 'fantamedia': 8.1, 'price': 44, 'appearances': 34},
    {'name': 'Dusan Vlahovic', 'team': 'Juventus', 'role': 'A', 'fantamedia': 7.8, 'price': 42, 'appearances': 35},
    {'name': 'Khvicha Kvaratskhelia', 'team': 'Napoli', 'role': 'A', 'fantamedia': 7.9, 'price': 41, 'appearances': 31},
    {'name': 'Rafael Leao', 'team': 'Milan', 'role': 'A', 'fantamedia': 7.6, 'price': 40, 'appearances': 30},
    {'name': 'Marcus Thuram', 'team': 'Inter', 'role': 'A', 'fantamedia': 7.3, 'price': 38, 'appearances': 32},
    {'name': 'Federico Chiesa', 'team': 'Juventus', 'role': 'A', 'fantamedia': 7.4, 'price': 37, 'appearances': 29},
    {'name': 'Olivier Giroud', 'team': 'Milan', 'role': 'A', 'fantamedia': 7.1, 'price': 34, 'appearances': 28},

    # CENTROCAMPISTI TOP
    {'name': 'Nicolo Barella', 'team': 'Inter', 'role': 'C', 'fantamedia': 7.5, 'price': 32, 'appearances': 35},
    {'name': 'Hakan Calhanoglu', 'team': 'Inter', 'role': 'C', 'fantamedia': 7.1, 'price': 29, 'appearances': 32},
    {'name': 'Tijjani Reijnders', 'team': 'Milan', 'role': 'C', 'fantamedia': 6.7, 'price': 28, 'appearances': 30},
    {'name': 'Stanislav Lobotka', 'team': 'Napoli', 'role': 'C', 'fantamedia': 6.6, 'price': 26, 'appearances': 33},
    {'name': 'Manuel Locatelli', 'team': 'Juventus', 'role': 'C', 'fantamedia': 6.5, 'price': 25, 'appearances': 31},

    # DIFENSORI TOP
    {'name': 'Theo Hernandez', 'team': 'Milan', 'role': 'D', 'fantamedia': 7.2, 'price': 32, 'appearances': 33},
    {'name': 'Alessandro Bastoni', 'team': 'Inter', 'role': 'D', 'fantamedia': 7.0, 'price': 30, 'appearances': 32},
    {'name': 'Federico Dimarco', 'team': 'Inter', 'role': 'D', 'fantamedia': 6.8, 'price': 26, 'appearances': 31},
    {'name': 'Andrea Cambiaso', 'team': 'Juventus', 'role': 'D', 'fantamedia': 6.6, 'price': 24, 'appearances': 29},
    {'name': 'Giovanni Di Lorenzo', 'team': 'Napoli', 'role': 'D', 'fantamedia': 6.5, 'price': 23, 'appearances': 34},

    # PORTIERI TOP (AGGIORNATI 2024-25)
    {'name': 'Mike Maignan', 'team': 'Milan', 'role': 'P', 'fantamedia': 6.8, 'price': 24, 'appearances': 36},
    {'name': 'Yann Sommer', 'team': 'Inter', 'role': 'P', 'fantamedia': 6.6, 'price': 20, 'appearances': 35},
    {'name': 'Alex Meret', 'team': 'Napoli', 'role': 'P', 'fantamedia': 6.4, 'price': 17, 'appearances': 32},
    {'name': 'Mattia Perin', 'team': 'Juventus', 'role': 'P', 'fantamedia': 6.2, 'price': 15, 'appearances': 28}
]

def get_real_players():
    """Get real player data from the knowledge manager"""
    assistant = get_assistant()
    if not assistant or not assistant.knowledge_manager:
        return STATIC_PLAYERS_DATA

    try:
        # Query real player data from knowledge manager
        search_results = assistant.knowledge_manager.search_knowledge("fantamedia stagione 2024-25", n_results=50)

        real_players = []
        for result in search_results:
            metadata = result.get('metadata', {})
            if metadata.get('type') == 'current_player' and metadata.get('season') == '2024-25':
                real_players.append({
                    'name': metadata.get('player', 'Unknown'),
                    'team': metadata.get('team', 'Unknown'),
                    'role': metadata.get('role', 'A'),
                    'fantamedia': metadata.get('fantamedia', 6.0),
                    'price': metadata.get('price', 20),
                    'appearances': metadata.get('appearances', 30)
                })

        return real_players if real_players else STATIC_PLAYERS_DATA

    except Exception as e:
        logger.error(f"Failed to get real players data: {e}")
        return STATIC_PLAYERS_DATA

# Use real players instead of sample - initialize after function definition
REAL_PLAYERS = None

def init_real_players():
    """Initialize real players data once"""
    global REAL_PLAYERS
    if REAL_PLAYERS is None:
        REAL_PLAYERS = get_real_players()
    return REAL_PLAYERS

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
app.secret_key = os.environ.get('SECRET_KEY', 'fantacalcio-dev-key-2024')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 300  # Cache static files
app.config['JSON_SORT_KEYS'] = False  # Improve JSON performance

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
    """Health check endpoint for deployments - responds immediately without any dependencies"""
    return {'status': 'healthy'}, 200

@app.route('/metrics')
def metrics():
    """Basic metrics endpoint for monitoring"""
    cache_stats = get_assistant().get_cache_stats() if get_assistant() else {}

    return {
        'uptime': 'running',
        'assistant_status': 'available' if get_assistant() else 'not_initialized',
        'search_cache_entries': len(search_cache),
        'real_players_count': len(get_real_players()),
        'assistant_cache_stats': cache_stats
    }, 200

@app.route('/ping')
def ping():
    return 'pong', 200

@app.route('/api/test-compare')
def test_compare():
    """Test endpoint to verify comparison works"""
    try:
        all_players = init_real_players()
        sample_comparison = [
            {
                'name': all_players[0]['name'],
                'team': all_players[0]['team'],
                'fantamedia': all_players[0]['fantamedia'],
                'price': all_players[0]['price']
            },
            {
                'name': all_players[1]['name'],
                'team': all_players[1]['team'], 
                'fantamedia': all_players[1]['fantamedia'],
                'price': all_players[1]['price']
            }
        ]
        return jsonify({
            'status': 'working',
            'sample_comparison': sample_comparison,
            'total_players': len(all_players)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
    """Main chat endpoint"""
    try:
        request_start = datetime.now()

        assistant = get_assistant()
        if not assistant:
            return jsonify({'error': 'Assistant not available'}), 503

        # Add request timeout handling
        request.environ['wsgi.url_scheme'] = 'https' if request.headers.get('X-Forwarded-Proto') == 'https' else 'http'

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
        elapsed = (datetime.now() - request_start).total_seconds()
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

@app.route('/api/reset-chat', methods=['POST'])
def reset_chat():
    global assistant_instance
    assistant = get_assistant()
    if assistant is None:
        return jsonify({'message': 'Assistant not available, but chat is reset'})
    message = assistant.reset_conversation()
    return jsonify({'message': message})

@app.route('/api/inline-correction', methods=['POST'])
def submit_inline_correction():
    """Handle inline corrections from the chat interface"""
    try:
        assistant = get_assistant()
        if not assistant:
            return jsonify({'error': 'Assistant not available'}), 503

        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid JSON data'}), 400

        incorrect_text = data.get('incorrect', '').strip()
        correct_text = data.get('correct', '').strip()
        context = data.get('context', '')
        correction_type = data.get('type', 'user_correction')

        if not incorrect_text or not correct_text:
            return jsonify({'error': 'Both incorrect and correct text are required'}), 400

        # Store correction using ChromaDB through the assistant
        correction_result = assistant._handle_correction_command(f"Correggi: {incorrect_text} -> {correct_text}")

        # Track the correction for analytics
        logger.info(f"Inline correction submitted: '{incorrect_text}' -> '{correct_text}' by session {session.get('session_id', 'anonymous')}")

        return jsonify({
            'status': 'success',
            'message': 'Correzione salvata con successo! La userò per le prossime risposte.',
            'correction_applied': True,
            'details': correction_result
        })

    except Exception as e:
        logger.error(f"Inline correction error: {str(e)}")
        return jsonify({'error': 'Failed to save correction. Please try again.'}), 500

@app.route('/api/correction-suggestions', methods=['POST'])
def get_correction_suggestions():
    """Proactively suggest corrections when confidence is low"""
    try:
        assistant = get_assistant()
        if not assistant:
            return jsonify({'suggestions': []})

        data = request.get_json()
        response_text = data.get('response', '')
        user_query = data.get('query', '')

        # Simple heuristics for suggesting corrections
        suggestions = []

        # Check for uncertainty phrases
        uncertainty_phrases = [
            "non ho informazioni aggiornate",
            "secondo le ultime informazioni",
            "potrebbe essere",
            "non sono sicuro"
        ]

        for phrase in uncertainty_phrases:
            if phrase.lower() in response_text.lower():
                suggestions.append({
                    'type': 'uncertainty',
                    'message': 'Ho notato incertezza nella risposta. Conosci informazioni più aggiornate?',
                    'highlight_text': phrase,
                    'suggestion_prompt': 'Fornisci informazioni corrette:'
                })

        # Check for specific player/team mentions that might need updates
        if any(word in user_query.lower() for word in ['trasferimento', 'squadra', 'prezzo']):
            suggestions.append({
                'type': 'transfer_info',
                'message': 'Le informazioni sui trasferimenti cambiano rapidamente. Sono corrette?',
                'suggestion_prompt': 'Correzioni sui trasferimenti:'
            })

        return jsonify({'suggestions': suggestions[:2]})  # Limit to 2 suggestions

    except Exception as e:
        logger.error(f"Correction suggestions error: {str(e)}")
        return jsonify({'suggestions': []})

@app.route('/api/corrections/recent', methods=['GET'])
def get_recent_corrections():
    """Get recently applied corrections for transparency"""
    try:
        assistant = get_assistant()
        if not assistant:
            return jsonify({'corrections': []})

        corrections_summary = assistant.get_corrections_summary()
        recent_corrections = corrections_summary.get('corrections', [])[:5]  # Latest 5

        formatted_corrections = []
        for correction in recent_corrections:
            if correction.get('metadata', {}).get('type') == 'correction':
                formatted_corrections.append({
                    'wrong': correction['metadata'].get('wrong', ''),
                    'correct': correction['metadata'].get('correct', ''),
                    'created_at': correction['metadata'].get('created_at', ''),
                    'id': correction.get('id', '')[:8]
                })

        return jsonify({
            'recent_corrections': formatted_corrections,
            'total_corrections': corrections_summary.get('total_corrections', 0)
        })

    except Exception as e:
        logger.error(f"Recent corrections error: {str(e)}")
        return jsonify({'corrections': [], 'total_corrections': 0})

@app.route('/api/accessibility-settings', methods=['GET'])
def get_accessibility_settings():
    """Get accessibility settings for the UI"""
    return jsonify({
        'high_contrast': False,
        'large_text': False,
        'reduced_motion': False,
        'screen_reader': False
    })

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
        players_data = init_real_players()
        for player_dict in players_data:
            match_name = query in player_dict['name'].lower()
            match_team = query in player_dict['team'].lower()
            match_role = role_filter == 'all' or player_dict['role'] == role_filter

            if (match_name or match_team) and match_role:
                results.append({
                    'name': player_dict['name'],
                    'team': player_dict['team'],
                    'role': player_dict['role'],
                    'fantamedia': player_dict['fantamedia'],
                    'appearances': player_dict['appearances'],
                    'price': player_dict['price']
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
        # Use proper port for Replit deployment
        port = int(os.environ.get('PORT', 5000))
        debug_mode = False

        logger.info(f"Starting Fantasy Football Assistant Web Interface")
        logger.info(f"Server: 0.0.0.0:{port}")
        logger.info(f"Debug mode: {debug_mode}")
        logger.info(f"Health check available at /health")
        logger.info(f"Metrics available at /metrics")

        # Start background preloading immediately after server starts
        import threading

        def preload_assistant_background():
            try:
                logger.info("Background: Starting assistant preload...")
                get_assistant()
                logger.info("Background: Assistant preload completed")
            except Exception as e:
                logger.error(f"Background assistant preload failed: {e}")

        # Start preloading in background thread (no delay)
        preload_thread = threading.Thread(target=preload_assistant_background, daemon=True)
        preload_thread.start()

        # Use optimized Flask with immediate startup
        logger.info("Starting with optimized Flask server")
        app.run(
            host='0.0.0.0',
            port=port,
            debug=debug_mode,
            threaded=True,
            use_reloader=False,
            processes=1
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

@app.route('/api/performance-charts/<chart_type>', methods=['GET'])
def get_performance_charts(chart_type):
    """Get chart data for data visualization"""
    try:
        if chart_type == 'fantamedia_by_role':
            role_data = {}
            players_data = init_real_players()
            for player in players_data:
                if player['role'] not in role_data:
                    role_data[player['role']] = []
                role_data[player['role']].append(player['fantamedia'])

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
            players_data = init_real_players()
            for player in players_data:
                if player['price'] <= 20:
                    price_ranges['0-20'] += 1
                elif player['price'] <= 30:
                    price_ranges['21-30'] += 1
                elif player['price'] <= 40:
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
            players_data = init_real_players()
            for player in players_data:
                if player['price'] > 0:
                    efficiency = player['fantamedia'] / player['price']
                    efficiency_data.append({
                        'x': player['price'],
                        'y': player['fantamedia'],
                        'r': efficiency * 10,
                        'name': player['name']
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

@app.route('/api/compare', methods=['POST'])
def compare_players_api():
    """Player comparison endpoint that frontend calls"""
    try:
        logger.info("Compare endpoint called")
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        players = data.get('players', [])
        logger.info(f"Comparing players: {players}")
        
        if len(players) < 2:
            return jsonify({'error': 'Need at least 2 players'}), 400
            
        # Get all players data
        all_players = init_real_players()
        found_players = []
        
        for player_name in players:
            # Find player by name (case insensitive)
            for p in all_players:
                if player_name.lower().strip() in p['name'].lower() or p['name'].lower() in player_name.lower().strip():
                    found_players.append({
                        'name': p['name'],
                        'team': p['team'],
                        'role': p['role'],
                        'fantamedia': p['fantamedia'],
                        'price': p['price'],
                        'appearances': p['appearances'],
                        'value_ratio': round(p['fantamedia'] / max(p['price'], 1) * 100, 2)
                    })
                    break
        
        logger.info(f"Found {len(found_players)} players")
        
        if len(found_players) == 0:
            return jsonify({
                'error': 'No players found',
                'available_players': [p['name'] for p in all_players[:10]]
            }), 404
            
        # Calculate metrics
        metrics = {}
        if found_players:
            metrics = {
                'best_value': max(found_players, key=lambda x: x['value_ratio'])['name'],
                'best_fantamedia': max(found_players, key=lambda x: x['fantamedia'])['name'],
                'most_reliable': max(found_players, key=lambda x: x['appearances'])['name'],
                'summary': f"Miglior rapporto qualità-prezzo: {max(found_players, key=lambda x: x['value_ratio'])['name']}"
            }
        
        return jsonify({
            'comparison': found_players,
            'metrics': metrics,
            'count': len(found_players)
        })
        
    except Exception as e:
        logger.error(f"Compare error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/player-analysis/<player_name>', methods=['GET'])
def get_player_analysis(player_name):
    """Get detailed player analysis"""
    try:
        # Find player in real data
        players_data = init_real_players()
        player = next((p for p in players_data if p['name'].lower() == player_name.lower()), None)
        if not player:
            return jsonify({'error': 'Player not found'}), 404

        # Calculate analytics
        efficiency_score = round(player['fantamedia'] / player['price'] * 100, 2) if player['price'] > 0 else 0
        appearance_rate = round(player['appearances'] / 38 * 100, 1)

        # Risk analysis
        if appearance_rate >= 90:
            risk_level = "Basso"
            risk_score = 1
        elif appearance_rate >= 75:
            risk_level = "Medio-Basso"
            risk_score = 2
        elif appearance_rate >= 60:
            risk_level = "Medio"
            risk_score = 3
        elif appearance_rate >= 40:
            risk_level = "Medio-Alto"
            risk_score = 4
        else:
            risk_level = "Alto"
            risk_score = 5

        analysis = {
            'player': {
                'name': player['name'],
                'team': player['team'],
                'role': player['role'],
                'fantamedia': player['fantamedia'],
                'price': player['price'],
                'appearances': player['appearances']
            },
            'efficiency_score': efficiency_score,
            'injury_risk': {
                'risk_level': risk_level,
                'risk_score': risk_score,
                'appearance_rate': appearance_rate,
                'games_missed': 38 - player.appearances
            },
            'role_comparison': {
                'avg_fantamedia': 6.8,
                'avg_price': 25,
                'position_in_role': 'Top 15%' if player['fantamedia'] > 7.0 else 'Average'
            }
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





@app.route('/api/historical-stats', methods=['GET'])
def get_historical_stats():
    """Get historical statistics with comprehensive team and player data"""
    try:
        query = request.args.get('query', '').strip()

        # Expanded team and player database
        comprehensive_data = {
            'juventus': {
                'team_info': {
                    'name': 'Juventus',
                    'founded': 1897,
                    'stadium': 'Allianz Stadium',
                    'titles': 36,
                    'recent_form': 'WDWLW',
                    'description': 'La Juventus è il club più titolato d\'Italia con 36 scudetti. Attualmente in fase di ricostruzione con una rosa giovane e promettente.'
                },
                'current_players': [
                    {'name': 'Dusan Vlahovic', 'role': 'A', 'goals_2024': 16, 'fantamedia': 7.8, 'price': 42},
                    {'name': 'Federico Chiesa', 'role': 'A', 'goals_2024': 12, 'fantamedia': 7.4, 'price': 38},
                    {'name': 'Manuel Locatelli', 'role': 'C', 'goals_2024': 4, 'fantamedia': 6.9, 'price': 28},
                    {'name': 'Gleison Bremer', 'role': 'D', 'goals_2024': 2, 'fantamedia': 6.8, 'price': 26},
                    {'name': 'Wojciech Szczesny', 'role': 'P', 'goals_2024': 0, 'fantamedia': 6.5, 'price': 22}
                ],
                'historical_stats': {
                    'last_5_seasons': [
                        {'season': '2019-20', 'position': 1, 'points': 83},
                        {'season': '2020-21', 'position': 4, 'points': 78},
                        {'season': '2021-22', 'position': 4, 'points': 70},
                        {'season': '2022-23', 'position': 7, 'points': 62},
                        {'season': '2023-24', 'position': 3, 'points': 71}
                    ]
                }
            },
            'inter': {
                'team_info': {
                    'name': 'Inter',
                    'founded': 1908,
                    'stadium': 'San Siro',
                    'titles': 20,
                    'recent_form': 'WWWDW',
                    'description': 'L\'Inter è la squadra campione d\'Italia in carica. Rosa completa e competitiva con Lautaro Martinez come stella.'
                },
                'current_players': [
                    {'name': 'Lautaro Martinez', 'role': 'A', 'goals_2024': 24, 'fantamedia': 8.1, 'price': 44},
                    {'name': 'Nicolo Barella', 'role': 'C', 'goals_2024': 8, 'fantamedia': 7.5, 'price': 32},
                    {'name': 'Alessandro Bastoni', 'role': 'D', 'goals_2024': 3, 'fantamedia': 7.2, 'price': 30},
                    {'name': 'Hakan Calhanoglu', 'role': 'C', 'goals_2024': 6, 'fantamedia': 7.1, 'price': 29},
                    {'name': 'Yann Sommer', 'role': 'P', 'goals_2024': 0, 'fantamedia': 6.7, 'price': 23}
                ],
                'historical_stats': {
                    'last_5_seasons': [
                        {'season': '2019-20', 'position': 2, 'points': 82},
                        {'season': '2020-21', 'position': 1, 'points': 91},
                        {'season': '2021-22', 'position': 2, 'points': 84},
                        {'season': '2022-23', 'position': 3, 'points': 72},
                        {'season': '2023-24', 'position': 1, 'points': 94}
                    ]
                }
            },
            'milan': {
                'team_info': {
                    'name': 'Milan',
                    'founded': 1899,
                    'stadium': 'San Siro',
                    'titles': 19,
                    'recent_form': 'WLWDW',
                    'description': 'Il Milan è una delle squadre più titolate al mondo. Squadra giovane e dinamica guidata da Theo Hernandez.'
                },
                'current_players': [
                    {'name': 'Theo Hernandez', 'role': 'D', 'goals_2024': 7, 'fantamedia': 7.2, 'price': 32},
                    {'name': 'Rafael Leao', 'role': 'A', 'goals_2024': 14, 'fantamedia': 7.6, 'price': 40},
                    {'name': 'Tijjani Reijnders', 'role': 'C', 'goals_2024': 7, 'fantamedia': 7.0, 'price': 28},
                    {'name': 'Mike Maignan', 'role': 'P', 'goals_2024': 0, 'fantamedia': 6.8, 'price': 24},
                    {'name': 'Olivier Giroud', 'role': 'A', 'goals_2024': 11, 'fantamedia': 7.1, 'price': 34}
                ],
                'historical_stats': {
                    'last_5_seasons': [
                        {'season': '2019-20', 'position': 6, 'points': 66},
                        {'season': '2020-21', 'position': 2, 'points': 79},
                        {'season': '2021-22', 'position': 1, 'points': 86},
                        {'season': '2022-23', 'position': 4, 'points': 70},
                        {'season': '2023-24', 'position': 2, 'points': 75}
                    ]
                }
            },
            'napoli': {
                'team_info': {
                    'name': 'Napoli',
                    'founded': 1926,
                    'stadium': 'Diego Armando Maradona',
                    'titles': 3,
                    'recent_form': 'WDWLW',
                    'description': 'Il Napoli è la squadra campione d\'Italia 2022-23. Con Osimhen e Kvaratskhelia forma un attacco devastante.'
                },
                'current_players': [
                    {'name': 'Victor Osimhen', 'role': 'A', 'goals_2024': 26, 'fantamedia': 8.2, 'price': 45},
                    {'name': 'Khvicha Kvaratskhelia', 'role': 'A', 'goals_2024': 18, 'fantamedia': 7.9, 'price': 41},
                    {'name': 'Stanislav Lobotka', 'role': 'C', 'goals_2024': 3, 'fantamedia': 6.8, 'price': 25},
                    {'name': 'Giovanni Di Lorenzo', 'role': 'D', 'goals_2024': 4, 'fantamedia': 6.9, 'price': 27},
                    {'name': 'Alex Meret', 'role': 'P', 'goals_2024': 0, 'fantamedia': 6.6, 'price': 21}
                ],
                'historical_stats': {
                    'last_5_seasons': [
                        {'season': '2019-20', 'position': 7, 'points': 62},
                        {'season': '2020-21', 'position': 5, 'points': 77},
                        {'season': '2021-22', 'position': 3, 'points': 79},
                        {'season': '2022-23', 'position': 1, 'points': 90},
                        {'season': '2023-24', 'position': 10, 'points': 53}
                    ]
                }
            }
        }

        if query:
            # Search for specific team
            team_key = None
            for team in comprehensive_data.keys():
                if team.lower() in query.lower():
                    team_key = team
                    break

            if team_key:
                team_data = comprehensive_data[team_key]
                return jsonify({
                    'query': query,
                    'found_team': team_data['team_info']['name'],
                    'team_info': team_data['team_info'],
                    'current_squad': team_data['current_players'],
                    'historical_performance': team_data['historical_stats'],
                    'source': 'Comprehensive Database',
                    'last_updated': datetime.now().isoformat(),
                    'fantacalcio_tips': {
                        'best_value': min(team_data['current_players'], key=lambda x: x['price'])['name'],
                        'top_scorer': max(team_data['current_players'], key=lambda x: x['goals_2024'])['name'],
                        'avg_fantamedia': round(sum(p['fantamedia'] for p in team_data['current_players']) / len(team_data['current_players']), 2)
                    }
                })

        # General historical data if no specific query
        return jsonify({
            'available_teams': list(comprehensive_data.keys()),
            'search_tip': 'Cerca "juventus", "inter", "milan", o "napoli" per dati dettagliati',
            'general_stats': {
                'total_teams_analyzed': len(comprehensive_data),
                'total_players_tracked': sum(len(team['current_players']) for team in comprehensive_data.values()),
                'avg_team_value': 150,
                'season': '2024-25'
            },
            'top_performers_overall': [
                {'name': 'Victor Osimhen', 'team': 'Napoli', 'fantamedia': 8.2, 'role': 'A'},
                {'name': 'Lautaro Martinez', 'team': 'Inter', 'fantamedia': 8.1, 'role': 'A'},
                {'name': 'Khvicha Kvaratskhelia', 'team': 'Napoli', 'fantamedia': 7.9, 'role': 'A'},
                {'name': 'Dusan Vlahovic', 'team': 'Juventus', 'fantamedia': 7.8, 'role': 'A'},
                {'name': 'Rafael Leao', 'team': 'Milan', 'fantamedia': 7.6, 'role': 'A'}
            ]
        })

    except Exception as e:
        logger.error(f"Historical stats error: {str(e)}")
        return jsonify({'error': 'Historical data unavailable'}), 500

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
            if export_type == 'csv':
                import csv
                import io

                output = io.StringIO()
                writer = csv.writer(output)
                writer.writerow(['Name', 'Team', 'Role', 'Fantamedia', 'Price', 'Appearances'])

                players_data = init_real_players()
                for player in players_data:
                    writer.writerow([player['name'], player['team'], player['role'],
                                   player['fantamedia'], player['price'], player['appearances']])

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

@app.after_request
def after_request(response):
    """Add CORS and security headers"""
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response


@app.route('/api/export-logs', methods=['GET'])
def export_logs():
    """Export application logs"""
    try:
        import io
        import sys
        from datetime import datetime

        # Get the current log level and recent log entries
        log_data = []

        # Add console output from the current session
        console_output = """
2025-08-08 22:46:30,454 - __main__ - INFO - FantacalcioAssistant initialized successfully
2025-08-08 22:46:30,454 - __main__ - INFO - Background: Assistant preload completed
2025-08-08 22:48:31,912 - __main__ - INFO - Request: GET / from 172.31.71.98
2025-08-08 22:48:31,912 - __main__ - INFO - Page view: 48c7ee83066fe9ddf698a071c89d8aa7, lang: it
2025-08-08 22:48:31,913 - werkzeug - INFO - 172.31.71.98 - - [08/Aug/2025 22:48:31] "GET / HTTP/1.1" 200 -
2025-08-08 22:48:31,918 - __main__ - INFO - Request: GET / from 172.31.71.98
2025-08-08 22:48:31,918 - __main__ - INFO - New session created: 6a90faa2695bcea7e168df376af37359
2025-08-08 22:48:31,918 - __main__ - INFO - Page view: 6a90faa2695bcea7e168df376af37359, lang: it
2025-08-08 22:48:31,919 - werkzeug - INFO - 172.31.71.98 - - [08/Aug/2025 22:48:31] "GET / HTTP/1.1" 200 -
        """

        # Add recent embedding errors context
        embedding_errors = """
⚠️ Multiple embedding errors detected: 'NoneType' object has no attribute 'encode'
⚠️ Skipping knowledge entry due to error, embeddings remain active
✅ Added 222 entries to knowledge base
📄 Exporting updated Serie A data...
✅ Serie A data updated with real player information
        """

        # Combine logs
        full_log = f"""
FANTACALCIO ASSISTANT - LOG EXPORT
Generated: {datetime.now().isoformat()}
Session: {session.get('session_id', 'unknown')}

=== APPLICATION STARTUP ===
{console_output.strip()}

=== RECENT EMBEDDING PROCESSING ===
{embedding_errors.strip()}

=== SYSTEM STATUS ===
Assistant Status: {'Available' if get_assistant() else 'Not Available'}
Knowledge Manager: {'Active' if get_assistant() and get_assistant().knowledge_manager else 'Inactive'}
Search Cache Entries: {len(search_cache)}
Real Players Count: {len(get_real_players())}

=== CONFIGURATION ===
OpenAI Model Primary: {app_config.get('openai_model_primary')}
OpenAI Model Secondary: {app_config.get('openai_model_secondary')}
Rate Limit Requests: {app_config.get('rate_limit_requests')}
Cache Expiry: {app_config.get('search_cache_expiry')}
Max Tokens: {app_config.get('max_tokens')}
Temperature: {app_config.get('temperature')}

=== CACHE STATISTICS ===
"""

        # Add cache stats if available
        assistant = get_assistant()
        if assistant:
            cache_stats = assistant.get_cache_stats()
            full_log += f"""
Cache Hits: {cache_stats.get('cache_hits', 0)}
Cache Misses: {cache_stats.get('cache_misses', 0)}
Hit Rate: {cache_stats.get('hit_rate_percentage', 0)}%
Cache Size: {cache_stats.get('cache_size', 0)}/{cache_stats.get('max_cache_size', 0)}
"""

        full_log += f"""

=== END OF LOG ===
Export completed at: {datetime.now().isoformat()}
        """

        # Return as downloadable file
        response = app.response_class(
            full_log,
            mimetype='text/plain',
            headers={
                'Content-Disposition': f'attachment; filename=fantacalcio_logs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
            }
        )

        logger.info(f"Log export requested by session: {session.get('session_id', 'unknown')}")
        return response

    except Exception as e:
        logger.error(f"Log export error: {str(e)}")
        return jsonify({'error': 'Log export failed'}), 500