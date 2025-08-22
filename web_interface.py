# -*- coding: utf-8 -*-
import uuid
import json
import logging
import subprocess
import os
import re # Import the re module
from flask import Flask, request, jsonify, session, render_template, g # Import g for application context
from flask import Response # Import Response for exporting rules

from config import HOST, PORT, LOG_LEVEL
from fantacalcio_assistant import FantacalcioAssistant
from corrections_manager import CorrectionsManager
# Assuming LeagueRulesManager is in a separate file named league_rules_manager.py
from league_rules_manager import LeagueRulesManager
from rate_limiter import RateLimiter

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
LOG = logging.getLogger("web_interface")

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = "dev-secret"  # per sessione firmata; metti in .env se vuoi

# Initialize rate limiter (10 requests per hour for deployed app)
rate_limiter = RateLimiter(max_requests=10, time_window=3600)

# ---------- Singleton ----------
def get_assistant() -> FantacalcioAssistant:
    # Use Flask's application context (g) for singletons
    if not hasattr(g, 'assistant'):
        LOG.info("Initializing FantacalcioAssistant (singleton)...")
        g.assistant = FantacalcioAssistant()
    else:
        # Refresh corrections data without full re-initialization
        if hasattr(g.assistant, 'corrections_manager') and g.assistant.corrections_manager:
            # Force reload of corrections cache
            if hasattr(g.assistant.corrections_manager, '_excluded_players_cache'):
                delattr(g.assistant.corrections_manager, '_excluded_players_cache')
    return g.assistant

def get_corrections_manager() -> CorrectionsManager:
    # Use Flask's application context (g) for singletons
    cm = g.get('_corrections_manager')
    if cm is None:
        assistant = get_assistant()
        cm = CorrectionsManager(knowledge_manager=assistant.km)
        g._corrections_manager = cm
    return cm

def get_rules_manager() -> LeagueRulesManager:
    # Use Flask's application context (g) for singletons
    if not hasattr(g, 'rules_manager'):
        LOG.info("Initializing LeagueRulesManager (singleton)...")
        g.rules_manager = LeagueRulesManager()
    return g.rules_manager

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

@app.route("/", methods=["GET"])
def index():
    lang = request.args.get("lang", "it")
    page_id = uuid.uuid4().hex[:16]
    LOG.info("Request: GET / from %s", request.remote_addr)
    LOG.info("Page view: %s, lang: %s", page_id, lang)
    return render_template("index.html", lang=lang, t=T.get(lang,T["it"]))

@app.route("/api/chat", methods=["POST"])
def api_chat():
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

    # Handle exclusions (rimuovi/escludi commands)
    exclusion_response = handle_exclusion(msg, state)
    if exclusion_response:
        set_state(state)
        return jsonify({"response": exclusion_response})

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

    try:
        reply, new_state = assistant.respond(msg, mode=mode, state=state, context_messages=context_messages)
    except Exception as e:
        LOG.error("Error in assistant.respond: %s", e, exc_info=True)
        reply = f"⚠️ Errore temporaneo del servizio. Messaggio: {msg[:50]}... - Riprova tra poco."
        new_state = state

    # Apply exclusions if any (both session and persistent)
    excluded_players = new_state.get("excluded_players", [])
    reply = apply_exclusions_to_text(reply, excluded_players)

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

    # Update conversation history
    new_state.setdefault("conversation_history", []).append({
        "role": "user",
        "content": msg
    })
    new_state["conversation_history"].append({
        "role": "assistant",
        "content": reply
    })

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

    # Pattern: "rimuovi/escludi [player name]"
    import re

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
                excluded_players = state.setdefault("excluded_players", [])
                if player_name not in excluded_players:
                    excluded_players.append(player_name)
                    return f"✅ **{player_name}** è stato escluso dalle future liste. Questa esclusione è attiva per tutta la sessione."
                else:
                    return f"**{player_name}** è già escluso dalle liste."

    return None

def apply_exclusions_to_text(text: str, excluded_players: list) -> str:
    """Remove excluded players from response text"""
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
        
        for excluded in all_excluded:
            excluded_lower = excluded.lower().strip()
            
            # Handle special characters by creating multiple search variants
            import re
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
                    
                # Pattern 1: Look for the name in **bold** format (most common in responses)
                bold_pattern = rf'\*\*[^*]*{re.escape(pattern)}[^*]*\*\*'
                if re.search(bold_pattern, line_lower):
                    should_exclude = True
                    LOG.info(f"Excluding line with bold player '{excluded}' (pattern: {pattern}): {line.strip()}")
                    break
                
                # Pattern 2: Check if main parts of the name appear
                pattern_parts = [part for part in pattern.split() if len(part) > 2]
                if pattern_parts:
                    # Check if all significant parts are present
                    parts_found = sum(1 for part in pattern_parts if part in line_lower)
                    if parts_found >= len(pattern_parts) * 0.7:  # At least 70% of parts match
                        should_exclude = True
                        LOG.info(f"Excluding line containing name parts from '{excluded}' (pattern: {pattern}): {line.strip()}")
                        break
                
                # Pattern 3: Direct substring match for substantial names
                if len(pattern) > 4 and pattern in line_lower:
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

    return None

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
def api_rate_limit_status():
    client_ip = rate_limiter._get_client_key(request)
    remaining = rate_limiter.get_remaining_requests(request)
    reset_time = rate_limiter.get_reset_time(request)
    
    # Get request history for this client (for debugging)
    client_requests = rate_limiter.requests.get(client_ip, [])
    request_count = len(client_requests)

    return jsonify({
        "is_deployed": rate_limiter.is_deployed,
        "limit": rate_limiter.max_requests,
        "remaining": remaining,
        "used": request_count,
        "reset_time": reset_time,
        "window_seconds": rate_limiter.time_window,
        "client_id": client_ip[:8] + "..." if len(client_ip) > 8 else client_ip,  # Partial IP for debugging
        "tracking_method": "IP-based" if rate_limiter.is_deployed else "Development (no limits)"
    })

@app.route("/api/test", methods=["GET"])
def api_test():
    a = get_assistant()
    return jsonify({
        "ok": True,
        "season_filter": a.season_filter,
        "age_index_size": len(a.age_index) + len(a.guessed_age_index),
        "overrides_size": len(a.overrides),
        "pool_size": len(a.filtered_roster),
        "status": "Assistant loaded successfully"
    })

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

@app.route("/api/corrections", methods=["GET"])
def api_get_corrections():
    limit = int(request.args.get("limit", 50))
    cm = get_corrections_manager()
    corrections = cm.get_corrections(limit)
    return jsonify({"corrections": corrections})

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