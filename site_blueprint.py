# -*- coding: utf-8 -*-
from flask import Blueprint, render_template, redirect, url_for
from device_detector import is_mobile_device, get_device_type, get_ui_mode

# Blueprint isolato per la landing "website-like".
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
    """
    Device-aware homepage that serves different UIs:
    - Mobile devices: Original mobile-friendly interface
    - Desktop/Tablet: New web-like interface
    """
    device_type = get_device_type()
    ui_mode = get_ui_mode()
    
    if ui_mode == 'mobile':
        # Serve mobile UI - redirect to main app interface
        return redirect('/app')
    else:
        # Serve desktop/tablet UI - new web-like interface
        return render_template("index_desktop.html")

# Rotte comode ma non invasive: le esponiamo SOLO se le monti.
@site_bp.route("/docs")
def docs():
    # Placeholder minimale: puoi sostituire con un template vero senza toccare l'app.
    return "<div style='font-family:Inter,system-ui;padding:24px'>Documentazione in arrivo.</div>"

@site_bp.route("/healthz")
def healthz():
    return {"status": "ok", "component": "site_bp"}

# Add /app route to serve mobile UI
@site_bp.route("/app")
def app():
    """Route for the mobile app interface - serves the original mobile UI."""
    return render_template("index.html")