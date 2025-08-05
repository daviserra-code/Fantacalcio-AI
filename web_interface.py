
from flask import Flask, render_template, request, jsonify
from main import FantacalcioAssistant
from fantacalcio_data import League, AuctionHelper
import json

app = Flask(__name__)
assistant = FantacalcioAssistant()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json()
    message = data.get('message', '')
    context = data.get('context', {})
    
    if not message:
        return jsonify({'error': 'Messaggio richiesto'}), 400
    
    response = assistant.get_response(message, context)
    return jsonify({'response': response})

@app.route('/api/reset', methods=['POST'])
def reset_chat():
    message = assistant.reset_conversation()
    return jsonify({'message': message})

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
