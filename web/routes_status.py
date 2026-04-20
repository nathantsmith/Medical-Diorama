"""
web/routes_status.py - Status routes and the main dashboard page.

Routes:
  GET /          - Redirect to dashboard
  GET /dashboard - Main dashboard page (requires login)
  GET /status    - Full state snapshot as JSON
"""

from flask import Blueprint, render_template, redirect, url_for, jsonify, current_app
from flask_login import login_required

from config import XRAY_DISPLAYS, XRAY_DEFAULT_INTERVAL
from shared.ransomware import ransomware_targets

status_bp = Blueprint("status", __name__)


@status_bp.route("/")
@login_required
def index():
    return redirect(url_for("status.dashboard"))


@status_bp.route("/dashboard")
@login_required
def dashboard():
    return render_template(
        "dashboard.html",
        xray_displays=XRAY_DISPLAYS,
        ransomware_targets=ransomware_targets(),
    )


@status_bp.route("/status")
@login_required
def get_status():
    """Full snapshot of application state as JSON, including per-display xray keys."""
    state = current_app.config["SHARED_STATE"]

    payload = {
        "monitor_hr": state.get("monitor_hr", 72),
        "monitor_spo2": state.get("monitor_spo2", 98),
        "monitor_alarm": state.get("monitor_alarm", None),
        "monitor_fps": state.get("monitor_fps", 0),
        "monitor_running": state.get("monitor_running", False),
        "ransomware_web_enabled": state.get("ransomware_web_enabled", False),
        "ransomware_gpio_asserted": state.get("ransomware_gpio_asserted", False),
        "ransomware_active": state.get("ransomware_active", False),
        "ransomware_targets": ransomware_targets(),
        "xray_displays": [d["id"] for d in XRAY_DISPLAYS],
    }
    for target in ransomware_targets():
        payload[f"ransomware_{target}_image"] = state.get(
            f"ransomware_{target}_image", None
        )
        payload[f"ransomware_{target}_version"] = state.get(
            f"ransomware_{target}_version", 0
        )
    for display in XRAY_DISPLAYS:
        did = display["id"]
        payload[f"{did}_images"] = list(state.get(f"{did}_images", []))
        payload[f"{did}_current_index"] = state.get(f"{did}_current_index", 0)
        payload[f"{did}_auto_play"] = state.get(f"{did}_auto_play", True)
        payload[f"{did}_interval"] = state.get(f"{did}_interval", XRAY_DEFAULT_INTERVAL)
        payload[f"{did}_running"] = state.get(f"{did}_running", False)
        payload[f"{did}_status"] = state.get(f"{did}_status", "no_images")
    return jsonify(payload)
