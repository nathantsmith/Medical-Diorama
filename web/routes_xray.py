"""
web/routes_xray.py - API routes for managing X-ray images per display.

All routes are scoped by display_id so we can run separate slideshows on
separate HDMI outputs. display_id must match one of config.XRAY_DISPLAYS.

Routes (all require auth, all prefixed with /xray/<display_id>/):
  GET    /list                - Images + current state
  POST   /upload              - Upload a new image
  DELETE /<filename>          - Delete an image
  POST   /set-index           - Jump to a specific image
  POST   /toggle-auto         - Toggle auto-advance
  POST   /set-interval        - Set auto-advance interval
  GET    /image/<filename>    - Serve an image file
"""

import os
import time

from flask import Blueprint, request, jsonify, current_app, send_from_directory, abort
from flask_login import login_required
from werkzeug.utils import secure_filename

import config
from shared.settings_store import save_settings
from shared.state import scan_xray_images

xray_bp = Blueprint("xray", __name__, url_prefix="/xray")


def _valid_display_ids():
    return {d["id"] for d in config.XRAY_DISPLAYS}


def _require_display(display_id):
    """Abort with 404 if display_id is not a configured xray display."""
    if display_id not in _valid_display_ids():
        abort(404, description=f"Unknown display '{display_id}'")


@xray_bp.route("/<display_id>/list", methods=["GET"])
@login_required
def list_images(display_id):
    """List images + playback state for one display."""
    _require_display(display_id)
    state = current_app.config["SHARED_STATE"]
    return jsonify({
        "display_id": display_id,
        "images": list(state.get(f"{display_id}_images", [])),
        "current_index": state.get(f"{display_id}_current_index", 0),
        "auto_play": state.get(f"{display_id}_auto_play", True),
        "interval": state.get(f"{display_id}_interval", config.XRAY_DEFAULT_INTERVAL),
    })


@xray_bp.route("/<display_id>/upload", methods=["POST"])
@login_required
def upload_image(display_id):
    """Upload a new image to this display's rotation."""
    _require_display(display_id)
    state = current_app.config["SHARED_STATE"]
    xray_dir = config.xray_dir_for(display_id)

    if "image" not in request.files:
        return jsonify({"error": "No image file provided"}), 400

    file = request.files["image"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400

    _, ext = os.path.splitext(file.filename)
    if ext.lower() not in config.ALLOWED_IMAGE_EXTENSIONS:
        return jsonify({
            "error": f"Invalid file type '{ext}'. Allowed: {', '.join(config.ALLOWED_IMAGE_EXTENSIONS)}"
        }), 400

    safe_name = secure_filename(file.filename)
    if not safe_name:
        safe_name = f"xray_{int(time.time())}{ext.lower()}"

    os.makedirs(xray_dir, exist_ok=True)
    save_path = os.path.join(xray_dir, safe_name)

    if os.path.exists(save_path):
        name_part, ext_part = os.path.splitext(safe_name)
        counter = 1
        while os.path.exists(save_path):
            safe_name = f"{name_part}_{counter}{ext_part}"
            save_path = os.path.join(xray_dir, safe_name)
            counter += 1

    file.save(save_path)
    scan_xray_images(state, display_id)
    save_settings(state)

    return jsonify({
        "ok": True,
        "filename": safe_name,
        "images": list(state.get(f"{display_id}_images", [])),
    })


@xray_bp.route("/<display_id>/<filename>", methods=["DELETE"])
@login_required
def delete_image(display_id, filename):
    """Delete an image from this display's rotation."""
    _require_display(display_id)
    state = current_app.config["SHARED_STATE"]
    xray_dir = config.xray_dir_for(display_id)

    safe_name = secure_filename(filename)
    file_path = os.path.join(xray_dir, safe_name)

    if not os.path.exists(file_path):
        return jsonify({"error": f"Image '{safe_name}' not found"}), 404

    try:
        os.remove(file_path)
    except OSError as e:
        return jsonify({"error": f"Failed to delete: {e}"}), 500

    scan_xray_images(state, display_id)
    save_settings(state)
    return jsonify({
        "ok": True,
        "images": list(state.get(f"{display_id}_images", [])),
    })


@xray_bp.route("/<display_id>/set-index", methods=["POST"])
@login_required
def set_index(display_id):
    """Jump to a specific image by index."""
    _require_display(display_id)
    state = current_app.config["SHARED_STATE"]
    data = request.get_json(silent=True)

    if not data or "index" not in data:
        return jsonify({"error": "Must provide 'index' in JSON body"}), 400
    try:
        index = int(data["index"])
    except (ValueError, TypeError):
        return jsonify({"error": "Index must be a number"}), 400

    images = list(state.get(f"{display_id}_images", []))
    if not images:
        return jsonify({"error": "No images in rotation"}), 400

    index = max(0, min(index, len(images) - 1))
    state[f"{display_id}_current_index"] = index
    save_settings(state)
    return jsonify({"ok": True, "current_index": index})


@xray_bp.route("/<display_id>/toggle-auto", methods=["POST"])
@login_required
def toggle_auto(display_id):
    """Toggle auto-play for one display."""
    _require_display(display_id)
    state = current_app.config["SHARED_STATE"]
    current = state.get(f"{display_id}_auto_play", True)
    state[f"{display_id}_auto_play"] = not current
    save_settings(state)
    return jsonify({"ok": True, "auto_play": state[f"{display_id}_auto_play"]})


@xray_bp.route("/<display_id>/set-interval", methods=["POST"])
@login_required
def set_interval(display_id):
    """Set the auto-advance interval (seconds) for one display."""
    _require_display(display_id)
    state = current_app.config["SHARED_STATE"]
    data = request.get_json(silent=True)

    if not data or "interval" not in data:
        return jsonify({"error": "Must provide 'interval' in JSON body"}), 400
    try:
        interval = int(data["interval"])
    except (ValueError, TypeError):
        return jsonify({"error": "Interval must be a number"}), 400
    if not (2 <= interval <= 120):
        return jsonify({"error": "Interval must be between 2 and 120 seconds"}), 400

    state[f"{display_id}_interval"] = interval
    save_settings(state)
    return jsonify({"ok": True, "interval": interval})


@xray_bp.route("/<display_id>/image/<filename>", methods=["GET"])
@login_required
def serve_image(display_id, filename):
    """Serve an image file (for web thumbnails)."""
    _require_display(display_id)
    safe_name = secure_filename(filename)
    return send_from_directory(config.xray_dir_for(display_id), safe_name)
