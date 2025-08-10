from flask import Flask, render_template, request, jsonify, session
import os
import json
import logging
from datetime import datetime
import unicodedata
from config import app_config

# Silenzia i warning HNSW di Chroma (opzionale)
logging.getLogger("chromadb.segment.impl.vector.local_persistent_hnsw").setLevel(logging.ERROR)

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
            # IMPORTANTISSIMO: l'import non deve lanciare ETL/seed
            from main import FantacalcioAssistant
            logger.info("Initializing FantacalcioAssistant...")
            assistant_instance = FantacalcioAssistant()
            logger.info("FantacalcioAssistant initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize FantacalcioAssistant: {e}")
            assistant_instance = create_mock_assistant()

    return assistant_instance if assistant_instance is not False else None

def create_mock_assistant():
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

# Helpers per normalizzazione nomi
def _norm(s: str) -> str:
    if not s:
        return ""
    s = s.strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return " ".join(s.split())

def _surname(s: str) -> str:
    parts = _norm(s).split()
    return parts[-1] if parts else ""

# Dati statici di fallback
STATIC_PLAYERS_DATA = [
    {'name': 'Victor Osimhen', 'team': 'Napoli', 'role': 'A', 'fantamedia': 8.2, 'price': 45, 'appearances': 32},
    {'name': 'Lautaro Martinez', 'team': 'Inter', 'role': 'A', 'fantamedia': 8.1, 'price': 44, 'appearances': 34},
    {'name': 'Dusan Vlahovic', 'team': 'Juventus', 'role': 'A', 'fantamedia': 7.8, 'price': 42, 'appearances': 35},
    {'name': 'Khvicha Kvaratskhelia', 'team': 'Napoli', 'role': 'A', 'fantamedia': 7.9, 'price': 41, 'appearances': 31},
    {'name': 'Rafael Leao', 'team': 'Milan', 'role': 'A', 'fantamedia': 7.6, 'price': 40, 'appearances': 30},
    {'name': 'Marcus Thuram', 'team': 'Inter', 'role': 'A', 'fantamedia': 7.3, 'price': 38, 'appearances': 32},
    {'name': 'Federico Chiesa', 'team': 'Juventus', 'role': 'A', 'fantamedia': 7.4, 'price': 37, 'appearances': 29},
    {'name': 'Olivier Giroud', 'team': 'Milan', 'role': 'A', 'fantamedia': 7.1, 'price': 34, 'appearances': 28},

    {'name': 'Nicolo Barella', 'team': 'Inter', 'role': 'C', 'fantamedia': 7.5, 'price': 32, 'appearances': 35},
    {'name': 'Hakan Calhanoglu', 'team': 'Inter', 'role': 'C', 'fantamedia': 7.1, 'price': 29, 'appearances': 32},
    {'name': 'Tijjani Reijnders', 'team': 'Milan', 'role': 'C', 'fantamedia': 6.7, 'price': 28, 'appearances': 30},
    {'name': 'Stanislav Lobotka', 'team': 'Napoli', 'role': 'C', 'fantamedia': 6.6, 'price': 26, 'appearances': 33},
    {'name': 'Manuel Locatelli', 'team': 'Juventus', 'role': 'C', 'fantamedia': 6.5, 'price': 25, 'appearances': 31},

    {'name': 'Theo Hernandez', 'team': 'Milan', 'role': 'D', 'fantamedia': 7.2, 'price': 32, 'appearances': 33},
    {'name': 'Alessandro Bastoni', 'team': 'Inter', 'role': 'D', 'fantamedia': 7.0, 'price': 30, 'appearances': 32},
    {'name': 'Federico Dimarco', 'team': 'Inter', 'role': 'D', 'fantamedia': 6.8, 'price': 26, 'appearances': 31},
    {'name': 'Andrea Cambiaso', 'team': 'Juventus', 'role': 'D', 'fantamedia': 6.6, 'price': 24, 'appearances': 29},
    {'name': 'Giovanni Di Lorenzo', 'team': 'Napoli', 'role': 'D', 'fantamedia': 6.5, 'price': 23, 'appearances': 34},

    {'name': 'Mike Maignan', 'team': 'Milan', 'role': 'P', 'fantamedia': 6.8, 'price': 24, 'appearances': 36},
    {'name': 'Yann Sommer', 'team': 'Inter', 'role': 'P', 'fantamedia': 6.6, 'price': 20, 'appearances': 35},
    {'name': 'Alex Meret', 'team': 'Napoli', 'role': 'P', 'fantamedia': 6.4, 'price': 17, 'appearances': 32},
    {'name': 'Mattia Perin', 'team': 'Juventus', 'role': 'P', 'fantamedia': 6.2, 'price': 15, 'appearances': 28}
]

