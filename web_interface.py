# -*- coding: utf-8 -*-
import uuid
import json
import logging
import subprocess
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

    # Check for corrections first
    correction_response = handle_correction(msg, corrections_manager)
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

    # Add conversation context
    state.setdefault("conversation_history", [])
    context_messages = state["conversation_history"][-10:]  # Keep last 10 messages
    
    reply, new_state = assistant.respond(msg, mode=mode, state=state, context_messages=context_messages)
    
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

def handle_correction(msg: str, corrections_manager: CorrectionsManager) -> str:
    """Detect and handle correction statements"""
    msg_lower = msg.lower()
    
    # Pattern: "X gioca ora nel/in Y" or "X non gioca più nel/in Y"
    if any(phrase in msg_lower for phrase in ["gioca ora nel", "gioca ora in", "non gioca più nel", "non gioca più in"]):
        import re
        
        # Extract player and team
        pattern = r"(\w+(?:\s+\w+)*)\s+(gioca ora nel|gioca ora in|non gioca più nel|non gioca più in)\s+(\w+(?:\s+\w+)*)"
        match = re.search(pattern, msg, re.IGNORECASE)
        
        if match:
            player = match.group(1).strip()
            action = match.group(2).strip()
            team = match.group(3).strip()
            
            if "gioca ora" in action:
                correction_id = corrections_manager.add_player_correction(
                    player_name=player,
                    field_name="team",
                    old_value="precedente team",
                    new_value=team,
                    reason=f"Trasferimento confermato dall'utente: {player} -> {team}"
                )
                return f"✅ **Correzione salvata**: {player} ora gioca nel {team}. Questa informazione è stata aggiunta al sistema per future ricerche."
            
            elif "non gioca più" in action:
                correction_id = corrections_manager.add_player_correction(
                    player_name=player,
                    field_name="team",
                    old_value=team,
                    new_value="nuovo team",
                    reason=f"Trasferimento confermato dall'utente: {player} ha lasciato {team}"
                )
                return f"✅ **Correzione salvata**: {player} non gioca più nel {team}. Questa informazione è stata aggiunta al sistema."
    
    # Pattern: "X è stato trasferito a Y"
    if "trasferito" in msg_lower:
        pattern = r"(\w+(?:\s+\w+)*)\s+è stato trasferito\s+(?:a|al|alla|all')\s+(\w+(?:\s+\w+)*)"
        match = re.search(pattern, msg, re.IGNORECASE)
        
        if match:
            player = match.group(1).strip()
            team = match.group(2).strip()
            
            correction_id = corrections_manager.add_player_correction(
                player_name=player,
                field_name="team",
                old_value="precedente team",
                new_value=team,
                reason=f"Trasferimento confermato dall'utente: {player} -> {team}"
            )
            return f"✅ **Correzione salvata**: {player} è stato trasferito al {team}. Questa informazione è stata aggiunta al sistema."
    
    return None

@app.route("/api/reset-chat", methods=["POST"])
def api_reset_chat():
    set_state({})
    return jsonify({"ok": True})

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
    parser.add_argument("--port", type=int, default=3000, help="Port to run the server on")
    args = parser.parse_args()

    LOG.info("Starting Fantasy Football Assistant Web Interface")
    host = "0.0.0.0"
    port = args.port
    LOG.info("Server: %s:%d", host, port)
    LOG.info("App should be accessible at the preview URL")
    app.run(host=host, port=port, debug=False)