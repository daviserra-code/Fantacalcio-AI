
from flask import Flask, render_template, request, jsonify, session
from fantacalcio_data import League, AuctionHelper, SAMPLE_PLAYERS
import json
import os

# Lazy import to avoid blocking startup
try:
    from main import FantacalcioAssistant
    print("FantacalcioAssistant imported successfully")
except Exception as e:
    print(f"Warning: Failed to import FantacalcioAssistant: {e}")
    FantacalcioAssistant = None

# Ensure Flask app can start even without FantacalcioAssistant
assistant = None

print("Flask app initialized, ready to start server")

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'fantacalcio_secret_key_2024')

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

assistant = None  # Initialize lazily when needed

@app.route('/health')
def health():
    return {'status': 'healthy', 'port': os.environ.get('PORT', 5000), 'assistant_available': FantacalcioAssistant is not None}, 200

@app.route('/ping')
def ping():
    return 'pong', 200

@app.route('/')
def index():
    lang = request.args.get('lang', 'it')
    if lang not in TRANSLATIONS:
        lang = 'it'
    session['lang'] = lang
    return render_template('index.html', lang=lang, t=TRANSLATIONS[lang])

@app.route('/api/chat', methods=['POST'])
def chat():
    global assistant
    if assistant is None:
        if FantacalcioAssistant is None:
            return jsonify({'error': 'Assistant service is temporarily unavailable. Please try again later.'}), 503
        try:
            assistant = FantacalcioAssistant()
        except Exception as e:
            print(f"Assistant initialization error: {str(e)}")
            return jsonify({'error': 'Assistant service initialization failed. Please contact support.'}), 503
    
    data = request.get_json()
    message = data.get('message', '')
    context = data.get('context', {})
    lang = session.get('lang', 'it')
    
    if not message:
        return jsonify({'error': 'Message required'}), 400
    
    # Add language context for AI responses
    context['language'] = lang
    response = assistant.get_response(message, context)
    return jsonify({'response': response})

@app.route('/api/reset', methods=['POST'])
def reset_chat():
    global assistant
    if assistant is None:
        return jsonify({'message': 'Chat already reset'})
    message = assistant.reset_conversation()
    return jsonify({'message': message})

@app.route('/api/search', methods=['POST'])
def search_players():
    data = request.get_json()
    query = data.get('query', '').lower()
    role_filter = data.get('role', 'all')
    
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
    
    return jsonify({'results': results})

@app.route('/api/league-setup', methods=['POST'])
def setup_league():
    data = request.get_json()
    league_type = data.get('type', 'Classic')
    participants = data.get('participants', 8)
    budget = data.get('budget', 500)
    
    league = League(league_type, participants, budget)
    
    return jsonify({
        'league': {
            'type': league.league_type,
            'participants': league.participants,
            'budget': league.budget,
            'rules': league.rules
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting Flask server on host 0.0.0.0, port {port}")
    print(f"Health check available at: http://0.0.0.0:{port}/health")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
