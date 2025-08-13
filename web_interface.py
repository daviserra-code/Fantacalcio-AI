# -*- coding: utf-8 -*-
import os
import json
import time
import logging
import threading
import subprocess
from typing import Any, Dict
from flask import Flask, request, jsonify, render_template

from fantacalcio_assistant import FantacalcioAssistant

LOG = logging.getLogger("web_interface")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret")

_ASSISTANT_SINGLETON = None
_ASSISTANT_LOCK = threading.Lock()

def get_assistant() -> FantacalcioAssistant:
    global _ASSISTANT_SINGLETON
    with _ASSISTANT_LOCK:
        if _ASSISTANT_SINGLETON is None:
            LOG.info("Initializing FantacalcioAssistant (singleton)...")
            _ASSISTANT_SINGLETON = FantacalcioAssistant()
    return _ASSISTANT_SINGLETON


# ----------------- UI -----------------
def translate(lang: str) -> Dict[str, str]:
    # dizionario minimo per evitare errori nel template
    it = {
        "title": "Fantasy Assistant",
        "subtitle": "Consigli fantacalcio con dati locali e controlli anti-hallucination",
        "participants": "Partecipanti",
        "budget": "Budget",
        "reset_chat": "Reset Chat",
        "send": "Invia",
        "welcome": "Benvenuto!",
    }
    en = {
        "title": "Fantasy Assistant",
        "subtitle": "Fantasy tips powered by your local data",
        "participants": "Participants",
        "budget": "Budget",
        "reset_chat": "Reset Chat",
        "send": "Send",
        "welcome": "Welcome!",
    }
    return it if lang == "it" else en


@app.route("/")
def index():
    lang = request.args.get("lang", "it")
    t = translate(lang)
    LOG.info("Request: GET / from %s", request.remote_addr)
    LOG.info("Page view: %s, lang: %s", os.urandom(8).hex(), lang)
    return render_template("index.html", lang=lang, t=t)


# ----------------- API -----------------
@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(force=True, silent=True) or {}
    message = data.get("message", "").strip()
    mode = data.get("mode", "classic")
    LOG.info("Request data: %s", {"message": message, "mode": mode})

    # fire-and-forget ETL refresh (non blocca la risposta)
    try:
        LOG.info("[ETL] Refresh roster avviato (background via Popen)")
        subprocess.Popen(["python", "etl_build_roster.py"])
        LOG.info("[ETL] Job di refresh lanciato")
    except Exception as e:
        LOG.info("[ETL] Popen fallita: %s", e)

    assistant = get_assistant()
    reply = assistant.get_response(message, mode=mode, context={})
    return jsonify({"response": reply})


@app.route("/api/age-coverage", methods=["GET"])
def api_age_coverage():
    a = get_assistant()
    res = a.count_age_coverage_by_role()
    return jsonify(res)


@app.route("/api/debug-under", methods=["GET"])
def api_debug_under():
    role = request.args.get("role", "D")
    max_age = int(request.args.get("max_age", "21"))
    take = int(request.args.get("take", "8"))
    a = get_assistant()
    sample = a.debug_under_sample(role, max_age=max_age, take=take)
    return jsonify({"role": role, "max_age": max_age, "count": len(sample), "items": sample})


@app.route("/api/peek-age", methods=["GET"])
def api_peek_age():
    name = request.args.get("name", "")
    team = request.args.get("team", "")
    a = get_assistant()
    out = a.peek_age(name, team)
    return jsonify(out)


# --------- Server bootstrap ----------
if __name__ == "__main__":
    LOG.info("Starting Fantasy Football Assistant Web Interface")
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))
    LOG.info("Server: %s:%d", host, port)
    LOG.info("App should be accessible at the preview URL")
    app.run(host=host, port=port, debug=False)
