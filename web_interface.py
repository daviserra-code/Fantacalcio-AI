# -*- coding: utf-8 -*-
import uuid
import json
import logging
import subprocess
import os
import re # Import the re module
import time
from flask import Flask, request, jsonify, session, render_template, g # Import g for application context
from flask import Response # Import Response for exporting rules
from flask_login import current_user

from config import HOST, PORT, LOG_LEVEL
from fantacalcio_assistant import FantacalcioAssistant
from corrections_manager import CorrectionsManager
# Assuming LeagueRulesManager is in a separate file named league_rules_manager.py
from league_rules_manager import LeagueRulesManager
from rate_limiter import RateLimiter
from static_transfers import get_team_arrivals, is_static_mode_enabled, get_transfer_stats

# Import authentication components
from app import app, db
from replit_auth import require_login, require_pro, make_replit_blueprint, init_login_manager
from models import User, UserLeague

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
LOG = logging.getLogger("web_interface")

# Initialize Flask-Login if not already initialized
try:
    # Check if login_manager is already initialized
    if not hasattr(app, 'login_manager'):
        LOG.info("Initializing Flask-Login in web_interface.py")
        init_login_manager(app)
    else:
        LOG.info("Flask-Login already initialized")
except Exception as e:
    LOG.error(f"Error initializing Flask-Login: {e}")

# Register authentication blueprint if not already registered
try:
    # Check if auth blueprint is already registered
    auth_blueprint_exists = any(bp.name == 'replit_auth' for bp in app.blueprints.values())
    if not auth_blueprint_exists:
        LOG.info("Registering authentication blueprint in web_interface.py")
        app.register_blueprint(make_replit_blueprint(), url_prefix="/auth")
    else:
        LOG.info("Authentication blueprint already registered")
except Exception as e:
    LOG.error(f"Error registering authentication blueprint: {e}")

# Import routes to ensure all routes are registered
try:
    import routes  # noqa: F401
    LOG.info("Routes imported successfully")
except ImportError as e:
    LOG.warning(f"Could not import routes: {e}")
except Exception as e:
    LOG.error(f"Error importing routes: {e}")

# Initialize rate limiter (10 requests per hour for deployed app)
rate_limiter = RateLimiter(max_requests=10, time_window=3600)

# ---------- Singletons ----------
# Global singleton to prevent re-initialization
_global_assistant = None

def get_assistant():
    global _global_assistant

    # Use global singleton instead of Flask g to prevent re-initialization
    if _global_assistant is None:
        LOG.info("Initializing FantacalcioAssistant (singleton)...")
        try:
            _global_assistant = FantacalcioAssistant()
            LOG.info("FantacalcioAssistant initialized successfully")
        except Exception as e:
            LOG.error(f"Failed to initialize FantacalcioAssistant: {e}")
            # Create a minimal fallback assistant
            from types import SimpleNamespace
            _global_assistant = SimpleNamespace()
            _global_assistant.respond = lambda msg, **kwargs: (f"⚠️ Servizio temporaneamente non disponibile: {e}", {})
            _global_assistant.roster = []
            _global_assistant.filtered_roster = []

    return _global_assistant

# Global singleton for corrections manager
_global_corrections_manager = None

def get_corrections_manager() -> CorrectionsManager:
    global _global_corrections_manager

    if _global_corrections_manager is None:
        assistant = get_assistant()
        _global_corrections_manager = CorrectionsManager(knowledge_manager=assistant.km)
    return _global_corrections_manager

# Global singleton for rules manager
_global_rules_manager = None

def get_rules_manager() -> LeagueRulesManager:
    global _global_rules_manager

    if _global_rules_manager is None:
        LOG.info("Initializing LeagueRulesManager (singleton)...")
        _global_rules_manager = LeagueRulesManager()
    return _global_rules_manager

def get_sid() -> str:
    sid = session.get("sid")
    if not sid:
        sid = uuid.uuid4().hex[:16]
        session["sid"] = sid
    return sid

def get_state() -> dict:
    st = session.get("state")
    return st if isinstance(st, dict) else {}

def set_state(st: dict) -> None:
    session["state"] = st

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

# Route moved to site_blueprint.py for device detection
# @app.route("/", methods=["GET"])
def index_legacy():
    try:
        lang = request.args.get("lang", "it")
        page_id = uuid.uuid4().hex[:16]
        LOG.info("Request: GET / from %s", request.remote_addr)
        LOG.info("Page view: %s, lang: %s", page_id, lang)

        # Return the original Fantasy Football AI interface
        return render_template("index.html", lang=lang, t=T.get(lang,T["it"]),
                             user=current_user if current_user.is_authenticated else None)
    except Exception as e:
        LOG.error(f"Error serving index page: {e}")
        # Fallback HTML if template fails
        return f"""
        <!DOCTYPE html>
        <html>
        <head><title>Fantasy Football Assistant</title></head>
        <body>
            <h1>Fantasy Football Assistant</h1>
            <p>Servizio temporaneamente non disponibile. Errore: {e}</p>
            <p><a href="/health">Controlla stato servizio</a></p>
        </body>
        </html>
        """, 500

