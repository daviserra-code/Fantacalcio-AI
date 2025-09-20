# -*- coding: utf-8 -*-
from flask import Blueprint, render_template

# Blueprint isolato per la landing “website-like”.
# Non tocca la tua logica esistente: basta registrarlo in app.py / server.py.
site_bp = Blueprint(
    "site_bp",
    __name__,
    template_folder="templates",
    static_folder="static",  # usiamo /static esistente del progetto
    static_url_path="/static"
)

@site_bp.route("/")
def home():
    # /templates/index.html
    return render_template("index.html")

# Rotte comode ma non invasive: le esponiamo SOLO se le monti.
@site_bp.route("/docs")
def docs():
    # Placeholder minimale: puoi sostituire con un template vero senza toccare l’app.
    return "<div style='font-family:Inter,system-ui;padding:24px'>Documentazione in arrivo.</div>"

@site_bp.route("/healthz")
def healthz():
    return {"status": "ok", "component": "site_bp"}
