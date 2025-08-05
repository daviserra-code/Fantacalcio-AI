
from flask import Flask, render_template, request, jsonify, session
from main import FantacalcioAssistant
from fantacalcio_data import League, AuctionHelper, SAMPLE_PLAYERS
import json
import os

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

assistant = FantacalcioAssistant()

@app.route('/')
def index():
    lang = request.args.get('lang', 'it')
    if lang not in TRANSLATIONS:
        lang = 'it'
    session['lang'] = lang
    return render_template('index.html', lang=lang, t=TRANSLATIONS[lang])

@app.route('/api/chat', methods=['POST'])
def chat():
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
    app.run(host='0.0.0.0', port=5000, debug=True)
