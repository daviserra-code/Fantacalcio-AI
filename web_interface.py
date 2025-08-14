# -*- coding: utf-8 -*-
import uuid
import json
import logging
import subprocess
from flask import Flask, request, jsonify, session, render_template

from config import HOST, PORT, LOG_LEVEL
from fantacalcio_assistant import FantacalcioAssistant

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

    reply, new_state = assistant.respond(msg, mode=mode, state=state)
    set_state(new_state)
    return jsonify({"response": reply})

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

if __name__ == "__main__":
    LOG.info("Starting Fantasy Football Assistant Web Interface")
    LOG.info("Server: %s:%d", HOST, PORT)
    LOG.info("App should be accessible at the preview URL")
    app.run(host=HOST, port=PORT)
