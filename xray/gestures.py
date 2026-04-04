"""
xray/gestures.py - Touch and swipe gesture detection for the X-ray viewer.

Detects swipe gestures from pygame touch/mouse events on the 4" HDMI
touchscreen. The touchscreen may present as either a touch device
(FINGERDOWN/FINGERUP events) or a mouse device (MOUSEBUTTONDOWN/MOUSEBUTTONUP),
depending on the driver — this module handles both.

Gesture types detected:
  - "swipe_left":  Horizontal swipe from right to left → next image
  - "swipe_right": Horizontal swipe from left to right → previous image
  - "tap":         Quick press and release with minimal movement → toggle auto-play

A swipe is recognized when:
  1. The horizontal distance exceeds XRAY_SWIPE_THRESHOLD pixels
  2. The horizontal distance is greater than the vertical distance
     (to distinguish from accidental vertical movement)
"""

import pygame
from config import XRAY_SWIPE_THRESHOLD


class SwipeDetector:
    """
    Detects swipe and tap gestures from pygame touch/mouse events.

    Usage:
        detector = SwipeDetector()
        for event in pygame.event.get():
            gesture = detector.process_event(event)
            if gesture == "swipe_left":
                slideshow.next_image()
            elif gesture == "swipe_right":
                slideshow.prev_image()
            elif gesture == "tap":
                slideshow.toggle_auto_play()
    """

    def __init__(self):
        """Initialize the swipe detector with no active touch."""
        # Starting position of the current touch/click
        self._start_x = None
        self._start_y = None
        # Whether we're currently tracking a touch
        self._tracking = False

    def process_event(self, event):
        """
        Process a single pygame event and return any detected gesture.

        Call this for every event from pygame.event.get(). Most events
        will return None (no gesture detected). A gesture string is
        returned only when a complete touch-and-release is recognized.

        Args:
            event: A pygame event object.

        Returns:
            "swipe_left", "swipe_right", "tap", or None.
        """
        # --- Handle touch START (finger down or mouse button down) ---
        if event.type == pygame.FINGERDOWN:
            # Touch events use normalized coordinates (0.0 to 1.0)
            # Convert to pixel coordinates using the display size
            display_info = pygame.display.get_surface()
            if display_info:
                self._start_x = event.x * display_info.get_width()
                self._start_y = event.y * display_info.get_height()
            else:
                self._start_x = event.x
                self._start_y = event.y
            self._tracking = True
            return None

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # Mouse click (left button) — some touchscreens use this
            self._start_x = event.pos[0]
            self._start_y = event.pos[1]
            self._tracking = True
            return None

        # --- Handle touch END (finger up or mouse button up) ---
        elif event.type == pygame.FINGERUP and self._tracking:
            # Get the end position
            display_info = pygame.display.get_surface()
            if display_info:
                end_x = event.x * display_info.get_width()
                end_y = event.y * display_info.get_height()
            else:
                end_x = event.x
                end_y = event.y
            return self._evaluate_gesture(end_x, end_y)

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self._tracking:
            end_x = event.pos[0]
            end_y = event.pos[1]
            return self._evaluate_gesture(end_x, end_y)

        return None

    def _evaluate_gesture(self, end_x, end_y):
        """
        Determine what gesture was made based on start and end positions.

        Args:
            end_x: X pixel coordinate where the touch ended.
            end_y: Y pixel coordinate where the touch ended.

        Returns:
            "swipe_left", "swipe_right", "tap", or None.
        """
        # Reset tracking state
        self._tracking = False

        # Safety check: make sure we have a valid start position
        if self._start_x is None or self._start_y is None:
            return None

        # Calculate how far the finger moved
        dx = end_x - self._start_x      # Positive = moved right
        dy = end_y - self._start_y       # Positive = moved down
        abs_dx = abs(dx)
        abs_dy = abs(dy)

        # Check if horizontal movement exceeds the swipe threshold
        # and is more horizontal than vertical (avoids diagonal confusion)
        if abs_dx >= XRAY_SWIPE_THRESHOLD and abs_dx > abs_dy:
            if dx < 0:
                # Swiped LEFT → go to next image
                return "swipe_left"
            else:
                # Swiped RIGHT → go to previous image
                return "swipe_right"

        # If movement was small, it's a tap
        if abs_dx < XRAY_SWIPE_THRESHOLD and abs_dy < XRAY_SWIPE_THRESHOLD:
            return "tap"

        # Vertical swipe or ambiguous gesture — ignore
        return None
