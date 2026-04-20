"""
shared/settings_store.py - Persist user-controlled settings across restarts.
"""

import json
import os
import tempfile

import config
from shared.ransomware import get_image_filename, ransomware_targets


def _persistent_keys():
    """Return the shared-state keys that should survive process restarts."""
    keys = [
        "monitor_hr",
        "monitor_spo2",
        "monitor_alarm",
        "ransomware_web_enabled",
    ]
    for display in config.XRAY_DISPLAYS:
        display_id = display["id"]
        keys.extend(
            [
                f"{display_id}_current_index",
                f"{display_id}_auto_play",
                f"{display_id}_interval",
            ]
        )
    for target in ransomware_targets():
        keys.append(f"ransomware_{target}_image")
    return keys


def load_settings(state):
    """Load persisted settings from disk into the shared state."""
    if not os.path.exists(config.SETTINGS_CACHE_PATH):
        return False

    with open(config.SETTINGS_CACHE_PATH, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    for key in _persistent_keys():
        if key in payload:
            state[key] = payload[key]

    state["ransomware_active"] = bool(
        state.get("ransomware_gpio_asserted", False)
        or state.get("ransomware_web_enabled", False)
    )
    return True


def save_settings(state):
    """Persist the current user-controlled settings to disk atomically."""
    payload = {}
    for key in _persistent_keys():
        payload[key] = state.get(key)

    os.makedirs(os.path.dirname(config.SETTINGS_CACHE_PATH), exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix="settings-",
        suffix=".json",
        dir=os.path.dirname(config.SETTINGS_CACHE_PATH),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_path, config.SETTINGS_CACHE_PATH)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def reconcile_persisted_assets(state):
    """Clear persisted ransomware image names if the underlying files are gone."""
    changed = False
    for target in ransomware_targets():
        filename = get_image_filename(state, target)
        if not filename:
            continue
        image_path = os.path.join(config.ransomware_dir_for(target), filename)
        if not os.path.exists(image_path):
            state[f"ransomware_{target}_image"] = None
            changed = True
    return changed
