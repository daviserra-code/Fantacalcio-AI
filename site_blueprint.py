# -*- coding: utf-8 -*-
from flask import Blueprint, render_template

# Blueprint isolato per la landing "website-like".
# Non tocca la tua logica esistente: basta registrarlo in app.py / server.py.
site_bp = Blueprint(
    "site_bp",
    __name__,
    template_folder="templates",
    static_folder="static",  # usiamo /static esistente del progetto
    static_url_path="/static"
)

def _render_app_interface():
    """Shared helper to render the app interface with translations."""
    from flask import request
    from flask_login import current_user
    
    # Centralized translations
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
    
    lang = request.args.get("lang", "it")
    return render_template("index.html", 
                         lang=lang, 
                         t=T.get(lang, T["it"]), 
                         user=current_user if current_user.is_authenticated else None)

@site_bp.route("/")
def home():
    """
    Desktop homepage with custom design but working search functionality.
    """
    return render_template("index_desktop.html")

# Rotte comode ma non invasive: le esponiamo SOLO se le monti.
@site_bp.route("/docs")
def docs():
    # Placeholder minimale: puoi sostituire con un template vero senza toccare l'app.
    return "<div style='font-family:Inter,system-ui;padding:24px'>Documentazione in arrivo.</div>"

@site_bp.route("/healthz")
def healthz():
    return {"status": "ok", "component": "site_bp"}

@site_bp.route("/app")
def app():
    """Route for backward compatibility - serves the same app interface as homepage."""
    return _render_app_interface()