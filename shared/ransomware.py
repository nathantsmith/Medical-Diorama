"""
shared/ransomware.py - Shared helpers for ransomware mode state and assets.
"""

import os

import config


def ransomware_targets():
    """Return the fixed set of display targets that support ransomware art."""
    return ["monitor"] + [display["id"] for display in config.XRAY_DISPLAYS]


def is_valid_target(target):
    """Return True if the target is one of the configured ransomware targets."""
    return target in ransomware_targets()


def image_state_key(target):
    """Return the shared-state key that stores the target's image filename."""
    return f"ransomware_{target}_image"


def image_version_key(target):
    """Return the shared-state key that stores the target's cache-buster token."""
    return f"ransomware_{target}_version"


def base_defaults():
    """Default shared-state keys for ransomware mode."""
    defaults = {
        "ransomware_web_enabled": False,
        "ransomware_gpio_asserted": False,
        "ransomware_active": False,
    }
    for target in ransomware_targets():
        defaults[image_state_key(target)] = None
        defaults[image_version_key(target)] = 0
    return defaults


def recompute_active(state):
    """Recompute the effective ransomware state from GPIO + web inputs."""
    active = bool(
        state.get("ransomware_gpio_asserted", False)
        or state.get("ransomware_web_enabled", False)
    )
    state["ransomware_active"] = active
    return active


def set_web_enabled(state, enabled):
    """Update the dashboard-controlled ransomware toggle."""
    state["ransomware_web_enabled"] = bool(enabled)
    return recompute_active(state)


def set_gpio_asserted(state, asserted):
    """Update the physical GPIO-controlled ransomware input."""
    state["ransomware_gpio_asserted"] = bool(asserted)
    return recompute_active(state)


def set_image_filename(state, target, filename):
    """Store the active ransomware filename for one display target."""
    state[image_state_key(target)] = filename
    state[image_version_key(target)] = time_token()


def get_image_filename(state, target):
    """Read the current ransomware filename for one display target."""
    return state.get(image_state_key(target))


def get_image_version(state, target):
    """Read the cache-buster token for one display target."""
    return state.get(image_version_key(target), 0)


def get_image_path(state, target):
    """Return the current ransomware asset path for one target, or None."""
    filename = get_image_filename(state, target)
    if not filename:
        return None
    return os.path.join(config.ransomware_dir_for(target), filename)


def time_token():
    """Return a monotonically increasing token suitable for cache busting."""
    import time

    return time.time_ns()
