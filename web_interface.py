# -*- coding: utf-8 -*-
import os
import uuid
import json
import logging
import subprocess
from flask import Flask, request, jsonify, session, render_template

from fantacalcio_assistant import FantacalcioAssistant

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
LOG = logging.getLogger("web_interface")

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret")  # necessario per session

# ---------------- Singleton Assistant ----------------
_assistant_singleton = None
def get_assistant() -> FantacalcioAssistant:
    global _assistant_singleton
    if _assistant_singleton is None:
        LOG.info("Initializing FantacalcioAssistant (singleton)...")
        _assistant_singleton = FantacalcioAssistant()
    return _assistant_singleton

# ---------------- In-memory chat histories per session ----------------
_chat_histories = {}  # sid -> list[ {role, content} ]

def get_sid() -> str:
    sid = session.get("sid")
    if not sid:
        sid = uuid.uuid4().hex[:16]
        session["sid"] = sid
    return sid

# ---------------- Translations (minime) ----------------
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
    },
    "en": {
        "title": "Fantasy Football Assistant",
        "subtitle": "Auction tips, lineups & strategy",
        "participants": "Participants",
        "budget": "Budget",
        "reset_chat": "Reset Chat",
        "welcome": "Hi! I can help with fantasy football.",
        "send": "Send",
        "search_placeholder": "Search players/clubs/metrics",
        "all_roles": "All",
        "goalkeeper": "Goalkeeper",
        "defender": "Defender",
        "midfielder": "Midfielder",
        "forward": "Forward",
    },
}

# ---------------- Routes ----------------
@app.route("/", methods=["GET"])
def index():
    lang = request.args.get("lang", "it")
    if lang not in T: lang = "it"
    page_id = uuid.uuid4().hex[:16]
    LOG.info("Request: GET / from %s", request.remote_addr)
    LOG.info("Page view: %s, lang: %s", page_id, lang)
    return render_template("index.html", lang=lang, t=T[lang])

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(force=True, silent=True) or {}
    msg = (data.get("message") or "").strip()
    mode = (data.get("mode") or "classic").strip()
    LOG.info("Request data: %s", data)

    # avvia ETL in background (non-bloccante)
    try:
        import etl_runner  # se esiste
        LOG.info("[ETL] Refresh roster avviato (background via etl_runner)")
        etl_runner.refresh_roster_async()
        LOG.info("[ETL] Job di refresh lanciato")
    except Exception as e:
        LOG.info("[ETL] Refresh roster avviato (background via Popen)")
        try:
            subprocess.Popen(["python", "etl_build_roster.py"])
            LOG.info("[ETL] Job di refresh lanciato")
        except Exception as e2:
            LOG.warning("[ETL] impossibile avviare ETL: %s", e2)

    if not msg:
        return jsonify({"response": "Scrivi un messaggio."})

    # contesto di sessione
    sid = get_sid()
    hist = _chat_histories.setdefault(sid, [])
    # (opzionale) mantieni le ultime n interazioni
    context = {"history": hist[-8:]}  # per eventuale uso futuro

    # assistant (singleton)
    assistant = get_assistant()
    reply = assistant.get_response(msg, mode=mode, context=context)

    # salva cronologia
    hist.append({"role": "user", "content": msg})
    hist.append({"role": "assistant", "content": reply})

    return jsonify({"response": reply})

@app.route("/api/reset-chat", methods=["POST"])
def api_reset_chat():
    sid = get_sid()
    _chat_histories[sid] = []
    return jsonify({"ok": True})

@app.route("/api/test", methods=["GET"])
def api_test():
    a = get_assistant()
    cov = a.get_age_coverage()
    return jsonify({
        "ok": True,
        "season_filter": a.season_filter,
        "age_index_size": len(a.age_index),
        "overrides_size": len(a.overrides),
        "filtered_pool": sum(v["total"] for v in cov.values()),
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

# ---------------- Main ----------------
if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))
    LOG.info("Starting Fantasy Football Assistant Web Interface")
    LOG.info("Server: %s:%d", host, port)
    LOG.info("App should be accessible at the preview URL")
    app.run(host=host, port=port)
