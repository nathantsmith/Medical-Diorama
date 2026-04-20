"""
web/routes_ransomware.py - API routes for ransomware mode controls and assets.
"""

import os
import time

from flask import Blueprint, abort, current_app, jsonify, request, send_from_directory
from flask_login import login_required
from werkzeug.utils import secure_filename

import config
from shared.ransomware import (
    get_image_filename,
    get_image_version,
    image_state_key,
    image_version_key,
    is_valid_target,
    ransomware_targets,
    set_image_filename,
    set_web_enabled,
)
from shared.settings_store import save_settings

ransomware_bp = Blueprint("ransomware", __name__, url_prefix="/ransomware")


def _require_target(target):
    """Abort with 404 if the ransomware target is unknown."""
    if not is_valid_target(target):
        abort(404, description=f"Unknown ransomware target '{target}'")


def _status_payload(state):
    """Build a consistent ransomware status response."""
    payload = {
        "ok": True,
        "ransomware_web_enabled": state.get("ransomware_web_enabled", False),
        "ransomware_gpio_asserted": state.get("ransomware_gpio_asserted", False),
        "ransomware_active": state.get("ransomware_active", False),
        "targets": ransomware_targets(),
    }
    for target in ransomware_targets():
        payload[image_state_key(target)] = get_image_filename(state, target)
        payload[image_version_key(target)] = get_image_version(state, target)
    return payload


@ransomware_bp.route("/status", methods=["GET"])
@login_required
def get_status():
    """Return the current ransomware mode state and configured assets."""
    return jsonify(_status_payload(current_app.config["SHARED_STATE"]))


@ransomware_bp.route("/toggle", methods=["POST"])
@login_required
def toggle():
    """Toggle or explicitly set the dashboard-controlled ransomware flag."""
    state = current_app.config["SHARED_STATE"]
    data = request.get_json(silent=True) or {}

    if "enabled" in data:
        enabled = bool(data["enabled"])
    else:
        enabled = not state.get("ransomware_web_enabled", False)

    set_web_enabled(state, enabled)
    save_settings(state)
    return jsonify(_status_payload(state))


@ransomware_bp.route("/<target>/upload", methods=["POST"])
@login_required
def upload(target):
    """Upload or replace the ransomware image for a single display target."""
    _require_target(target)
    state = current_app.config["SHARED_STATE"]

    if "image" not in request.files:
        return jsonify({"error": "No image file provided"}), 400

    file = request.files["image"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400

    _, ext = os.path.splitext(file.filename)
    if ext.lower() not in config.ALLOWED_IMAGE_EXTENSIONS:
        return jsonify({"error": f"Invalid file type '{ext}'"}), 400

    safe_name = secure_filename(file.filename)
    if not safe_name:
        safe_name = f"ransomware_{target}_{int(time.time())}{ext.lower()}"

    target_dir = config.ransomware_dir_for(target)
    os.makedirs(target_dir, exist_ok=True)

    for filename in os.listdir(target_dir):
        file_path = os.path.join(target_dir, filename)
        if os.path.isfile(file_path):
            os.remove(file_path)

    save_path = os.path.join(target_dir, safe_name)
    file.save(save_path)
    set_image_filename(state, target, safe_name)
    save_settings(state)

    payload = _status_payload(state)
    payload["target"] = target
    payload["filename"] = safe_name
    return jsonify(payload)


@ransomware_bp.route("/<target>", methods=["DELETE"])
@login_required
def delete(target):
    """Delete the configured ransomware image for one display target."""
    _require_target(target)
    state = current_app.config["SHARED_STATE"]
    target_dir = config.ransomware_dir_for(target)

    filename = get_image_filename(state, target)
    if filename:
        file_path = os.path.join(target_dir, filename)
        if os.path.exists(file_path):
            os.remove(file_path)

    if os.path.isdir(target_dir):
        for extra_name in os.listdir(target_dir):
            extra_path = os.path.join(target_dir, extra_name)
            if os.path.isfile(extra_path):
                os.remove(extra_path)

    set_image_filename(state, target, None)
    save_settings(state)
    payload = _status_payload(state)
    payload["target"] = target
    return jsonify(payload)


@ransomware_bp.route("/<target>/image/<filename>", methods=["GET"])
@login_required
def serve_image(target, filename):
    """Serve a ransomware image for dashboard previews."""
    _require_target(target)
    safe_name = secure_filename(filename)
    return send_from_directory(config.ransomware_dir_for(target), safe_name)
