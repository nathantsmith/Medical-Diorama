"""
shared/state.py - Shared state management for all three processes.

The shared state is a multiprocessing Manager dict that acts as the single
source of truth. The web portal writes to it, and the display processes
read from it each frame. The Manager proxy handles process-safety automatically.

IMPORTANT: Because this is a Manager().dict(), nested mutable objects (like lists)
must be RE-ASSIGNED to trigger synchronization across processes. For example:
    WRONG:  state["xray_images"].append("new.jpg")   # Won't sync!
    RIGHT:  imgs = list(state["xray_images"])         # Copy the list
            imgs.append("new.jpg")                     # Modify the copy
            state["xray_images"] = imgs                # Re-assign to sync
"""

import os
import config

# =============================================================================
# Default State Values
# =============================================================================
# These are the initial values when the application starts up.

DEFAULT_STATE = {
    # --- Patient Monitor ---
    "monitor_hr": 72,              # Heart rate in BPM (valid range: 30-250)
    "monitor_spo2": 98,            # Blood oxygen percentage (valid range: 70-100)
    "monitor_alarm": None,         # Active alarm: None, "hr_high", "hr_low", "spo2_low"
    "monitor_alarm_active": False, # Whether the alarm visual flash is currently on

    # --- X-Ray Viewer ---
    "xray_images": [],             # List of image filenames in data/xrays/
    "xray_current_index": 0,       # Index of the currently displayed image
    "xray_auto_play": True,        # Whether auto-slideshow is enabled
    "xray_interval": 8,            # Seconds between auto-advance slides

    # --- Status Info (written by display processes, read by web portal) ---
    "monitor_fps": 0,              # Current FPS of the patient monitor loop
    "monitor_running": False,      # Whether the monitor process is active
    "xray_running": False,         # Whether the xray viewer process is active
    "xray_status": "no_images",    # "running", "stopped", "no_images"
}


def create_state(manager):
    """
    Create and return a Manager dict initialized with default values.

    Args:
        manager: A multiprocessing.Manager() instance.

    Returns:
        A SyncManager.dict proxy with all default state values.
    """
    state = manager.dict()
    for key, value in DEFAULT_STATE.items():
        state[key] = value
    return state


def scan_xray_images(state):
    """
    Scan the X-ray images directory and update the shared state.

    Reads all image files from the XRAY_DIR, filters by allowed extensions,
    sorts them alphabetically, and writes the list to shared state.
    Also adjusts the current index if it would be out of bounds.

    Args:
        state: The shared Manager dict to update.
    """
    # Make sure the xray directory exists
    xray_dir = config.XRAY_DIR
    os.makedirs(xray_dir, exist_ok=True)

    # Find all image files in the directory
    images = []
    for filename in os.listdir(xray_dir):
        # Check if the file extension is in our allowed list
        _, ext = os.path.splitext(filename)
        if ext.lower() in config.ALLOWED_IMAGE_EXTENSIONS:
            images.append(filename)

    # Sort alphabetically for consistent ordering
    images.sort()

    # Re-assign the full list to trigger Manager proxy sync
    state["xray_images"] = images

    # Make sure the current index is still valid
    if len(images) == 0:
        state["xray_current_index"] = 0
        state["xray_status"] = "no_images"
    else:
        # Clamp index to valid range
        current = state["xray_current_index"]
        if current >= len(images):
            state["xray_current_index"] = 0
        state["xray_status"] = "running"
