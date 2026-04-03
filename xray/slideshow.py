"""
xray/slideshow.py - X-ray slideshow logic and image management.

Manages the image rotation for the X-ray viewer display:
  - Auto-advance: cycles through images on a timer
  - Manual navigation: next/previous via swipe gestures
  - State sync: reads and writes the shared state dict

The image list and current index live in shared state so the web portal
can also control what's being displayed and know what's currently shown.
"""

import os
import time
import logging

from config import XRAY_DIR

logger = logging.getLogger(__name__)


class Slideshow:
    """
    Manages the X-ray image slideshow state and auto-advance timing.

    Works with the shared state dict to coordinate between the display
    process (which shows images) and the web portal (which uploads/manages them).
    """

    def __init__(self, state):
        """
        Initialize the slideshow manager.

        Args:
            state: The shared multiprocessing Manager dict.
        """
        self._state = state
        # Track when we last auto-advanced (for the timer)
        self._last_advance_time = time.time()

    def next_image(self):
        """
        Advance to the next image in the rotation.

        Wraps around to the first image after the last one.
        Resets the auto-advance timer so the new image stays
        on screen for the full interval.
        """
        images = list(self._state.get("xray_images", []))
        if not images:
            return

        # Increment index, wrapping around to 0
        current = self._state.get("xray_current_index", 0)
        new_index = (current + 1) % len(images)
        self._state["xray_current_index"] = new_index

        # Reset the auto-advance timer
        self._last_advance_time = time.time()
        logger.debug("Advanced to image %d/%d", new_index + 1, len(images))

    def prev_image(self):
        """
        Go back to the previous image in the rotation.

        Wraps around to the last image if currently on the first one.
        Resets the auto-advance timer.
        """
        images = list(self._state.get("xray_images", []))
        if not images:
            return

        current = self._state.get("xray_current_index", 0)
        new_index = (current - 1) % len(images)
        self._state["xray_current_index"] = new_index

        # Reset the auto-advance timer
        self._last_advance_time = time.time()
        logger.debug("Went back to image %d/%d", new_index + 1, len(images))

    def toggle_auto_play(self):
        """Toggle the auto-advance slideshow on or off."""
        current = self._state.get("xray_auto_play", True)
        self._state["xray_auto_play"] = not current
        logger.info("Auto-play %s", "enabled" if not current else "disabled")
        # Reset timer when re-enabling so it doesn't immediately advance
        self._last_advance_time = time.time()

    def get_current_path(self):
        """
        Get the full file path to the currently displayed image.

        Returns:
            Full path string to the current image, or None if no images
            are available.
        """
        images = list(self._state.get("xray_images", []))
        if not images:
            return None

        index = self._state.get("xray_current_index", 0)

        # Clamp index to valid range (in case images were deleted)
        if index >= len(images):
            index = 0
            self._state["xray_current_index"] = 0

        return os.path.join(XRAY_DIR, images[index])

    def check_auto_advance(self):
        """
        Check if it's time to auto-advance to the next image.

        Only advances if auto-play is enabled and enough time has
        passed since the last advance (manual or automatic).

        Returns:
            True if the slideshow advanced, False otherwise.
        """
        # Don't auto-advance if disabled
        if not self._state.get("xray_auto_play", True):
            return False

        # Don't advance if there are no images
        images = list(self._state.get("xray_images", []))
        if len(images) <= 1:
            return False

        # Check if enough time has passed
        interval = self._state.get("xray_interval", 8)
        elapsed = time.time() - self._last_advance_time

        if elapsed >= interval:
            self.next_image()
            return True

        return False