def get_assistant_players():
    """Legge dal KM se disponibile (senza scrivere su DB)."""
    assistant = get_assistant()
    if not assistant or not getattr(assistant, "knowledge_manager", None):
        return []

    try:
        # query "larga" per pescare giocatori recenti
        search_results = assistant.knowledge_manager.search_knowledge(
            "giocatore attaccante centrocampista difensore portiere fantamedia stagione",
            n_results=400
        )
        real_players = []
        for r in search_results:
            md = r.get("metadata", {})
            if md.get("type") in ("current_player", "player_info"):
                real_players.append({
                    "name": md.get("player", md.get("title", "Unknown")),
                    "team": md.get("team", "Unknown"),
                    "role": md.get("role", "A"),
                    "fantamedia": md.get("fantamedia", 6.0),
                    "price": md.get("price", 20),
                    "appearances": md.get("appearances", 30),
                })
        return real_players
    except Exception as e:
        logger.error(f"Failed to get real players data: {e}")
        return []

def get_all_players_merged():
    """Unisce KB + statici e deduplica per nome normalizzato."""
    real = get_assistant_players()
    merged = {}
    for p in (real or []):
        merged[_norm(p['name'])] = p
    for p in STATIC_PLAYERS_DATA:
        key = _norm(p['name'])
        if key not in merged:
            merged[key] = p
    return list(merged.values())

