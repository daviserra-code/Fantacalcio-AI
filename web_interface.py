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

    reply, new_state = assistant.respond(msg, mode=mode, state=state, context_messages=context_messages)

    # Apply any corrections to the reply
    if corrections_manager:
        try:
            corrected_reply, applied_corrections = corrections_manager.apply_corrections_to_text(reply)
            if applied_corrections:
                LOG.info(f"Applied corrections: {applied_corrections}")
                reply = corrected_reply
        except Exception as e:
            LOG.error(f"Error applying corrections: {e}")
            # Continue with original reply if correction fails

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

    # Pattern: "X non gioca più nel/in Y" or "X gioca nel/in Y in Francia/etc"
    import re

    # Enhanced patterns for various correction formats
    patterns = [
        # "X non gioca più nel Y ma gioca nel Z"
        r"(\w+(?:\s+\w+)*)\s+non\s+gioca\s+più\s+nel\s+(\w+)(?:\s+ma\s+gioca\s+(?:nel|in)\s+(\w+(?:\s+\w+)*))?",
        # "X gioca ora nel Y"
        r"(\w+(?:\s+\w+)*)\s+gioca\s+ora\s+(?:nel|in)\s+(\w+(?:\s+\w+)*)",
        # "X non gioca più nel Y"
        r"(\w+(?:\s+\w+)*)\s+non\s+gioca\s+più\s+(?:nel|in)\s+(\w+(?:\s+\w+)*)",
        # "X gioca nel Y in Francia/etc"
        r"(\w+(?:\s+\w+)*)\s+gioca\s+(?:nel|in)\s+(\w+(?:\s+\w+)*)\s+in\s+(\w+(?:\s+\w+)*)",
        # "X è stato trasferito al Y"
        r"(\w+(?:\s+\w+)*)\s+è\s+stato\s+trasferito\s+(?:al|alla|all')\s+(\w+(?:\s+\w+)*)"
    ]

    for pattern in patterns:
        match = re.search(pattern, msg, re.IGNORECASE)
        if match:
            player = match.group(1).strip()

            if len(match.groups()) >= 3 and match.group(3):  # Pattern with old and new team
                old_team = match.group(2).strip()
                new_team = match.group(3).strip()

                correction_id = corrections_manager.add_player_correction(
                    player_name=player,
                    field_name="team",
                    old_value=old_team,
                    new_value=new_team,
                    reason=f"Trasferimento confermato dall'utente: {player} {old_team} -> {new_team}"
                )
                return f"✅ **Correzione salvata**: {player} è passato da {old_team} a {new_team}. Questa informazione è stata aggiunta al sistema."

            elif len(match.groups()) >= 2:  # Pattern with just new team or old team
                team = match.group(2).strip()

                if "non gioca più" in msg_lower:
                    correction_id = corrections_manager.add_player_correction(
                        player_name=player,
                        field_name="team",
                        old_value=team,
                        new_value="nuovo club",
                        reason=f"Trasferimento confermato dall'utente: {player} ha lasciato {team}"
                    )
                    return f"✅ **Correzione salvata**: {player} non gioca più nel {team}. Questa informazione è stata aggiunta al sistema."

                else:  # "gioca ora nel" or "trasferito"
                    correction_id = corrections_manager.add_player_correction(
                        player_name=player,
                        field_name="team",
                        old_value="precedente team",
                        new_value=team,
                        reason=f"Trasferimento confermato dall'utente: {player} -> {team}"
                    )
                    return f"✅ **Correzione salvata**: {player} ora gioca nel {team}. Questa informazione è stata aggiunta al sistema."

            break  # Exit after first match
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