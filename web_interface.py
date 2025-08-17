# -*- coding: utf-8 -*-
import uuid
import json
import logging
import subprocess
import re # Import the re module
from flask import Flask, request, jsonify, session, render_template

from config import HOST, PORT, LOG_LEVEL
from fantacalcio_assistant import FantacalcioAssistant
from corrections_manager import CorrectionsManager

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
LOG = logging.getLogger("web_interface")

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = "dev-secret"  # per sessione firmata; metti in .env se vuoi

# ---------- Singleton ----------
def get_assistant() -> FantacalcioAssistant:
    inst = app.config.get("_assistant_instance")
    if inst is None:
        LOG.info("Initializing FantacalcioAssistant (singleton)...")
        inst = FantacalcioAssistant()
        app.config["_assistant_instance"] = inst
    return inst

def get_corrections_manager() -> CorrectionsManager:
    cm = app.config.get("_corrections_manager")
    if cm is None:
        assistant = get_assistant()
        cm = CorrectionsManager(knowledge_manager=assistant.km)
        app.config["_corrections_manager"] = cm
    return cm

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
    data = request.get_json(force=True, silent=True) or {}
    msg  = (data.get("message") or "").strip()
    mode = (data.get("mode") or "classic").strip()

    LOG.info("Request data: %s", data)

    # Best-effort: avvia ETL senza bloccare
    try:
        subprocess.Popen(["python", "etl_build_roster.py"])
        LOG.info("[ETL] Job di refresh lanciato")
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

    # Apply exclusions to the reply
    if excluded_players:
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
    return jsonify({"response": reply})

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
    if not excluded_players:
        return text

    lines = text.split('\n')
    filtered_lines = []

    for line in lines:
        # Skip lines that contain excluded players
        should_exclude = False
        for excluded in excluded_players:
            # Case-insensitive check
            if excluded.lower() in line.lower():
                should_exclude = True
                break

        if not should_exclude:
            filtered_lines.append(line)

    return '\n'.join(filtered_lines)

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
                result = fantacalcio_assistant.remove_player_permanently(player_name)
                # Force reload of the assistant's data to apply changes immediately
                fantacalcio_assistant.roster = fantacalcio_assistant.corrections_manager.apply_corrections_to_data(fantacalcio_assistant.roster)
                fantacalcio_assistant._make_filtered_roster()
                return result
            except Exception as e:
                return f"❌ Errore nell'applicare la correzione: {e}"

    # Pattern for team updates: "sposta [player] a [team]" or "[player] gioca nel [team]"
    team_update_patterns = [
        r"(.+?)\s+(?:gioca\s+nel|è\s+al|è\s+del|trasferito\s+al|al)\s+(.+)$",
        r"sposta\s+(.+?)\s+(?:al|nel|a)\s+(.+)$",
        r"aggiorna\s+(.+?)\s+(?:al|nel|a)\s+(.+)$"
    ]

    for pattern in team_update_patterns:
        match = re.search(pattern, message_lower)
        if match:
            player_name = match.group(1).strip().title()
            new_team = match.group(2).strip().title()

            try:
                result = fantacalcio_assistant.update_player_data(player_name, team=new_team)
                return f"✅ {result}"
            except Exception as e:
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

@app.route("/api/test", methods=["GET"])
def api_test():
    a = get_assistant()
    cov = a.get_age_coverage()
    return jsonify({
        "ok": True,
        "season_filter": a.season_filter,
        "age_index_size": len(a.age_index) + len(a.guessed_age_index),
        "overrides_size": len(a.overrides),
        "pool_size": len(a.filtered_roster),
        "coverage": cov
    })

@app.route("/api/age-coverage", methods=["GET"])
def api_age_coverage():
    a = get_assistant()
    return jsonify(a.get_age_coverage())

@app.route("/api/debug-under", methods=["GET"])
def api_debug_under():
    role = (request.args.get("role") or "D").upper()[:1]
    a = get_assistant()
    return jsonify(a.debug_under(role))

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
        host=host,
        port=port,
        debug=False,
        threaded=True,
        use_reloader=False,
        processes=1
    )