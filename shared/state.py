"""
shared/state.py - Shared state management for all processes.

The shared state is a multiprocessing Manager dict that acts as the single
source of truth. The web portal writes to it, and the display processes
read from it each frame. The Manager proxy handles process-safety automatically.

IMPORTANT: Because this is a Manager().dict(), nested mutable objects (like lists)
must be RE-ASSIGNED to trigger synchronization across processes. For example:
    WRONG:  state["xray1_images"].append("new.jpg")   # Won't sync!
    RIGHT:  imgs = list(state["xray1_images"])         # Copy the list
            imgs.append("new.jpg")                      # Modify the copy
            state["xray1_images"] = imgs                # Re-assign to sync
"""

import os
import config
from shared.ransomware import base_defaults as ransomware_defaults


def _xray_defaults(display_id):
    """Return the default per-display xray state keys."""
    return {
        f"{display_id}_images": [],
        f"{display_id}_current_index": 0,
        f"{display_id}_auto_play": True,
        f"{display_id}_interval": config.XRAY_DEFAULT_INTERVAL,
        f"{display_id}_running": False,
        f"{display_id}_status": "no_images",
    }


def _base_defaults():
    """Default state shared by the monitor + general bookkeeping."""
    defaults = {
        # --- Patient Monitor ---
        "monitor_hr": 72,
        "monitor_spo2": 98,
        "monitor_alarm": None,
        "monitor_alarm_active": False,
        "monitor_fps": 0,
        "monitor_running": False,
    }
    defaults.update(ransomware_defaults())
    return defaults


def _default_state_dict():
    """Materialize the full default state as a plain dictionary."""
    defaults = {}
    defaults.update(_base_defaults())
    for display in config.XRAY_DISPLAYS:
        defaults.update(_xray_defaults(display["id"]))
    return defaults


DEFAULT_STATE = _default_state_dict()


def create_state(manager):
    """
    Create and return a Manager dict initialized with default values.

    Args:
        manager: A multiprocessing.Manager() instance.

    Returns:
        A SyncManager.dict proxy with all default state values (monitor +
        one set of xray_* keys per entry in config.XRAY_DISPLAYS).
    """
    state = manager.dict()
    for key, value in DEFAULT_STATE.items():
        state[key] = value
    return state


def scan_xray_images(state, display_id):
    """
    Scan one xray display's image directory and update its shared-state keys.

    Reads all image files from the display's directory, filters by allowed
    extensions, sorts alphabetically, and writes the list to state under
    "<display_id>_images". Also adjusts the current index if it would be out
    of bounds.

    Args:
        state: The shared Manager dict.
        display_id: One of the ids in config.XRAY_DISPLAYS (e.g. "xray1").
    """
    xray_dir = config.xray_dir_for(display_id)
    os.makedirs(xray_dir, exist_ok=True)

    images = []
    for filename in os.listdir(xray_dir):
        _, ext = os.path.splitext(filename)
        if ext.lower() in config.ALLOWED_IMAGE_EXTENSIONS:
            images.append(filename)
    images.sort()

    # Re-assign the full list to trigger Manager proxy sync
    state[f"{display_id}_images"] = images

    if not images:
        state[f"{display_id}_current_index"] = 0
        state[f"{display_id}_status"] = "no_images"
    else:
        current = state.get(f"{display_id}_current_index", 0)
        if current >= len(images):
            state[f"{display_id}_current_index"] = 0
        state[f"{display_id}_status"] = "running"


def scan_all_xray_images(state):
    """Scan image directories for every configured display."""
    for display in config.XRAY_DISPLAYS:
        scan_xray_images(state, display["id"])
