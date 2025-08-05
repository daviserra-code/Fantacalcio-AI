
from flask import Flask, render_template, request, jsonify, session
from main import FantacalcioAssistant
from fantacalcio_data import League, AuctionHelper, SAMPLE_PLAYERS
from knowledge_manager import KnowledgeManager
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
    
    # Check for quick actions
    quick_action = detect_quick_action(message)
    if quick_action:
        return jsonify(quick_action)
    
    # Add language context for AI responses
    context['language'] = lang
    response = assistant.get_response(message, context)
    
    # Add suggested follow-up questions
    follow_ups = generate_follow_up_suggestions(message, context)
    
    return jsonify({
        'response': response,
        'follow_ups': follow_ups,
        'context_detected': extract_context_from_message(message)
    })

def detect_quick_action(message: str) -> Dict:
    """Detect and handle quick actions"""
    message_lower = message.lower()
    
    if "confronta" in message_lower and " vs " in message_lower:
        players = message.split(" vs ")
        if len(players) == 2:
            return {
                'type': 'player_comparison',
                'players': [p.strip() for p in players],
                'response': f"Confronto tra {players[0].strip()} e {players[1].strip()} in preparazione..."
            }
    
    if "formazione" in message_lower and any(f in message_lower for f in ["3-5-2", "4-4-2", "3-4-3"]):
        return {
            'type': 'formation_analysis',
            'response': "Analizzo la formazione ottimale per la tua rosa..."
        }
    
    return None

def generate_follow_up_suggestions(message: str, context: Dict) -> List[str]:
    """Generate contextual follow-up suggestions"""
    suggestions = []
    message_lower = message.lower()
    
    if any(word in message_lower for word in ["prezzo", "vale", "costa"]):
        suggestions.extend([
            "Mostrami alternative più economiche",
            "Analizza il rapporto qualità/prezzo",
            "Confronta con giocatori simili"
        ])
    
    if any(word in message_lower for word in ["formazione", "modulo"]):
        suggestions.extend([
            "Suggerisci il capitano",
            "Analizza i panchina",
            "Valuta formazioni alternative"
        ])
    
    if "infortunio" in message_lower:
        suggestions.extend([
            "Mostra alternative sicure",
            "Analizza rischio infortuni",
            "Suggerisci sostituzioni"
        ])
    
    return suggestions[:3]  # Limit to 3 suggestions

def extract_context_from_message(message: str) -> Dict:
    """Extract context information from user message"""
    context = {}
    
    # Extract player names (simple pattern matching)
    words = message.split()
    potential_players = [w for w in words if w[0].isupper() and len(w) > 3]
    if potential_players:
        context['mentioned_players'] = potential_players
    
    # Extract numbers (likely prices or budgets)
    import re
    numbers = re.findall(r'\d+', message)
    if numbers:
        context['mentioned_numbers'] = [int(n) for n in numbers]
    
    return context

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

@app.route('/api/knowledge/search', methods=['POST'])
def search_knowledge():
    data = request.get_json()
    query = data.get('query', '')
    
    if not query:
        return jsonify({'error': 'Query required'}), 400
    
    try:
        knowledge_items = assistant.rag_system.search_knowledge(query, n_results=5)
        return jsonify({'results': knowledge_items})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/knowledge/add', methods=['POST'])
def add_knowledge():
    data = request.get_json()
    text = data.get('text', '')
    metadata = data.get('metadata', {})
    
    if not text:
        return jsonify({'error': 'Text required'}), 400
    
    try:
        assistant.rag_system.add_knowledge(text, metadata)
        return jsonify({'message': 'Knowledge added successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
