"""
web/routes_status.py - Status routes and the main dashboard page.

Provides the dashboard page (the main UI after login) and a JSON
status endpoint for getting the full application state.

Routes:
  GET /          - Redirect to dashboard
  GET /dashboard - Main dashboard page (requires login)
  GET /status    - Full state snapshot as JSON
"""

from flask import Blueprint, render_template, redirect, url_for, jsonify, current_app
from flask_login import login_required

# Create the blueprint
status_bp = Blueprint("status", __name__)


@status_bp.route("/")
@login_required
def index():
    """Redirect the root URL to the dashboard."""
    return redirect(url_for("status.dashboard"))


@status_bp.route("/dashboard")
@login_required
def dashboard():
    """
    Render the main dashboard page.

    This is the primary UI for controlling both displays. It shows:
    - Patient monitor controls (HR, SpO2, alarms)
    - X-ray viewer controls (image list, upload, slideshow settings)
    - Live status updates via SocketIO
    """
    return render_template("dashboard.html")


@status_bp.route("/status")
@login_required
def get_status():
    """
    Get a full snapshot of the application state as JSON.

    Used by the dashboard JavaScript for initial load and as a
    fallback if the SocketIO connection drops.

    Returns all shared state values including monitor vitals,
    alarm state, X-ray image list, and process status.
    """
    state = current_app.config["SHARED_STATE"]

    return jsonify({
        # Patient monitor state
        "monitor_hr": state.get("monitor_hr", 72),
        "monitor_spo2": state.get("monitor_spo2", 98),
        "monitor_alarm": state.get("monitor_alarm", None),
        "monitor_fps": state.get("monitor_fps", 0),
        "monitor_running": state.get("monitor_running", False),

        # X-ray viewer state
        "xray_images": list(state.get("xray_images", [])),
        "xray_current_index": state.get("xray_current_index", 0),
        "xray_auto_play": state.get("xray_auto_play", True),
        "xray_interval": state.get("xray_interval", 8),
        "xray_running": state.get("xray_running", False),
        "xray_status": state.get("xray_status", "no_images"),
    })
