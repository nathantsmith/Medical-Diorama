"""
web/routes_monitor.py - API routes for controlling the patient monitor.

These routes let the web portal dashboard set vital signs and trigger
alarms on the patient monitor display. All routes require authentication.

Routes:
  POST /monitor/set       - Set heart rate and/or SpO2 values
  POST /monitor/alarm     - Trigger or clear an alarm
  GET  /monitor/status    - Get current monitor values (JSON)
"""

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required
from shared.settings_store import save_settings

# Create the blueprint — routes are prefixed with /monitor
monitor_bp = Blueprint("monitor", __name__, url_prefix="/monitor")


@monitor_bp.route("/set", methods=["POST"])
@login_required
def set_vitals():
    """
    Set the heart rate and/or SpO2 values on the patient monitor.

    Accepts JSON body:
      {
        "hr": 72,      // Heart rate in BPM (optional, 30-250)
        "spo2": 98     // SpO2 percentage (optional, 70-100)
      }

    Returns JSON with the updated values and any validation errors.
    """
    state = current_app.config["SHARED_STATE"]
    data = request.get_json(silent=True)

    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    errors = []

    # Update heart rate if provided
    if "hr" in data:
        try:
            hr = int(data["hr"])
            if 30 <= hr <= 250:
                state["monitor_hr"] = hr
            else:
                errors.append("Heart rate must be between 30 and 250 BPM")
        except (ValueError, TypeError):
            errors.append("Heart rate must be a number")

    # Update SpO2 if provided
    if "spo2" in data:
        try:
            spo2 = int(data["spo2"])
            if 70 <= spo2 <= 100:
                state["monitor_spo2"] = spo2
            else:
                errors.append("SpO2 must be between 70 and 100%")
        except (ValueError, TypeError):
            errors.append("SpO2 must be a number")

    if errors:
        return jsonify({"error": "; ".join(errors)}), 400

    save_settings(state)

    return jsonify({
        "ok": True,
        "monitor_hr": state["monitor_hr"],
        "monitor_spo2": state["monitor_spo2"],
    })


@monitor_bp.route("/alarm", methods=["POST"])
@login_required
def set_alarm():
    """
    Trigger or clear an alarm on the patient monitor.

    Accepts JSON body:
      {
        "alarm": "hr_high"   // One of: "hr_high", "hr_low", "spo2_low", or null to clear
      }

    Valid alarm types:
      - "hr_high"  : High heart rate alarm
      - "hr_low"   : Low heart rate alarm
      - "spo2_low" : Low blood oxygen alarm
      - null        : Clear all alarms
    """
    state = current_app.config["SHARED_STATE"]
    data = request.get_json(silent=True)

    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    # Validate alarm type
    alarm = data.get("alarm")
    valid_alarms = {"hr_high", "hr_low", "spo2_low", None}

    if alarm not in valid_alarms:
        return jsonify({
            "error": f"Invalid alarm type. Must be one of: hr_high, hr_low, spo2_low, or null"
        }), 400

    # Set the alarm in shared state
    state["monitor_alarm"] = alarm
    save_settings(state)

    return jsonify({
        "ok": True,
        "monitor_alarm": state["monitor_alarm"],
    })


@monitor_bp.route("/status", methods=["GET"])
@login_required
def get_status():
    """
    Get the current patient monitor state as JSON.

    Used by the dashboard for initial page load (before SocketIO connects).

    Returns:
      {
        "monitor_hr": 72,
        "monitor_spo2": 98,
        "monitor_alarm": null,
        "monitor_fps": 30,
        "monitor_running": true
      }
    """
    state = current_app.config["SHARED_STATE"]

    return jsonify({
        "monitor_hr": state.get("monitor_hr", 72),
        "monitor_spo2": state.get("monitor_spo2", 98),
        "monitor_alarm": state.get("monitor_alarm", None),
        "monitor_fps": state.get("monitor_fps", 0),
        "monitor_running": state.get("monitor_running", False),
    })
