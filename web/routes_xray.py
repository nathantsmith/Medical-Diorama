"""
web/routes_xray.py - API routes for managing X-ray images.

These routes let the web portal upload, delete, and browse X-ray images
in the slideshow rotation. All routes require authentication.

Routes:
  GET    /xray/list         - List all images and current index
  POST   /xray/upload       - Upload a new X-ray image
  DELETE /xray/<filename>   - Remove an image from the rotation
  POST   /xray/set-index    - Jump to a specific image
  POST   /xray/toggle-auto  - Toggle auto-advance on/off
  POST   /xray/set-interval - Set the auto-advance interval
  GET    /xray/image/<name> - Serve an X-ray image file (for thumbnails)
"""

import os

from flask import Blueprint, request, jsonify, current_app, send_from_directory
from flask_login import login_required
from werkzeug.utils import secure_filename

from config import XRAY_DIR, ALLOWED_IMAGE_EXTENSIONS
from shared.state import scan_xray_images

# Create the blueprint — routes are prefixed with /xray
xray_bp = Blueprint("xray", __name__, url_prefix="/xray")


@xray_bp.route("/list", methods=["GET"])
@login_required
def list_images():
    """
    Get the list of X-ray images and current slideshow state.

    Returns JSON:
      {
        "images": ["xray1.jpg", "xray2.png", ...],
        "current_index": 0,
        "auto_play": true,
        "interval": 8
      }
    """
    state = current_app.config["SHARED_STATE"]

    return jsonify({
        "images": list(state.get("xray_images", [])),
        "current_index": state.get("xray_current_index", 0),
        "auto_play": state.get("xray_auto_play", True),
        "interval": state.get("xray_interval", 8),
    })


@xray_bp.route("/upload", methods=["POST"])
@login_required
def upload_image():
    """
    Upload a new X-ray image to the rotation.

    Accepts a multipart form upload with field name "image".
    The image is saved to data/xrays/ and the shared state is updated.

    Returns JSON with success status and updated image list.
    """
    state = current_app.config["SHARED_STATE"]

    # Check that a file was included in the upload
    if "image" not in request.files:
        return jsonify({"error": "No image file provided"}), 400

    file = request.files["image"]

    # Check that the file has a name
    if file.filename == "" or file.filename is None:
        return jsonify({"error": "No file selected"}), 400

    # Validate the file extension
    _, ext = os.path.splitext(file.filename)
    if ext.lower() not in ALLOWED_IMAGE_EXTENSIONS:
        return jsonify({
            "error": f"Invalid file type '{ext}'. Allowed: {', '.join(ALLOWED_IMAGE_EXTENSIONS)}"
        }), 400

    # Sanitize the filename to prevent path traversal attacks
    safe_name = secure_filename(file.filename)

    # If the sanitized name is empty (e.g., all special chars), generate one
    if not safe_name:
        import time
        safe_name = f"xray_{int(time.time())}{ext.lower()}"

    # Save the file to the xrays directory
    os.makedirs(XRAY_DIR, exist_ok=True)
    save_path = os.path.join(XRAY_DIR, safe_name)

    # If a file with this name already exists, add a number suffix
    if os.path.exists(save_path):
        name_part, ext_part = os.path.splitext(safe_name)
        counter = 1
        while os.path.exists(save_path):
            safe_name = f"{name_part}_{counter}{ext_part}"
            save_path = os.path.join(XRAY_DIR, safe_name)
            counter += 1

    file.save(save_path)

    # Re-scan the directory to update the shared state image list
    # This re-assigns state["xray_images"] (required for Manager proxy sync)
    scan_xray_images(state)

    return jsonify({
        "ok": True,
        "filename": safe_name,
        "images": list(state.get("xray_images", [])),
    })


@xray_bp.route("/<filename>", methods=["DELETE"])
@login_required
def delete_image(filename):
    """
    Remove an X-ray image from the rotation.

    Deletes the file from disk and updates the shared state.

    Args:
        filename: The image filename to delete (URL parameter).
    """
    state = current_app.config["SHARED_STATE"]

    # Sanitize the filename to prevent path traversal
    safe_name = secure_filename(filename)
    file_path = os.path.join(XRAY_DIR, safe_name)

    # Check that the file exists
    if not os.path.exists(file_path):
        return jsonify({"error": f"Image '{safe_name}' not found"}), 404

    # Delete the file
    try:
        os.remove(file_path)
    except OSError as e:
        return jsonify({"error": f"Failed to delete: {e}"}), 500

    # Re-scan the directory to update shared state
    scan_xray_images(state)

    return jsonify({
        "ok": True,
        "images": list(state.get("xray_images", [])),
    })


@xray_bp.route("/set-index", methods=["POST"])
@login_required
def set_index():
    """
    Jump to a specific image in the slideshow by index.

    Accepts JSON body:
      { "index": 3 }
    """
    state = current_app.config["SHARED_STATE"]
    data = request.get_json(silent=True)

    if not data or "index" not in data:
        return jsonify({"error": "Must provide 'index' in JSON body"}), 400

    try:
        index = int(data["index"])
    except (ValueError, TypeError):
        return jsonify({"error": "Index must be a number"}), 400

    images = list(state.get("xray_images", []))
    if not images:
        return jsonify({"error": "No images in rotation"}), 400

    # Clamp to valid range
    index = max(0, min(index, len(images) - 1))
    state["xray_current_index"] = index

    return jsonify({"ok": True, "current_index": index})


@xray_bp.route("/toggle-auto", methods=["POST"])
@login_required
def toggle_auto():
    """Toggle the auto-advance slideshow on or off."""
    state = current_app.config["SHARED_STATE"]
    current = state.get("xray_auto_play", True)
    state["xray_auto_play"] = not current

    return jsonify({
        "ok": True,
        "auto_play": state["xray_auto_play"],
    })


@xray_bp.route("/set-interval", methods=["POST"])
@login_required
def set_interval():
    """
    Set the auto-advance interval in seconds.

    Accepts JSON body:
      { "interval": 10 }

    Valid range: 2 to 120 seconds.
    """
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

    state["xray_interval"] = interval

    return jsonify({"ok": True, "interval": interval})


@xray_bp.route("/image/<filename>", methods=["GET"])
@login_required
def serve_image(filename):
    """
    Serve an X-ray image file for thumbnail display in the web portal.

    Args:
        filename: The image filename to serve.
    """
    safe_name = secure_filename(filename)
    return send_from_directory(XRAY_DIR, safe_name)
