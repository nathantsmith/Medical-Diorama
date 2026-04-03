"""
xray/process.py - X-ray viewer display process.

This module runs as a separate process (spawned by main.py) and drives
the 4" HDMI touchscreen display. It shows X-ray images in a fullscreen
slideshow with touch/swipe navigation.

The main loop:
  1. Process pygame events (touch gestures, quit)
  2. Check auto-advance timer
  3. Load and display the current image (cached to avoid reloading every frame)
  4. Render to screen
  5. Periodically re-check the image list for changes from the web portal
"""

import os
import sys
import time
import logging

import pygame

from config import (
    HDMI_DISPLAY_ENV, XRAY_SLIDESHOW_FPS,
    COLOR_BLACK, COLOR_WHITE, COLOR_DARK_GRAY,
)
from xray.slideshow import Slideshow
from xray.gestures import SwipeDetector

logger = logging.getLogger(__name__)

# How often (in seconds) to re-check the image list from shared state.
# This picks up uploads/deletions from the web portal.
IMAGE_LIST_CHECK_INTERVAL = 1.0


def run(state, shutdown_event, mock_hardware=False):
    """
    Main entry point for the X-ray viewer process.

    Initializes pygame, creates a fullscreen window on the HDMI touchscreen,
    and runs the slideshow loop until shutdown_event is set.

    Args:
        state: A multiprocessing Manager dict with shared application state.
        shutdown_event: A multiprocessing.Event that signals shutdown.
        mock_hardware: If True, run in a small window instead of fullscreen.
    """
    # Set environment variables to target the correct HDMI output
    # These must be set BEFORE pygame.init()
    for key, value in HDMI_DISPLAY_ENV.items():
        os.environ[key] = value

    # Initialize pygame
    pygame.init()

    # Set up the display window
    if mock_hardware:
        # Development mode: small resizable window
        screen = pygame.display.set_mode((480, 320))
        pygame.display.set_caption("X-Ray Viewer (Mock)")
    else:
        # Production mode: fullscreen on the HDMI touchscreen
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)

    screen_width, screen_height = screen.get_size()
    logger.info(
        "X-ray viewer started: %dx%d %s",
        screen_width, screen_height,
        "(windowed)" if mock_hardware else "(fullscreen)"
    )

    # Hide the mouse cursor (we're using touch, not a pointer)
    pygame.mouse.set_visible(False)

    # Create slideshow manager and swipe detector
    slideshow = Slideshow(state)
    swipe_detector = SwipeDetector()

    # Frame rate clock
    clock = pygame.time.Clock()

    # Cache the currently loaded and scaled image surface to avoid
    # reloading from disk every frame
    cached_path = None
    cached_surface = None

    # Track when we last checked the image list for changes
    last_list_check = time.time()

    # Mark the viewer as running
    state["xray_running"] = True

    try:
        # === Main display loop ===
        while not shutdown_event.is_set():

            # --- Step 1: Process pygame events ---
            for event in pygame.event.get():
                # Handle quit event (window close, etc.)
                if event.type == pygame.QUIT:
                    shutdown_event.set()
                    break

                # Handle keyboard events (for development convenience)
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        shutdown_event.set()
                        break
                    elif event.key == pygame.K_RIGHT:
                        slideshow.next_image()
                    elif event.key == pygame.K_LEFT:
                        slideshow.prev_image()
                    elif event.key == pygame.K_SPACE:
                        slideshow.toggle_auto_play()

                # Handle touch/swipe gestures
                gesture = swipe_detector.process_event(event)
                if gesture == "swipe_left":
                    slideshow.next_image()
                elif gesture == "swipe_right":
                    slideshow.prev_image()
                elif gesture == "tap":
                    slideshow.toggle_auto_play()

            # Check if shutdown was triggered during event processing
            if shutdown_event.is_set():
                break

            # --- Step 2: Check auto-advance timer ---
            slideshow.check_auto_advance()

            # --- Step 3: Periodically re-check image list ---
            # The web portal may have added or removed images
            now = time.time()
            if now - last_list_check >= IMAGE_LIST_CHECK_INTERVAL:
                last_list_check = now
                # Update status based on image availability
                images = list(state.get("xray_images", []))
                if images:
                    state["xray_status"] = "running"
                else:
                    state["xray_status"] = "no_images"

            # --- Step 4: Load and display the current image ---
            current_path = slideshow.get_current_path()

            if current_path and os.path.exists(current_path):
                # Only reload from disk if the image changed
                if current_path != cached_path:
                    try:
                        # Load the image from disk
                        raw_surface = pygame.image.load(current_path)

                        # Scale to fit the screen while maintaining aspect ratio
                        cached_surface = _scale_to_fit(
                            raw_surface, screen_width, screen_height
                        )
                        cached_path = current_path
                        logger.debug("Loaded image: %s", os.path.basename(current_path))
                    except Exception as e:
                        logger.warning("Failed to load image %s: %s", current_path, e)
                        cached_surface = None
                        cached_path = None

                # Draw the image centered on a black background
                screen.fill(COLOR_BLACK)
                if cached_surface:
                    # Center the image on screen
                    img_rect = cached_surface.get_rect(
                        center=(screen_width // 2, screen_height // 2)
                    )
                    screen.blit(cached_surface, img_rect)
            else:
                # No image to display — show a placeholder message
                screen.fill(COLOR_BLACK)
                _draw_no_images_message(screen, screen_width, screen_height)

            # --- Step 5: Update the display ---
            pygame.display.flip()

            # --- Step 6: Cap the frame rate ---
            # 15 FPS is plenty for a slideshow; saves CPU for other processes
            clock.tick(XRAY_SLIDESHOW_FPS)

    except KeyboardInterrupt:
        logger.info("X-ray viewer received keyboard interrupt")
    except Exception as e:
        logger.error("X-ray viewer error: %s", e, exc_info=True)
    finally:
        state["xray_running"] = False
        pygame.quit()
        logger.info("X-ray viewer process stopped")


def _scale_to_fit(surface, max_width, max_height):
    """
    Scale a pygame surface to fit within the given dimensions,
    maintaining the original aspect ratio.

    Args:
        surface: The pygame.Surface to scale.
        max_width: Maximum width in pixels.
        max_height: Maximum height in pixels.

    Returns:
        A new pygame.Surface scaled to fit.
    """
    img_width, img_height = surface.get_size()

    # Calculate scale factors for both dimensions
    scale_x = max_width / img_width
    scale_y = max_height / img_height

    # Use the smaller scale factor to ensure the image fits entirely
    scale = min(scale_x, scale_y)

    # Calculate new dimensions
    new_width = int(img_width * scale)
    new_height = int(img_height * scale)

    # Scale the image smoothly
    return pygame.transform.smoothscale(surface, (new_width, new_height))


def _draw_no_images_message(screen, width, height):
    """
    Draw a placeholder message when no X-ray images are available.

    Shows a centered message telling the user to upload images
    via the web portal.

    Args:
        screen: The pygame display surface.
        width: Screen width in pixels.
        height: Screen height in pixels.
    """
    try:
        font = pygame.font.SysFont("dejavusansmono", 20)
    except Exception:
        font = pygame.font.Font(None, 24)

    # Render the message lines
    lines = [
        "No X-Ray Images",
        "",
        "Upload images via the",
        "web portal to begin.",
    ]

    y_start = height // 2 - (len(lines) * 28) // 2
    for i, line in enumerate(lines):
        if line:
            color = COLOR_WHITE if i == 0 else COLOR_DARK_GRAY
            text_surface = font.render(line, True, color)
            text_rect = text_surface.get_rect(center=(width // 2, y_start + i * 28))
            screen.blit(text_surface, text_rect)
