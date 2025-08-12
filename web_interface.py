# web_interface.py
# -*- coding: utf-8 -*-

import os
import json
import logging
from flask import Flask, request, jsonify, render_template

from fantacalcio_assistant import FantacalcioAssistant

APP_PORT = int(os.getenv("PORT", "5000"))
APP_HOST = os.getenv("HOST", "0.0.0.0")

LOG = logging.getLogger("web_interface")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

app = Flask(__name__, template_folder="templates", static_folder="static")

_assistant = None
_translations_cache = {}


def get_assistant() -> FantacalcioAssistant:
    global _assistant
    if _assistant is None:
        _assistant = FantacalcioAssistant()
    return _assistant


def _deep_merge(a: dict, b: dict) -> dict:
    """
    Merge profondo: b sovrascrive a, ma preserva chiavi mancanti.
    """
    out = dict(a)  # copia
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _default_translations(lang: str) -> dict:
    # Fallback completo per evitare UndefinedError in Jinja.
    return {
        "title": "Fantacalcio Assistant",
        "subtitle": "Consigli, strategie e dati per asta e giornata",
        "placeholders": {
            "input": "Scrivi qui la tua domanda…"
        },
        "buttons": {
            "send": "Invia",
            "clear": "Pulisci",
            "reset": "Reset",
            "export": "Esporta"
        },
        "modes": {
            "classic": "Classic",
            "stats": "Statistiche",
            "scouting": "Scouting",
            "fixtures": "Calendario",
            "market": "Mercato"
        },
        "sections": {
            "quick_actions": "Azioni rapide",
            "history": "Storico",
            "output": "Risposta"
        },
        "quickActions": {
            "topFwBudget": "Top attaccanti (budget 150)",
            "lineup352_500": "Formazione 3-5-2 (500 crediti)",
            "u21Def": "2-3 difensori Under 21",
            "genoaTransfers": "Ultimi acquisti Genoa",
            "juveTransfers": "Ultimi acquisti Juventus"
        },
        "labels": {
            "mode": "Modalità",
            "language": "Lingua"
        },
        "toasts": {
            "error": "Errore imprevisto",
            "empty": "Scrivi prima un messaggio",
            "sent": "Richiesta inviata"
        },
        "footer": {
            "disclaimer": "Consigli senza garanzia. Verifica i dati."
        }
    }


def _load_translations_from_file(lang: str) -> dict:
    """
    Prova a caricare ./i18n/<lang>.json (se esiste).
    Unisce con il fallback per garantire tutte le chiavi usate dalla UI.
    """
    defaults = _default_translations(lang)
    path = os.path.join("i18n", f"{lang}.json")
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data:
                return _deep_merge(defaults, data)
    except Exception as e:
        LOG.warning("Impossibile caricare %s: %s (uso fallback)", path, e)
    return defaults


def get_translations(lang: str) -> dict:
    """
    Cache semplice per evitare IO ad ogni richiesta.
    """
    lang = (lang or "it").lower()
    if lang in _translations_cache:
        return _translations_cache[lang]
    t = _load_translations_from_file(lang)
    _translations_cache[lang] = t
    return t


@app.route("/", methods=["GET"])
def index():
    lang = request.args.get("lang", "it")
    LOG.info("Request: GET / from %s", request.remote_addr)
    LOG.info("Page view: %s, lang: %s", os.urandom(16).hex(), lang)

    t = get_translations(lang)
    return render_template("index.html", lang=lang, t=t)


@app.route("/api/chat", methods=["POST"])
def api_chat():
    LOG.info("Request: POST /api/chat from %s", request.remote_addr)
    try:
        data = request.get_json(force=True) or {}
        LOG.info("Chat request received from %s", request.remote_addr)
        LOG.info("Request data: %s", data)
        message = (data.get("message") or "").strip()
        mode = (data.get("mode") or "classic").strip()

        if not message:
            return jsonify({"response": "Dimmi pure la tua domanda 😉"}), 200

        assistant = get_assistant()
        reply = assistant.get_response(message, mode=mode, context=None)

        return jsonify({"response": reply}), 200

    except Exception as e:
        LOG.exception("Chat endpoint error: %s", e)
        return jsonify({"response": "⚠️ Servizio momentaneamente non disponibile. Riprova tra poco."}), 200


@app.route("/api/reset-chat", methods=["POST"])
def api_reset():
    global _assistant
    _assistant = None
    return jsonify({"ok": True})


@app.route("/api/export-logs", methods=["GET"])
def export_logs():
    return jsonify({"response": "Esportazione log non configurata in questa build."})


def main():
    LOG.info("Starting Fantasy Football Assistant Web Interface")
    LOG.info("Server: %s:%d", APP_HOST, APP_PORT)
    LOG.info("App should be accessible at the preview URL")
    app.run(host=APP_HOST, port=APP_PORT, debug=False)


if __name__ == "__main__":
    main()