@app.route("/api/chat", methods=["POST"])
def api_chat():
    try:
        # Log client info for debugging
        client_ip = rate_limiter._get_client_key(request)
        LOG.info(f"Chat request from client: {client_ip}")

        # Check rate limit first
        if not rate_limiter.is_allowed(request):
            remaining_requests = rate_limiter.get_remaining_requests(request)
            reset_time = rate_limiter.get_reset_time(request)

            LOG.warning(f"Rate limit exceeded for client {client_ip}: {remaining_requests} remaining, reset at {reset_time}")

            return jsonify({
                "error": "Rate limit exceeded",
                "message": "Hai superato il limite di 10 richieste per ora. Riprova più tardi.",
                "remaining_requests": remaining_requests,
                "reset_time": reset_time,
                "client_id": client_ip[:8] + "..." if len(client_ip) > 8 else client_ip  # Partial IP for debugging
            }), 429

        data = request.get_json(force=True, silent=True) or {}
        msg  = (data.get("message") or "").strip()
        mode = (data.get("mode") or "classic").strip()

        LOG.info("Request data: %s", data)
    except Exception as e:
        LOG.error(f"Error processing request: {e}")
        return jsonify({"response": "❌ Errore nell'elaborazione della richiesta. Riprova."}), 500

    # Best-effort: avvia ETL senza bloccare (skip in deployment if issues)
    try:
        import os
        if os.path.exists("etl_build_roster.py"):
            subprocess.Popen(["python", "etl_build_roster.py"],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            LOG.info("[ETL] Job di refresh lanciato")
        else:
            LOG.info("[ETL] ETL script non trovato, skip")
    except Exception as e2:
        LOG.warning("[ETL] impossibile avviare ETL: %s", e2)

    if not msg:
        return jsonify({"response": "Scrivi un messaggio."})

    get_sid()
    state = get_state()
    assistant = get_assistant()
    corrections_manager = get_corrections_manager()

    # Handle exclusion requests
    import re  # Ensure re module is available in local scope
    exclusion_patterns = [
        r"rimuovi\s+([a-zA-ZÀ-ÿ\s]+?)(?:\s+dalla?\s+([a-zA-ZÀ-ÿ\s]+))?(?:\s|$)",
        r"escludi\s+([a-zA-ZÀ-ÿ\s]+?)(?:\s+dalla?\s+([a-zA-ZÀ-ÿ\s]+))?(?:\s|$)",
        r"togli\s+([a-zA-ZÀ-ÿ\s]+?)(?:\s+dalla?\s+([a-zA-ZÀ-ÿ\s]+))?(?:\s|$)"
    ]

    for pattern in exclusion_patterns:
        match = re.search(pattern, msg.lower())
        if match:
            player_name = match.group(1).strip().title()
            team_name = match.group(2).strip().title() if match.group(2) else ""

            LOG.info(f"[Web] Exclusion request: {player_name} from {team_name or 'all teams'}")

            if assistant.corrections_manager:
                if team_name:
                    result = assistant.corrections_manager.add_exclusion(player_name, team_name)
                    # Store in session for immediate effect
                    session_exclusions = state.get("excluded_players", [])
                    exclusion_key = f"{player_name.lower()}_{team_name.lower()}"
                    if exclusion_key not in session_exclusions:
                        session_exclusions.append(exclusion_key)
                        state["excluded_players"] = session_exclusions
                        LOG.info(f"[Web] Added to session exclusions: {exclusion_key}")

                    # Force refresh of assistant data
                    assistant.roster = assistant.corrections_manager.apply_corrections_to_data(assistant.roster)
                    assistant._make_filtered_roster()

                    response = result
                else:
                    result = assistant.corrections_manager.remove_player(player_name)
                    # Store in session for global exclusion
                    session_exclusions = state.get("excluded_players", [])
                    exclusion_key = f"{player_name.lower()}_global"
                    if exclusion_key not in session_exclusions:
                        session_exclusions.append(exclusion_key)
                        state["excluded_players"] = session_exclusions
                        LOG.info(f"[Web] Added to session exclusions (global): {exclusion_key}")

                    # Force refresh of assistant data
                    assistant.roster = assistant.corrections_manager.apply_corrections_to_data(assistant.roster)
                    assistant._make_filtered_roster()

                    response = result
            else:
                response = f"✅ **{player_name}** è stato escluso dalle future liste. Questa esclusione è attiva per tutta la sessione."
                # Store in session even without corrections manager
                session_exclusions = state.get("excluded_players", [])
                exclusion_key = f"{player_name.lower()}_{team_name.lower() if team_name else 'global'}"
                if exclusion_key not in session_exclusions:
                    session_exclusions.append(exclusion_key)
                    state["excluded_players"] = session_exclusions
                    LOG.info(f"[Web] Added to session exclusions (fallback): {exclusion_key}")

            set_state(state)
            return jsonify({"response": response, "state": state})

    # Check for corrections
    correction_response = handle_correction(msg, assistant) # Pass assistant instead of corrections_manager
    if correction_response:
        # Add correction context to conversation history
        state.setdefault("conversation_history", []).append({
            "role": "user",
            "content": msg
        })
        state["conversation_history"].append({
            "role": "assistant",
            "content": correction_response
        })
        set_state(state)
        return jsonify({"response": correction_response})

    # Get relevant corrections for context
    relevant_corrections = corrections_manager.get_relevant_corrections(msg, limit=5)

    # Add conversation context with corrections
    state.setdefault("conversation_history", [])
    context_messages = state["conversation_history"][-8:]  # Keep last 8 messages for more space

    # Add corrections context if any
    if relevant_corrections:
        corrections_context = "CORREZIONI RECENTI:\n"
        for corr in relevant_corrections[:3]:  # Top 3 most relevant
            corrections_context += f"- {corr.get('wrong', '')} → {corr.get('correct', '')}\n"

        context_messages.insert(0, {
            "role": "system",
            "content": corrections_context
        })

    # Add exclusions to context
    excluded_players = state.get("excluded_players", [])
    if excluded_players:
        exclusions_context = f"GIOCATORI ESCLUSI: {', '.join(excluded_players)}"
        context_messages.insert(0, {
            "role": "system",
            "content": exclusions_context
        })

    # Apply exclusions before processing
    session_exclusions = state.get("excluded_players", [])
    persistent_exclusions = []
    if assistant.corrections_manager:
        try:
            persistent_exclusions = assistant.corrections_manager.get_excluded_players()
        except Exception as e:
            LOG.error(f"Error getting persistent exclusions: {e}")

    all_exclusions = session_exclusions + persistent_exclusions
    LOG.info(f"Applying exclusions: session={session_exclusions}, persistent={persistent_exclusions}")

    # Update assistant's excluded players cache before processing
    if assistant.corrections_manager and all_exclusions:
        if not hasattr(assistant.corrections_manager, '_excluded_players_cache'):
            assistant.corrections_manager._excluded_players_cache = {}

        # Parse session exclusions and add to cache
        for exclusion in session_exclusions:
            if "_" in exclusion:
                player_name, team_or_global = exclusion.split("_", 1)
                if team_or_global != "global":
                    if team_or_global not in assistant.corrections_manager._excluded_players_cache:
                        assistant.corrections_manager._excluded_players_cache[team_or_global] = set()
                    assistant.corrections_manager._excluded_players_cache[team_or_global].add(player_name.lower())

        LOG.info(f"Updated exclusions cache with session data")


    try:
        reply, new_state = assistant.respond(msg, mode=mode, state=state, context_messages=context_messages)
    except Exception as e:
        LOG.error("Error in assistant.respond: %s", e, exc_info=True)
        reply = f"⚠️ Errore temporaneo del servizio. Messaggio: {msg[:50]}... - Riprova tra poco."
        new_state = state

    # Apply exclusions to response text
    reply = apply_exclusions_to_text(reply, new_state.get("excluded_players", []))

    # Apply corrections and data validation to response
    try:
        corrected_response, applied_corrections = corrections_manager.apply_corrections_to_text(reply)
        if applied_corrections:
            LOG.info("Applied %d corrections to response", len(applied_corrections))
            reply = corrected_response

        # Additional validation: remove mentions of non-Serie A teams
        non_serie_a_patterns = [
            r'\b(Newcastle|PSG|Paris Saint-Germain|Al Hilal|Tottenham|Arsenal|Manchester United|Manchester City|Chelsea|Liverpool|Real Madrid|Barcelona|Atletico Madrid|Bayern Munich|Borussia Dortmund)\b',
            r'\(Newcastle\)',
            r'\(PSG\)',
            r'\(Al Hilal\)',
            r'\(Tottenham\)',
            r'\(Premier League\)',
            r'\(La Liga\)',
            r'\(Bundesliga\)',
            r'\(Ligue 1\)'
        ]

        import re
        for pattern in non_serie_a_patterns:
            reply = re.sub(pattern, '', reply, flags=re.IGNORECASE)

        # Clean up multiple spaces and empty lines
        reply = re.sub(r'\s+', ' ', reply)
        reply = re.sub(r'\n\s*\n', '\n', reply)
        reply = reply.strip()

    except Exception as e:
        LOG.error("Error applying corrections: %s", e)

    # Update conversation history (avoid duplicates since assistant already handles this)
    if "conversation_history" not in new_state:
        new_state["conversation_history"] = []
        # Add the current exchange if not already added by assistant
        new_state["conversation_history"].extend([
            {"role": "user", "content": msg, "timestamp": time.time()},
            {"role": "assistant", "content": reply, "timestamp": time.time()}
        ])
    else:
        # Ensure current exchange is added if not already handled by assistant.respond
        if not any(item['content'] == reply for item in new_state["conversation_history"] if item['role'] == 'assistant'):
            new_state["conversation_history"].append({"role": "user", "content": msg, "timestamp": time.time()})
            new_state["conversation_history"].append({"role": "assistant", "content": reply, "timestamp": time.time()})


    set_state(new_state)

    # Add rate limit info to response
    response = jsonify({"response": reply})
    remaining = rate_limiter.get_remaining_requests(request)
    response.headers['X-RateLimit-Remaining'] = str(remaining)
    response.headers['X-RateLimit-Limit'] = str(rate_limiter.max_requests)

    reset_time = rate_limiter.get_reset_time(request)
    if reset_time:
        response.headers['X-RateLimit-Reset'] = str(reset_time)

    return response

def handle_exclusion(msg: str, state: dict) -> str:
    """Handle player exclusions (rimuovi/escludi commands)"""
    msg_lower = msg.lower()

    # Pattern for team-specific exclusions
    team_exclusion_pattern = r"rimuovi\s+([a-zA-ZÀ-ÿ\s]+?)\s+dall[ao]\s+([a-zA-ZÀ-ÿ\s]+?)(?:\s*$)"
    team_match = re.search(team_exclusion_pattern, msg, re.IGNORECASE)

    if team_match:
        player_name = team_match.group(1).strip()
        team_name = team_match.group(2).strip()

        # Clean up common words
        player_name = re.sub(r'\b(dalla?|lista|squadre?|non|di|serie|a)\b', '', player_name, flags=re.IGNORECASE).strip()
        team_name = re.sub(r'\b(lista|squadra)\b', '', team_name, flags=re.IGNORECASE).strip()

        if len(player_name) > 2 and len(team_name) > 2:
            # Use persistent team-specific exclusions
            try:
                corrections_manager = get_corrections_manager()
                if corrections_manager:
                    # Call persistent add_exclusion method for team-specific exclusion
                    result = corrections_manager.add_exclusion(player_name, team_name)

                    # Also add to session for immediate effect in current session
                    team_exclusions = state.setdefault("team_exclusions", {})
                    if team_name not in team_exclusions:
                        team_exclusions[team_name] = []
                    if player_name not in team_exclusions[team_name]:
                        team_exclusions[team_name].append(player_name)

                    return result
                else:
                    # Fallback to session-only if corrections manager unavailable
                    team_exclusions = state.setdefault("team_exclusions", {})
                    if team_name not in team_exclusions:
                        team_exclusions[team_name] = []

                    if player_name not in team_exclusions[team_name]:
                        team_exclusions[team_name].append(player_name)
                        return f"✅ **{player_name}** è stato escluso dalle liste della **{team_name}** (solo sessione corrente). Potrà ancora apparire se trasferito in altre squadre."
                    else:
                        return f"**{player_name}** è già escluso dalle liste della **{team_name}**."
            except Exception as e:
                LOG.error(f"Error using corrections manager for team exclusion {player_name} from {team_name}: {e}")
                # Fallback to session-only storage
                team_exclusions = state.setdefault("team_exclusions", {})
                if team_name not in team_exclusions:
                    team_exclusions[team_name] = []

                if player_name not in team_exclusions[team_name]:
                    team_exclusions[team_name].append(player_name)
                    return f"✅ **{player_name}** è stato escluso dalle liste della **{team_name}** (solo sessione corrente). Potrà ancora apparire se trasferito in altre squadre."
                else:
                    return f"**{player_name}** è già escluso dalle liste della **{team_name}**."

    # Fallback patterns for general exclusions
    patterns = [
        r"rimuovi\s+([a-zA-ZÀ-ÿ\s]+?)(?:\s+dalla?\s+lista)?(?:\s*$)",
        r"escludi\s+([a-zA-ZÀ-ÿ\s]+?)(?:\s+dalla?\s+lista)?(?:\s*$)"
    ]

    for pattern in patterns:
        match = re.search(pattern, msg, re.IGNORECASE)
        if match:
            player_name = match.group(1).strip()

            # Clean up common words that might be captured
            player_name = re.sub(r'\b(dalla?|lista|squadre?|non|di|serie|a)\b', '', player_name, flags=re.IGNORECASE).strip()

            if len(player_name) > 2:  # Avoid very short matches
                # Use persistent corrections manager instead of session-only storage
                try:
                    corrections_manager = get_corrections_manager()
                    if corrections_manager:
                        # Call persistent remove_player method
                        result = corrections_manager.remove_player(player_name, "User web interface request")

                        # Also add to session for immediate effect in current session
                        excluded_players = state.setdefault("excluded_players", [])
                        if player_name not in excluded_players:
                            excluded_players.append(player_name)

                        return result
                    else:
                        # Fallback to session-only if corrections manager unavailable
                        excluded_players = state.setdefault("excluded_players", [])
                        if player_name not in excluded_players:
                            excluded_players.append(player_name)
                            return f"✅ **{player_name}** è stato escluso dalle future liste (solo sessione corrente - riavvia per applicare permanentemente)."
                        else:
                            return f"**{player_name}** è già escluso dalle liste."
                except Exception as e:
                    LOG.error(f"Error using corrections manager for {player_name}: {e}")
                    # Fallback to session-only storage
                    excluded_players = state.setdefault("excluded_players", [])
                    if player_name not in excluded_players:
                        excluded_players.append(player_name)
                        return f"✅ **{player_name}** è stato escluso dalle future liste (solo sessione corrente)."
                    else:
                        return f"**{player_name}** è già escluso dalle liste."

    return ""

def apply_exclusions_to_text(text: str, excluded_players: list) -> str:
    """Remove excluded players from response text, considering team-specific exclusions"""
    # Get persistent exclusions from corrections manager
    try:
        corrections_manager = get_corrections_manager()
        persistent_excluded = corrections_manager.get_excluded_players()
        all_excluded = list(set(excluded_players + persistent_excluded))
        LOG.info(f"Applying exclusions: session={excluded_players}, persistent={persistent_excluded}")
    except Exception as e:
        LOG.error(f"Error getting persistent exclusions: {e}")
        all_excluded = excluded_players

    if not all_excluded:
        return text

    lines = text.split('\n')
    filtered_lines = []

    for line in lines:
        # Skip lines that contain excluded players
        should_exclude = False
        line_lower = line.lower()

        # Extract team from line if possible (format: **Player** (Team))
        team_in_line = None
        import re
        team_match = re.search(r'\*\*[^*]+\*\*\s*\(([^)]+)\)', line)
        if team_match:
            team_in_line = team_match.group(1).strip()

        for excluded in all_excluded:
            excluded_lower = excluded.lower().strip()

            # Handle special characters by creating multiple search variants
            import unicodedata

            # Normalize the excluded name to handle accented characters
            excluded_normalized = unicodedata.normalize('NFD', excluded_lower)
            excluded_normalized = ''.join(c for c in excluded_normalized if unicodedata.category(c) != 'Mn')

            # Create search patterns for the player name
            search_patterns = [
                excluded_lower,
                excluded_normalized,
                excluded_lower.replace('ć', 'c').replace('č', 'c').replace('ž', 'z').replace('š', 's'),
                excluded_lower.replace('ovic', 'ović').replace('ovic', 'ovič')
            ]

            # Remove duplicates
            search_patterns = list(set(search_patterns))

            for pattern in search_patterns:
                if not pattern or len(pattern) < 3:
                    continue

                # Enhanced pattern matching for better exclusion
                # Pattern 1: Look for the name in **bold** format (most common in responses)
                bold_pattern = rf'\*\*[^*]*{re.escape(pattern)}[^*]*\*\*'
                if re.search(bold_pattern, line_lower, re.IGNORECASE):
                    should_exclude = True
                    LOG.info(f"Excluding line with bold player '{excluded}' (pattern: {pattern}): {line.strip()}")
                    break

                # Pattern 2: Look for exact name matches in list items (e.g., "1. **Name** →")
                list_pattern = rf'\d+\.\s*\*\*[^*]*{re.escape(pattern)}[^*]*\*\*'
                if re.search(list_pattern, line_lower, re.IGNORECASE):
                    should_exclude = True
                    LOG.info(f"Excluding numbered list item with '{excluded}' (pattern: {pattern}): {line.strip()}")
                    break

                # Pattern 3: Check if main parts of the name appear
                pattern_parts = [part for part in pattern.split() if len(part) > 2]
                if pattern_parts:
                    # For names with multiple parts, check if most parts match
                    parts_found = sum(1 for part in pattern_parts if part in line_lower)
                    if len(pattern_parts) > 1 and parts_found >= len(pattern_parts):
                        should_exclude = True
                        LOG.info(f"Excluding line containing all name parts from '{excluded}' (pattern: {pattern}): {line.strip()}")
                        break
                    elif len(pattern_parts) == 1 and parts_found > 0 and len(pattern_parts[0]) > 4:
                        # For single long names, be more strict
                        should_exclude = True
                        LOG.info(f"Excluding line containing single name part from '{excluded}' (pattern: {pattern}): {line.strip()}")
                        break

                # Pattern 4: Direct substring match for substantial names (stricter)
                if len(pattern) > 6 and pattern in line_lower:
                    should_exclude = True
                    LOG.info(f"Excluding line containing '{excluded}' (pattern: {pattern}): {line.strip()}")
                    break

            if should_exclude:
                break

        if not should_exclude:
            filtered_lines.append(line)

    result = '\n'.join(filtered_lines)

    # Log the filtering result
    if len(filtered_lines) < len(lines):
        LOG.info(f"Filtered out {len(lines) - len(filtered_lines)} lines containing excluded players")

    return result

def handle_correction(user_message: str, fantacalcio_assistant) -> str:
    """Handle comprehensive user corrections and apply them permanently"""
    message_lower = user_message.lower().strip()

    # Pattern for removing players: "rimuovi [player name]"
    remove_patterns = [
        r"rimuovi\s+(.+?)(?:\s+dalla\s+lista)?$",
        r"escludi\s+(.+?)(?:\s+dalla\s+lista)?$",
        r"togli\s+(.+?)(?:\s+dalla\s+lista)?$"
    ]

    for pattern in remove_patterns:
        match = re.search(pattern, message_lower)
        if match:
            player_name = match.group(1).strip()
            # Clean up player name
            player_name = re.sub(r'\s+', ' ', player_name).title()

            try:
                # Use corrections manager from web interface
                corrections_manager = get_corrections_manager()
                result = corrections_manager.remove_player(player_name, "Web interface user request")

                # Force reload of the assistant's data to apply changes immediately
                if hasattr(fantacalcio_assistant, 'roster'):
                    fantacalcio_assistant.roster = corrections_manager.apply_corrections_to_data(fantacalcio_assistant.roster)
                if hasattr(fantacalcio_assistant, '_make_filtered_roster'):
                    fantacalcio_assistant._make_filtered_roster()

                return result
            except Exception as e:
                LOG.error(f"Error in handle_correction for {player_name}: {e}")
                return f"❌ Errore nell'applicare la correzione: {e}"

    # Pattern for team updates: "sposta [player] a [team]" or "[player] gioca nel [team]"
    team_update_patterns = [
        r"^(.+?)\s+(?:ora\s+|adesso\s+)?(?:gioca\s+nel|è\s+al|è\s+del|trasferito\s+al|va\s+al)\s+(.+)$",
        r"^sposta\s+(.+?)\s+(?:al|nel|a)\s+(.+)$",
        r"^aggiorna\s+(.+?)\s+(?:al|nel|a)\s+(.+)$"
    ]

    for pattern in team_update_patterns:
        match = re.search(pattern, message_lower)
        if match:
            player_name = match.group(1).strip().title()
            new_team = match.group(2).strip().title()

            # Log the extraction for debugging
            LOG.info(f"Team update detected: '{player_name}' -> '{new_team}'")

            try:
                # Get corrections manager and apply the update
                corrections_manager = get_corrections_manager()

                # Find the current team for this player
                old_team = "Unknown"
                for p in fantacalcio_assistant.roster:
                    if p.get("name", "").lower() == player_name.lower():
                        old_team = p.get("team", "Unknown")
                        break

                # Apply the correction persistently
                corrections_manager.add_correction_to_db(player_name, "TEAM_UPDATE", old_team, new_team, persistent=True)

                # Update the player data immediately in the assistant's roster
                for p in fantacalcio_assistant.roster:
                    if p.get("name", "").lower() == player_name.lower():
                        p["team"] = new_team
                        LOG.info(f"Updated {player_name} team from {old_team} to {new_team} in roster")

                # Also update filtered roster
                for p in fantacalcio_assistant.filtered_roster:
                    if p.get("name", "").lower() == player_name.lower():
                        p["team"] = new_team
                        LOG.info(f"Updated {player_name} team in filtered roster: {old_team} → {new_team}")

                # Force reload of filtered roster to apply changes
                fantacalcio_assistant._make_filtered_roster()

                return f"✅ Aggiornato {player_name}: {old_team} → {new_team}"
            except Exception as e:
                LOG.error(f"Error updating player team: {e}")
                return f"❌ Errore nell'aggiornare il giocatore: {e}"

    # Pattern for excluding non-Serie A teams
    if any(phrase in message_lower for phrase in ["escludi squadre non di serie a", "solo serie a", "escludi squadre estere"]):
        try:
            # This will trigger data filtering in the next request
            return "✅ Applicherò il filtro Serie A nelle prossime ricerche. I giocatori di squadre non italiane saranno esclusi automaticamente."
        except Exception as e:
            return f"❌ Errore nell'applicare il filtro: {e}"

    # Pattern for data quality issues
    quality_patterns = [
        r"aggiorna\s+i\s+dati",
        r"dati\s+non\s+aggiornati",
        r"informazioni\s+obsolete",
        r"dati\s+vecchi"
    ]

    for pattern in quality_patterns:
        if re.search(pattern, message_lower):
            try:
                report = fantacalcio_assistant.get_data_quality_report()
                return f"📊 **Report Qualità Dati:**\n" \
                       f"• Giocatori totali: {report['roster_stats']['total_players']}\n" \
                       f"• Giocatori Serie A: {report['roster_stats']['serie_a_players']}\n" \
                       f"• Completezza dati: {report['roster_stats']['data_completeness']}%\n" \
                       f"• Correzioni applicate: {report['total_corrections']}\n" \
                       f"• Giocatori esclusi: {report['excluded_players']}\n\n" \
                       f"💡 *Usa 'rimuovi [nome giocatore]' per escludere giocatori obsoleti*"
            except Exception as e:
                return f"❌ Errore nel generare il report: {e}"

    return ""

@app.route("/api/reset-chat", methods=["POST"])
def api_reset_chat():
    set_state({})
    return jsonify({"ok": True})

@app.route("/api/reset-exclusions", methods=["POST"])
def api_reset_exclusions():
    state = get_state()
    state.pop("excluded_players", None)
    set_state(state)
    return jsonify({"ok": True, "message": "Esclusioni rimosse"})

@app.route("/api/rate-limit-status", methods=["GET"])
def rate_limit_status():
    """Get current rate limiting status"""
    try:
        status = rate_limiter.get_status()
        return jsonify(status)
    except Exception as e:
        LOG.error(f"Error getting rate limit status: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/api/transfers/arrivals", methods=["GET"])
def api_transfers_arrivals():
    """Get transfer arrivals for a specific team using static data"""
    try:
        team = request.args.get('team', '').strip()
        season = request.args.get('season', '2025-26').strip()

        if not team:
            return jsonify({"error": "Team parameter required"}), 400

        LOG.info(f"[Static Transfers API] Getting arrivals for {team}, season {season}")

        # Check if static mode is enabled
        if not is_static_mode_enabled():
            return jsonify({
                "error": "Static transfers mode not enabled",
                "team": team,
                "arrivals": []
            }), 503

        # Get arrivals from static data
        arrivals = get_team_arrivals(team, season)

        # Format response
        formatted_arrivals = []
        for transfer in arrivals:
            formatted_arrivals.append({
                "player": transfer.get("player", ""),
                "team": transfer.get("team", ""),
                "from_team": transfer.get("from_team", ""),
                "fee": transfer.get("fee", ""),
                "position": transfer.get("position", ""),
                "season": transfer.get("season", ""),
                "source": transfer.get("source", "Apify"),
                "direction": transfer.get("direction", "in")
            })

        LOG.info(f"[Static Transfers API] Returning {len(formatted_arrivals)} arrivals for {team}")

        return jsonify({
            "team": team,
            "season": season,
            "arrivals": formatted_arrivals,
            "count": len(formatted_arrivals),
            "static_mode": True
        })

    except Exception as e:
        LOG.error(f"Error in transfers arrivals API: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/api/transfers/stats", methods=["GET"])
def api_transfers_stats():
    """Get transfer data statistics"""
    try:
        stats = get_transfer_stats()
        return jsonify(stats)
    except Exception as e:
        LOG.error(f"Error getting transfer stats: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/api/search', methods=['POST'])
def api_search():
    """Search functionality for statistics"""
    try:
        LOG.info(f"[Search API] Request received - Method: {request.method}")
        LOG.info(f"[Search API] Content-Type: {request.content_type}")
        LOG.info(f"[Search API] Raw data: {request.get_data()}")

        data = request.get_json()
        LOG.info(f"[Search API] Parsed JSON data: {data}")

        if not data:
            LOG.error("[Search API] No data provided in request")
            return jsonify({"error": "No data provided"}), 400

        query = data.get('query', '').strip()
        role = data.get('role', '').strip()

        LOG.info(f"[Search API] Search parameters - Query: '{query}', Role: '{role}'")

        if not query:
            LOG.error("[Search API] Query parameter is empty or missing")
            return jsonify({"error": "Query parameter required"}), 400

        # Initialize assistant if needed
        assistant = get_assistant()
        if not assistant:
            LOG.error("[Search API] Assistant not initialized")
            return jsonify({"error": "Assistant not initialized"}), 500

        LOG.info(f"[Search API] Assistant loaded, filtered_roster size: {len(assistant.filtered_roster)}")

        # Search players based on query and role
        results = []

        # Get all players and filter by role if specified
        all_players = assistant.filtered_roster
        if role:
            all_players = [p for p in all_players if p.get('role', '').upper() == role.upper()]

        # Simple text search in player names and teams
        query_lower = query.lower()
        for player in all_players:
            name = (player.get('name') or '').lower()
            team = (player.get('team') or '').lower()

            if query_lower in name or query_lower in team:
                # Only show players with real names - skip players with missing/empty names
                player_name = player.get('name', '').strip()
                player_team = player.get('team', '').strip()
                fantamedia = player.get('_fm')
                price = player.get('_price')

                # Skip players without real names (no artificial display names)
                if not player_name or len(player_name) < 2:
                    continue

                results.append({
                    'name': player_name,
                    'team': player_team or 'N/D',
                    'role': player.get('role', ''),
                    'fantamedia': fantamedia,
                    'price': price,
                    'age': assistant._age_from_by(player.get('birth_year')) if player.get('birth_year') else None
                })

        # Sort by fantamedia descending
        results.sort(key=lambda x: -(x.get('fantamedia') or 0))

        # Limit results
        results = results[:20]

        LOG.info(f"[Search API] Query '{query}' returned {len(results)} results")
        LOG.info(f"[Search API] Sample results: {results[:3] if results else 'No results'}")
        LOG.info(f"[Search API] Data source: filtered_roster (roster.json processed)")

        response_data = {
            'results': results,
            'total': len(results),
            'debug_info': {
                'query': query,
                'role_filter': role,
                'data_source': 'filtered_roster',
                'total_pool_size': len(assistant.filtered_roster),
                'matching_players': len([p for p in assistant.filtered_roster if query.lower() in (p.get('name') or '').lower() or query.lower() in (p.get('team') or '').lower()]),
                'role_filtered': len([p for p in assistant.filtered_roster if role and p.get('role', '').upper() == role.upper()]) if role else 'N/A'
            }
        }

        LOG.info(f"[Search API] Returning response: {response_data}")
        return jsonify(response_data)

    except Exception as e:
        LOG.error(f"[Search API] Error in search endpoint: {e}", exc_info=True)
        return jsonify({
            "error": "Internal server error",
            "debug_info": {
                "error_type": type(e).__name__,
                "error_message": str(e)
            }
        }), 500

@app.route('/api/players')
def api_players():
    """Get filtered players with U21 and In forma options"""
    try:
        LOG.info(f"[Players API] Request received - Method: {request.method}")
        LOG.info(f"[Players API] Request args: {dict(request.args)}")

        # Get query parameters
        search_query = request.args.get('search', '').strip()
        role_filter = request.args.get('role', '').strip().upper()
        team_filter = request.args.get('team', '').strip().lower()
        u21_filter = request.args.get('u21', '').lower() == 'true'
        in_forma_filter = request.args.get('in_forma', '').lower() == 'true'
        limit = int(request.args.get('limit', 50))

        LOG.info(f"[Players API] Filters - Search: '{search_query}', Role: '{role_filter}', Team: '{team_filter}', U21: {u21_filter}, In forma: {in_forma_filter}")

        assistant = get_assistant()
        if not assistant:
            LOG.error("[Players API] Assistant not available")
            return jsonify({
                "players": [],
                "total": 0,
                "error": "Assistant not available"
            }), 200

        # Ensure data is loaded
        assistant._ensure_data_loaded()

        # Use sample data if roster is not available
        players = []
        if hasattr(assistant, 'filtered_roster') and assistant.filtered_roster:
            players = assistant.filtered_roster
        else:
            LOG.warning("[Players API] Using sample data as roster is not available")
            # Sample data for demonstration
            players = [
                {"name": "Osimhen", "team": "Napoli", "role": "A", "_fm": 7.2, "_price": 45, "birth_year": 1999},
                {"name": "Vlahovic", "team": "Juventus", "role": "A", "_fm": 6.8, "_price": 40, "birth_year": 2000},
                {"name": "Leao", "team": "Milan", "role": "A", "_fm": 6.7, "_price": 38, "birth_year": 1999},
                {"name": "Kvaratskhelia", "team": "Napoli", "role": "A", "_fm": 7.1, "_price": 42, "birth_year": 2001},
                {"name": "Barella", "team": "Inter", "role": "C", "_fm": 6.8, "_price": 35, "birth_year": 1997},
                {"name": "Tonali", "team": "Milan", "role": "C", "_fm": 6.3, "_price": 28, "birth_year": 2000},
                {"name": "Theo Hernandez", "team": "Milan", "role": "D", "_fm": 6.8, "_price": 32, "birth_year": 1997},
                {"name": "Bastoni", "team": "Inter", "role": "D", "_fm": 6.2, "_price": 28, "birth_year": 1999},
                {"name": "Donnarumma", "team": "PSG", "role": "P", "_fm": 6.5, "_price": 25, "birth_year": 1999},
                {"name": "Maignan", "team": "Milan", "role": "P", "_fm": 6.3, "_price": 22, "birth_year": 1995}
            ]

        # Apply filters
        filtered_players = []
        current_year = 2025

        for player in players:
            # Search filter
            if search_query:
                player_name = (player.get('name') or '').lower()
                player_team = (player.get('team') or '').lower()
                if (search_query.lower() not in player_name and
                    search_query.lower() not in player_team):
                    continue

            # Role filter
            if role_filter:
                player_role = (player.get('role') or '').upper()
                if player_role != role_filter:
                    continue

            # Team filter
            if team_filter:
                player_team = (player.get('team') or '').lower()
                if team_filter not in player_team:
                    continue

            # U21 filter
            if u21_filter:
                birth_year = player.get('birth_year')
                if not birth_year or (current_year - birth_year) > 21:
                    continue

            # In forma filter (players with high fantamedia)
            if in_forma_filter:
                fm = player.get('_fm') or 0
                if fm < 6.5:  # Consider players "in forma" if fantamedia >= 6.5
                    continue

            filtered_players.append(player)

        # Sort by fantamedia descending
        filtered_players.sort(key=lambda x: x.get('_fm') or 0, reverse=True)

        # Limit results
        filtered_players = filtered_players[:limit]

        LOG.info(f"[Players API] Returning {len(filtered_players)} players")

        return jsonify({
            "players": filtered_players,
            "total": len(filtered_players),
            "filters_applied": {
                "search": search_query,
                "role": role_filter,
                "team": team_filter,
                "u21": u21_filter,
                "in_forma": in_forma_filter
            }
        }), 200

    except Exception as e:
        LOG.error(f"[Players API] Error: {str(e)}", exc_info=True)
        return jsonify({
            "players": [],
            "total": 0,
            "error": str(e)
        }), 500

@app.route('/api/statistics')
def api_statistics():
    """Get player statistics by role"""
    try:
        LOG.info(f"[Statistics API] Request received - Method: {request.method}")
        LOG.info(f"[Statistics API] Request args: {dict(request.args)}")

        assistant = get_assistant()
        if not assistant:
            return jsonify({
                "error": "Assistant not available",
                "role_statistics": {},
                "total_players": 0
            }), 200

        # Get query parameters for filtering
        role_filter = request.args.get('role', '').strip().upper()
        team_filter = request.args.get('team', '').strip().lower()

        LOG.info(f"[Statistics API] Filters - Role: '{role_filter}', Team: '{team_filter}'")

        # Try to ensure data is loaded
        try:
            assistant._ensure_data_loaded()
        except Exception as e:
            LOG.warning(f"[Statistics API] Data loading failed: {e}")

        # Use available data or fallback to sample
        players = []
        if hasattr(assistant, 'filtered_roster') and assistant.filtered_roster:
            players = assistant.filtered_roster
        else:
            LOG.warning("[Statistics API] Using sample data")
            players = [
                {"name": "Osimhen", "team": "Napoli", "role": "A", "_fm": 7.2, "_price": 45},
                {"name": "Vlahovic", "team": "Juventus", "role": "A", "_fm": 6.8, "_price": 40},
                {"name": "Barella", "team": "Inter", "role": "C", "_fm": 6.8, "_price": 35},
                {"name": "Theo Hernandez", "team": "Milan", "role": "D", "_fm": 6.8, "_price": 32},
                {"name": "Donnarumma", "team": "PSG", "role": "P", "_fm": 6.5, "_price": 25}
            ]

        LOG.info(f"[Statistics API] Using {len(players)} players for statistics")

        # Aggregate statistics by role
        role_stats = {}
        # When team filtering is applied, always show breakdown for all roles of that team
        # When role filtering is applied, show only that specific role
        roles = ['P', 'D', 'C', 'A'] if not role_filter else [role_filter]

        for role in roles:
            # Get players for this role
            players = []
            role_matches = 0
            team_matches = 0

            for p in assistant.filtered_roster:
                # Check role match with multiple variations
                player_role = p.get('role', '').strip().upper()
                role_raw = p.get('role_raw', '').strip().upper()

                # Enhanced role matching for Italian terms with better filtering
                is_role_match = False
                if role == "P":
                    is_role_match = (player_role in ["P", "PORTIERE", "GK", "POR"] or
                                   any(x in role_raw for x in ["PORTIER", "PORTIERE", "GK", "POR", "GOALKEEPER"]))
                elif role == "D":
                    is_role_match = (player_role in ["D", "DIFENSORE"] or
                                   any(x in role_raw for x in ["DIFENSOR", "DIFENSORE", "DEF", "DC", "RB", "LB", "TD", "TS", "TERZINO", "CENTRALE"]))
                elif role == "C":
                    is_role_match = (player_role in ["C", "CENTROCAMPISTA"] or
                                   any(x in role_raw for x in ["CENTROCAMP", "CENTROCAMPISTA", "MED", "MEZZ", "CM", "CAM", "CDM", "AM", "TQ", "MEDIANO", "TREQUARTISTA"]))
                elif role == "A":
                    is_role_match = (player_role in ["A", "ATTACCANTE"] or
                                   any(x in role_raw for x in ["ATTACC", "ATTACCANTE", "ATT", "ST", "CF", "LW", "RW", "SS", "PUN", "PRIMA PUNTA", "SECONDA PUNTA"]))

                if is_role_match:
                    role_matches += 1

                if not is_role_match:
                    continue

                # Apply team filter if specified
                team_match = True
                if team_filter:
                    player_team = p.get('team', '').strip().lower()
                    # More flexible team matching
                    team_match = (team_filter in player_team or
                                player_team in team_filter or
                                any(part in player_team for part in team_filter.split() if len(part) > 2))

                    if team_match:
                        team_matches += 1

                if not team_match:
                    continue

                # Include all players, even those with missing names
                name = p.get('name', '').strip()
                # Assign default name for players with missing names but keep them in statistics
                if not name or len(name) < 2:
                    p['display_name'] = f"Player {p.get('team', 'Unknown')} {p.get('role', 'Unknown')}"
                else:
                    p['display_name'] = name

                players.append(p)

            LOG.info(f"[Statistics] Role {role}: {role_matches} role matches, {team_matches} team matches, {len(players)} final players")

            if not players:
                role_stats[role] = {
                    'count': 0,
                    'avg_fantamedia': 0,
                    'avg_price': 0,
                    'top_players': []
                }
                continue

            # Calculate averages with safer handling
            fantamedias = []
            prices = []

            for p in players:
                fm = p.get('_fm')
                pr = p.get('_price')
                if isinstance(fm, (int, float)) and fm > 0:
                    fantamedias.append(fm)
                if isinstance(pr, (int, float)) and pr > 0:
                    prices.append(pr)

            avg_fm = round(sum(fantamedias) / len(fantamedias), 2) if fantamedias else 0
            avg_price = round(sum(prices) / len(prices), 2) if prices else 0

            # Get top players - include all players now (since we want to show the full roster)
            valid_players = []
            for p in players:
                name = p.get('name', '').strip()
                team = p.get('team', '').strip()

                # Skip non-Serie A teams only
                if team and any(excluded_team in team.lower() for excluded_team in ['newcastle', 'psg', 'al hilal', 'tottenham', 'arsenal', 'manchester', 'chelsea', 'liverpool', 'real madrid', 'barcelona', 'atletico', 'bayern', 'borussia']):
                    continue

                valid_players.append(p)

            players_sorted = sorted(valid_players, key=lambda x: -(x.get('_fm') or 0))
            top_players = []

            for p in players_sorted[:5]:
                name = p.get('name', '').strip()
                display_name = p.get('display_name', name)  # Use display_name if available
                team = p.get('team', '').strip()
                fm = p.get('_fm')
                pr = p.get('_price')

                top_players.append({
                    'name': display_name or f"Player {team or 'Unknown'} {p.get('role', 'Unknown')}",
                    'team': team or 'N/D',
                    'fantamedia': round(fm, 2) if isinstance(fm, (int, float)) and fm > 0 else 0,
                    'price': int(pr) if isinstance(pr, (int, float)) and pr > 0 else 0
                })

            LOG.info(f"[Statistics] Role {role} final: {len(valid_players)} valid players, top player: {top_players[0]['name'] if top_players else 'none'}")

            role_stats[role] = {
                'count': len(valid_players),
                'avg_fantamedia': avg_fm,
                'avg_price': avg_price,
                'top_players': top_players
            }

        # Count total filtered players
        total_filtered = 0
        for stats in role_stats.values():
            total_filtered += stats.get('count', 0)

        # Add clearer messaging about what data is being shown
        filter_description = "All Serie A players"
        if team_filter and role_filter:
            filter_description = f"{team_filter.title()} {role_filter} players"
        elif team_filter:
            filter_description = f"{team_filter.title()} players"
        elif role_filter:
            filter_description = f"All Serie A {role_filter} players"

        response_data = {
            'role_statistics': role_stats,
            'total_players': total_filtered,
            'filter_description': filter_description,
            'filters_applied': {
                'role': role_filter or 'all',
                'team': team_filter or 'all'
            },
            'success': True,
            'debug_info': {
                'data_source': 'filtered_roster',
                'source_file': 'season_roster.json',
                'total_roster_size': len(assistant.filtered_roster),
                'role_breakdown': {role: stats.get('count', 0) for role, stats in role_stats.items()},
                'sql_used': False,
                'json_processed': True,
                'is_filtered': bool(team_filter or role_filter),
                'active_filters': f"Team: {team_filter or 'none'}, Role: {role_filter or 'none'}"
            }
        }

        LOG.info(f"[Statistics API] Response generated successfully")
        LOG.info(f"[Statistics API] Filter description: {filter_description}")
        LOG.info(f"[Statistics API] Total players after filtering: {total_filtered}")
        LOG.info(f"[Statistics API] Role statistics: {role_stats}")
        LOG.info(f"[Statistics API] Debug info: {response_data['debug_info']}")

        return jsonify(response_data)

    except Exception as e:
        LOG.error(f"[Statistics API] Error generating statistics: {e}", exc_info=True)
        return jsonify({
            "error": f"Error generating statistics: {str(e)}",
            "role_statistics": {},
            "total_players": 0,
            "success": False,
            "debug_info": {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "data_source": "failed to load",
                "sql_used": False
            }
        }), 500

@app.route('/api/data-quality-report')
def data_quality_report():
    """Get data quality report"""
    try:
        assistant = get_assistant()
        if not assistant:
            return jsonify({"error": "Assistant not available"}), 500

        report = assistant.get_data_quality_report()
        return jsonify(report)
    except Exception as e:
        LOG.error(f"Error generating data quality report: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/api/user/status", methods=["GET"])
def api_user_status():
    """Get current user login status and basic info"""
    try:
        if current_user.is_authenticated:
            return jsonify({
                "logged_in": True,
                "user": {
                    "id": current_user.id,
                    "username": current_user.username,
                    "email": current_user.email,
                    "first_name": current_user.first_name,
                    "last_name": current_user.last_name,
                    "pro_expires_at": current_user.pro_expires_at.isoformat() if current_user.pro_expires_at else None,
                    "profile_image_url": current_user.profile_image_url
                }
            })
        else:
            return jsonify({
                "logged_in": False,
                "user": None
            })
    except Exception as e:
        LOG.error(f"Error in user status API: {e}")
        return jsonify({
            "logged_in": False,
            "user": None,
            "error": str(e)
        }), 500

@app.route("/api/test", methods=["GET"])
def api_test():
    try:
        a = get_assistant()
        return jsonify({
            "ok": True,
            "season_filter": getattr(a, 'season_filter', 'unknown'),
            "age_index_size": len(getattr(a, 'age_index', [])) + len(getattr(a, 'guessed_age_index', [])),
            "overrides_size": len(getattr(a, 'overrides', [])),
            "pool_size": len(getattr(a, 'filtered_roster', [])),
            "status": "Assistant loaded successfully"
        })
    except Exception as e:
        LOG.error(f"Error in api_test: {e}")
        return jsonify({
            "ok": False,
            "error": str(e),
            "status": "Error loading assistant"
        }), 500

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint for deployment"""
    try:
        # Basic health check
        return jsonify({
            "status": "healthy",
            "timestamp": time.time(),
            "deployment": os.getenv("REPLIT_DEPLOYMENT", "unknown")
        })
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500

@app.route("/api/age-coverage", methods=["GET"])
def api_age_coverage():
    a = get_assistant()
    # Calculate age coverage manually
    total_players = len(a.filtered_roster)
    players_with_age = len([p for p in a.filtered_roster if p.get("birth_year")])
    coverage_percent = (players_with_age / total_players * 100) if total_players > 0 else 0

    return jsonify({
        "total_players": total_players,
        "players_with_age": players_with_age,
        "coverage_percent": round(coverage_percent, 1),
        "age_sources": {
            "age_index": len(a.age_index),
            "overrides": len(a.overrides),
            "guessed": len(a.guessed_age_index)
        }
    })

@app.route("/api/debug-under", methods=["GET"])
def api_debug_under():
    a = get_assistant()
    role = request.args.get("role", "A")
    max_age = int(request.args.get("max_age", 21))
    take = int(request.args.get("take", 10))
    return jsonify(a.debug_under(role, max_age, take))

@app.route("/api/peek-age", methods=["GET"])
def api_peek_age():
    name = request.args.get("name","")
    team = request.args.get("team","")
    a = get_assistant()
    return jsonify(a.peek_age(name, team))

@app.route("/api/add-correction", methods=["POST"])
def api_add_correction():
    data = request.get_json() or {}
    player = data.get("player", "")
    field = data.get("field", "team")
    old_value = data.get("old_value", "")
    new_value = data.get("new_value", "")
    reason = data.get("reason", "")

    if not player or not new_value:
        return jsonify({"error": "Player and new_value are required"}), 400

    cm = get_corrections_manager()
    correction_id = cm.add_player_correction(player, field, old_value, new_value, reason)

    if correction_id:
        return jsonify({"success": True, "id": correction_id})
    else:
        return jsonify({"error": "Failed to add correction"}), 500

@app.route('/api/corrections', methods=['POST'])
def add_correction():
    try:
        data = request.get_json()
        player_name = data.get('player_name', '').strip()
        field_name = data.get('field_name', '').strip()
        old_value = data.get('old_value', '').strip()
        new_value = data.get('new_value', '').strip()
        reason = data.get('reason', 'Manual correction via API').strip()

        if not all([player_name, field_name, new_value]):
            return jsonify({"error": "player_name, field_name, and new_value are required"}), 400

        assistant = get_assistant()
        if hasattr(assistant, 'corrections_manager'):
            correction_id = assistant.corrections_manager.add_player_correction(
                player_name=player_name,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                reason=reason
            )

            if correction_id:
                return jsonify({
                    "success": True,
                    "message": f"Correction added for {player_name}",
                    "correction_id": correction_id
                })
            else:
                return jsonify({"error": "Failed to add correction"}), 500
        else:
            return jsonify({"error": "Corrections manager not available"}), 500

    except Exception as e:
        LOG.error(f"Error adding correction: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/corrections', methods=['GET'])
def get_corrections():
    try:
        assistant = get_assistant()
        if hasattr(assistant, 'corrections_manager'):
            corrections = assistant.corrections_manager.get_recent_corrections(limit=20)
            return jsonify({"corrections": corrections})
        else:
            return jsonify({"error": "Corrections manager not available"}), 500
    except Exception as e:
        LOG.error(f"Error getting corrections: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/compare', methods=['POST'])
def api_compare_players():
    """Compare multiple players"""
    try:
        data = request.get_json()
        if not data or 'players' not in data:
            return jsonify({"error": "Players list required"}), 400
        
        player_names = data.get('players', [])
        if len(player_names) < 2:
            return jsonify({"error": "At least 2 players required for comparison"}), 400
        
        assistant = get_assistant()
        if not assistant:
            return jsonify({"error": "Assistant not available"}), 500
        
        # Ensure data is loaded
        assistant._ensure_data_loaded()
        
        comparison_results = []
        
        for player_name in player_names:
            # Search for player in roster
            found_player = None
            player_name_lower = player_name.lower().strip()
            
            for player in assistant.filtered_roster:
                roster_name = (player.get('name') or '').lower().strip()
                if player_name_lower in roster_name or roster_name in player_name_lower:
                    found_player = player
                    break
            
            if found_player:
                # Format player data for comparison
                comparison_player = {
                    'name': found_player.get('name', 'N/D'),
                    'team': found_player.get('team', 'N/D'),
                    'role': found_player.get('role', 'N/D'),
                    'fantamedia': found_player.get('_fm') or found_player.get('fantamedia') or 0,
                    'price': found_player.get('_price') or found_player.get('price') or 0,
                    'appearances': found_player.get('appearances', 'N/D'),
                    'birth_year': found_player.get('birth_year', 'N/D'),
                    'age': assistant._age_from_by(found_player.get('birth_year')) if found_player.get('birth_year') else 'N/D'
                }
                comparison_results.append(comparison_player)
            else:
                # Player not found, add placeholder
                comparison_results.append({
                    'name': player_name,
                    'team': 'Non trovato',
                    'role': 'N/D',
                    'fantamedia': 0,
                    'price': 0,
                    'appearances': 'N/D',
                    'birth_year': 'N/D',
                    'age': 'N/D'
                })
        
        return jsonify({
            'comparison': comparison_results,
            'success': True,
            'count': len(comparison_results)
        })
        
    except Exception as e:
        LOG.error(f"Error in player comparison: {e}")
        return jsonify({"error": str(e)}), 500


# League Rules Management Endpoints
@app.route("/api/rules", methods=["GET"])
def api_get_rules():
    """Get all league rules"""
    rm = get_rules_manager()
    return jsonify(rm.get_rules())

@app.route("/api/rules/summary", methods=["GET"])
def api_get_rules_summary():
    """Get rules summary"""
    rm = get_rules_manager()
    return jsonify(rm.get_rules_summary())

@app.route("/api/rules/section/<section_name>", methods=["GET"])
def api_get_rules_section(section_name):
    """Get a specific rules section"""
    rm = get_rules_manager()
    section = rm.get_section(section_name)
    if section is None:
        return jsonify({"error": f"Section {section_name} not found"}), 404
    return jsonify(section)

@app.route("/api/rules/section/<section_name>", methods=["PUT"])
def api_update_rules_section(section_name):
    """Update a specific rules section"""
    rm = get_rules_manager()
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    success = rm.update_section(section_name, data)
    if success:
        return jsonify({"message": f"Section {section_name} updated successfully"})
    else:
        return jsonify({"error": f"Failed to update section {section_name}"}), 500

@app.route("/api/rules/custom", methods=["POST"])
def api_add_custom_rule():
    """Add a custom rule"""
    rm = get_rules_manager()
    data = request.get_json()
    if not data or "description" not in data:
        return jsonify({"error": "Rule description required"}), 400

    rule_type = data.get("type", "house_rules")
    success = rm.add_custom_rule(data["description"], rule_type)

    if success:
        return jsonify({"message": "Custom rule added successfully"})
    else:
        return jsonify({"error": "Failed to add custom rule"}), 500

@app.route("/api/rules/export", methods=["GET"])
def api_export_rules():
    """Export rules as formatted text"""
    rm = get_rules_manager()
    export_format = request.args.get("format", "txt")

    if export_format == "txt":
        content = rm.export_rules_txt()
        return Response(content, mimetype="text/plain")
    elif export_format == "json":
        return jsonify(rm.get_rules())
    else:
        return jsonify({"error": "Unsupported format"}), 400

@app.route("/api/rules/validate-formation", methods=["POST"])
def api_validate_formation():
    """Validate if a formation is allowed"""
    rm = get_rules_manager()
    data = request.get_json()
    if not data or "formation" not in data:
        return jsonify({"error": "Formation required"}), 400

    is_valid = rm.validate_formation(data["formation"])
    return jsonify({"formation": data["formation"], "valid": is_valid})

@app.route("/api/rules/transfer-window", methods=["GET"])
def api_check_transfer_window():
    """Check if transfer window is open"""
    rm = get_rules_manager()
    date_str = request.args.get("date")  # Optional: check specific date
    is_open = rm.is_transfer_window_open(date_str)
    return jsonify({"transfer_window_open": is_open, "date": date_str or "today"})

@app.route("/api/rules/import", methods=["POST"])
@require_login
@require_pro
def api_import_rules_document():
    """Import rules from uploaded document"""
    data = request.get_json()
    if not data or "file_path" not in data:
        return jsonify({"error": "File path required"}), 400

    file_path = data["file_path"]

    # Security check - ensure file is in attached_assets
    if not file_path.startswith("attached_assets/"):
        file_path = f"attached_assets/{file_path}"

    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404

    rm = get_rules_manager()
    success = rm.import_from_document(file_path)

    if success:
        return jsonify({"message": "Rules imported successfully!", "success": True})
    else:
        return jsonify({"error": "Failed to import rules document"}), 500


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5000, help="Port to run the server on")
    args = parser.parse_args()

    LOG.info("Starting Fantasy Football Assistant Web Interface")
    host = "0.0.0.0"
    port = args.port
    LOG.info("Server: %s:%d", host, port)
    LOG.info("App should be accessible at the preview URL")

    # Configure Flask for production deployment
    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        threaded=True,
        use_reloader=False
    )