# Multilingua minimale (usata dall'index.html)
TRANSLATIONS = {
    'it': {
        'title': 'Assistente Fantacalcio Pro',
        'subtitle': 'Il tuo consulente per vincere il fantacalcio',
        'modes': {'classic': 'Classic', 'mantra': 'Mantra', 'draft': 'Draft', 'superscudetto': 'Superscudetto'},
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
        'modes': {'classic': 'Classic', 'mantra': 'Mantra', 'draft': 'Draft', 'superscudetto': 'Superscudetto'},
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

# Flask app
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'fantacalcio-dev-key-2024')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 300
app.config['JSON_SORT_KEYS'] = False

@app.before_request
def log_request_info():
    logger.info(f"Request: {request.method} {request.path} from {request.remote_addr}")

@app.route('/health')
def health():
    return {'status': 'healthy'}, 200

@app.route('/metrics')
def metrics():
    assistant = get_assistant()
    cache_stats = assistant.get_cache_stats() if assistant else {}
    return {
        'uptime': 'running',
        'assistant_status': 'available' if assistant else 'not_initialized',
        'players_total': len(get_all_players_merged()),
        'assistant_cache_stats': cache_stats
    }, 200

@app.route('/')
def index():
    if 'session_id' not in session:
        session['session_id'] = os.urandom(16).hex()
        session.permanent = True
        logger.info(f"New session created: {session['session_id']}")
    lang = request.args.get('lang', 'it')
    if lang not in TRANSLATIONS:
        lang = 'it'
    session['lang'] = lang
    logger.info(f"Page view: {session['session_id']}, lang: {lang}")
    return render_template('index.html', lang=lang, t=TRANSLATIONS[lang])

@app.route('/api/compare', methods=['POST', 'OPTIONS', 'GET'])
@app.route('/api/player-comparison', methods=['POST', 'OPTIONS', 'GET'])
def compare_players_api():
    """Player comparison robusta + merge KB/statici, nessuna scrittura su Chroma."""
    try:
        if request.method == 'OPTIONS':
            return ('', 204)
        if request.method == 'GET':
            sample = [p['name'] for p in get_all_players_merged()[:2]]
            return jsonify({'status': 'ok', 'hint': 'POST JSON { "players": ["Nome1", "Nome2"] }', 'sample': sample})

        data = request.get_json(silent=True) or {}
        players = data.get('players', [])
        logger.info(f"Comparing players: {players}")
        if len(players) < 2:
            return jsonify({'error': 'Need at least 2 players'}), 400

        all_players = get_all_players_merged()
        index = [{
            "name": p["name"],
            "norm": _norm(p["name"]),
            "surname": _surname(p["name"]),
            "data": p
        } for p in all_players]

        found_players = []
        for q_raw in players:
            q = _norm(q_raw)
            q_surname = _surname(q_raw)
            hit = None

            # 1) match pieno o contenuto
            for it in index:
                if q and (q == it["norm"] or q in it["norm"] or it["norm"] in q):
                    hit = it["data"]; break
            # 2) cognome
            if not hit and q_surname:
                for it in index:
                    if q_surname and q_surname == it["surname"]:
                        hit = it["data"]; break
            # 3) overlap token
            if not hit and q:
                q_tokens = set(q.split())
                for it in index:
                    if q_tokens & set(it["norm"].split()):
                        hit = it["data"]; break

            if hit:
                p = hit
                found_players.append({
                    'name': p['name'],
                    'team': p['team'],
                    'role': p['role'],
                    'fantamedia': p['fantamedia'],
                    'price': p['price'],
                    'appearances': p['appearances'],
                    'value_ratio': round(p['fantamedia'] / max(p['price'], 1) * 100, 2)
                })

        requested_norm = [_norm(x) for x in players]
        found_norm = [_norm(x['name']) for x in found_players]
        missed = [players[i] for i, rn in enumerate(requested_norm) if rn not in set(found_norm)]
        if missed:
            logger.info(f"Compare miss: requested={players} missed={missed}")

        logger.info(f"Found {len(found_players)} players")
        if not found_players:
            return jsonify({'error': 'No players found', 'available_players': [p['name'] for p in all_players[:10]]}), 404

        metrics = {
            'best_value': max(found_players, key=lambda x: x['value_ratio'])['name'],
            'best_fantamedia': max(found_players, key=lambda x: x['fantamedia'])['name'],
            'most_reliable': max(found_players, key=lambda x: x['appearances'])['name'],
            'summary': f"Miglior rapporto qualità-prezzo: {max(found_players, key=lambda x: x['value_ratio'])['name']}"
        }
        return jsonify({'comparison': found_players, 'metrics': metrics, 'count': len(found_players)})

    except Exception as e:
        logger.error(f"Compare error: {e}")
        return jsonify({'error': 'Comparison failed'}), 500


# --- Endpoints base (chat, ecc.) opzionali: qui teniamo solo quelli utili alla comparison ---

@app.errorhandler(404)
def not_found(error):
    logger.warning(f"404 error: {request.path}")
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"500 error: {error}")
    return jsonify({'error': 'Internal server error'}), 500

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response


if __name__ == '__main__':
    try:
        port = int(os.environ.get('PORT', 5000))
        debug_mode = False
        logger.info("Starting Fantasy Football Assistant Web Interface")
        logger.info(f"Server: 0.0.0.0:{port}")
        app.run(host='0.0.0.0', port=port, debug=debug_mode, threaded=True, use_reloader=False, processes=1)
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        raise