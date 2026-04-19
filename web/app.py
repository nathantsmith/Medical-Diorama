"""
web/app.py - Flask application factory and SocketIO setup.

Creates the Flask web application, registers all blueprints (auth, monitor,
xray, status), initializes SocketIO for real-time updates, and starts a
background thread that pushes state updates to connected browsers.

The application factory pattern (create_app) lets us configure the app
differently for testing vs. production.
"""

import os
import time
import logging
import threading

from flask import Flask
from flask_socketio import SocketIO
from dotenv import load_dotenv

from config import WEB_HOST, WEB_PORT, BASE_DIR, XRAY_DISPLAYS

logger = logging.getLogger(__name__)

# The SocketIO instance — created in create_app(), accessible for imports
socketio = SocketIO()


def create_app(state):
    """
    Create and configure the Flask application.

    Args:
        state: The shared multiprocessing Manager dict. Stored in
               app.config so routes can access it via current_app.

    Returns:
        Tuple of (Flask app, SocketIO instance).
    """
    # Load environment variables from .env file (if it exists)
    load_dotenv(os.path.join(BASE_DIR, ".env"))

    # Create the Flask app
    app = Flask(
        __name__,
        template_folder=os.path.join(BASE_DIR, "web", "templates"),
        static_folder=os.path.join(BASE_DIR, "web", "static"),
    )

    # Configure Flask
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max upload size

    # Store the shared state in app config so routes can access it
    app.config["SHARED_STATE"] = state

    # Initialize Flask-Login (authentication)
    from web.auth import init_auth, auth_bp
    init_auth(app)

    # Initialize Flask-SocketIO (real-time updates)
    socketio.init_app(app, cors_allowed_origins="*")

    # Register blueprints (route groups)
    from web.routes_monitor import monitor_bp
    from web.routes_xray import xray_bp
    from web.routes_status import status_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(monitor_bp)
    app.register_blueprint(xray_bp)
    app.register_blueprint(status_bp)

    # Set up SocketIO event handlers
    _setup_socketio_events(state)

    return app, socketio


def _setup_socketio_events(state):
    """
    Register SocketIO event handlers.

    Handles:
      - "request_status": Client requests an immediate state push.

    Args:
        state: The shared state dict.
    """
    @socketio.on("request_status")
    def handle_status_request():
        """Client requested an immediate status update."""
        socketio.emit("status_update", _get_state_snapshot(state))


def _get_state_snapshot(state):
    """
    Build a JSON-serializable snapshot of the full application state.

    Reads all values from the shared Manager dict and returns them
    as a plain dictionary suitable for sending over SocketIO.

    Args:
        state: The shared Manager dict.

    Returns:
        A plain dict with all state values.
    """
    snapshot = {
        "monitor_hr": state.get("monitor_hr", 72),
        "monitor_spo2": state.get("monitor_spo2", 98),
        "monitor_alarm": state.get("monitor_alarm", None),
        "monitor_fps": state.get("monitor_fps", 0),
        "monitor_running": state.get("monitor_running", False),
        "xray_displays": [d["id"] for d in XRAY_DISPLAYS],
    }
    for display in XRAY_DISPLAYS:
        display_id = display["id"]
        snapshot[f"{display_id}_images"] = list(state.get(f"{display_id}_images", []))
        snapshot[f"{display_id}_current_index"] = state.get(f"{display_id}_current_index", 0)
        snapshot[f"{display_id}_auto_play"] = state.get(f"{display_id}_auto_play", True)
        snapshot[f"{display_id}_interval"] = state.get(f"{display_id}_interval", 8)
        snapshot[f"{display_id}_running"] = state.get(f"{display_id}_running", False)
        snapshot[f"{display_id}_status"] = state.get(f"{display_id}_status", "no_images")
    return snapshot


def _background_status_emitter(state):
    """
    Background thread that pushes state updates to all connected browsers.

    Runs in a loop, reading the shared state once per second and emitting
    a "status_update" SocketIO event. This keeps the dashboard live without
    the browser needing to poll.

    Args:
        state: The shared Manager dict.
    """
    logger.info("Background status emitter started (1-second interval)")
    while True:
        try:
            time.sleep(1)
            snapshot = _get_state_snapshot(state)
            socketio.emit("status_update", snapshot)
        except Exception as e:
            logger.warning("Status emitter error: %s", e)
            time.sleep(1)


def run_server(state, shutdown_event, debug=False):
    """
    Start the Flask web server with SocketIO.

    This function is called as the target of a multiprocessing.Process
    from main.py. It creates the app, starts the background emitter
    thread, and runs the server.

    Args:
        state: The shared multiprocessing Manager dict.
        shutdown_event: A multiprocessing.Event for shutdown (not used
                       directly here since Flask has its own shutdown).
        debug: If True, enable Flask debug mode (auto-reload, etc.).
    """
    app, sio = create_app(state)

    # Start the background thread that pushes status updates
    emitter = threading.Thread(
        target=_background_status_emitter,
        args=(state,),
        daemon=True,  # Dies when the process exits
    )
    emitter.start()

    logger.info("Web portal starting on http://%s:%d", WEB_HOST, WEB_PORT)

    # Run the Flask-SocketIO server
    # allow_unsafe_werkzeug=True is needed for running in a subprocess
    sio.run(
        app,
        host=WEB_HOST,
        port=WEB_PORT,
        debug=debug,
        use_reloader=False,  # Don't use reloader in subprocess mode
        allow_unsafe_werkzeug=True,
    )
