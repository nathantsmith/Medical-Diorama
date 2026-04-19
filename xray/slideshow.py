"""
xray/slideshow.py - X-ray slideshow logic and image management.

Manages the image rotation for one X-ray viewer display. Each display has
its own Slideshow instance, bound to a display_id whose state keys take the
form "<display_id>_images", "<display_id>_current_index", etc.
"""

import os
import time
import logging

import config

logger = logging.getLogger(__name__)


class Slideshow:
    """
    Manages the X-ray image slideshow state and auto-advance timing
    for one display. Operates on the shared state dict under the
    "<display_id>_*" key prefix.
    """

    def __init__(self, state, display_id):
        """
        Args:
            state: The shared multiprocessing Manager dict.
            display_id: Display identifier matching config.XRAY_DISPLAYS.
        """
        self._state = state
        self._id = display_id
        self._dir = config.xray_dir_for(display_id)
        self._last_advance_time = time.time()

    # --- Key helpers --------------------------------------------------------

    def _k(self, suffix):
        return f"{self._id}_{suffix}"

    # --- Navigation ---------------------------------------------------------

    def next_image(self):
        """Advance to the next image, wrapping around."""
        images = list(self._state.get(self._k("images"), []))
        if not images:
            return
        current = self._state.get(self._k("current_index"), 0)
        new_index = (current + 1) % len(images)
        self._state[self._k("current_index")] = new_index
        self._last_advance_time = time.time()
        logger.debug("[%s] advanced to image %d/%d", self._id, new_index + 1, len(images))

    def prev_image(self):
        """Go back one image, wrapping around."""
        images = list(self._state.get(self._k("images"), []))
        if not images:
            return
        current = self._state.get(self._k("current_index"), 0)
        new_index = (current - 1) % len(images)
        self._state[self._k("current_index")] = new_index
        self._last_advance_time = time.time()
        logger.debug("[%s] back to image %d/%d", self._id, new_index + 1, len(images))

    def toggle_auto_play(self):
        """Toggle the auto-advance slideshow on or off."""
        current = self._state.get(self._k("auto_play"), True)
        self._state[self._k("auto_play")] = not current
        logger.info("[%s] auto-play %s", self._id, "enabled" if not current else "disabled")
        self._last_advance_time = time.time()

    # --- Current image ------------------------------------------------------

    def get_current_path(self):
        """Full path to the current image, or None if no images exist."""
        images = list(self._state.get(self._k("images"), []))
        if not images:
            return None
        index = self._state.get(self._k("current_index"), 0)
        if index >= len(images):
            index = 0
            self._state[self._k("current_index")] = 0
        return os.path.join(self._dir, images[index])

    # --- Auto-advance -------------------------------------------------------

    def check_auto_advance(self):
        """Advance if auto-play is on and the interval has elapsed."""
        if not self._state.get(self._k("auto_play"), True):
            return False
        images = list(self._state.get(self._k("images"), []))
        if len(images) <= 1:
            return False
        interval = self._state.get(self._k("interval"), config.XRAY_DEFAULT_INTERVAL)
        if time.time() - self._last_advance_time >= interval:
            self.next_image()
            return True
        return False
