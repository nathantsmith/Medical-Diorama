"""
xray/process.py - X-ray viewer display process.

Runs as a separate process (spawned by main.py) to drive one HDMI output.
main.py spawns one copy of this per entry in config.XRAY_DISPLAYS, each
pinned to a specific HDMI port via pygame.display.set_mode(display=N).
"""

import os
import time
import logging

import pygame

from config import (
    XRAY_SLIDESHOW_FPS,
    COLOR_BLACK, COLOR_WHITE, COLOR_DARK_GRAY,
)
from xray.slideshow import Slideshow
from xray.gestures import SwipeDetector

logger = logging.getLogger(__name__)

IMAGE_LIST_CHECK_INTERVAL = 1.0  # seconds between re-scans of the shared state


def run(state, shutdown_event, display_id, hdmi_index, mock_hardware=False):
    """
    Main entry point for one X-ray viewer process.

    Args:
        state: A multiprocessing Manager dict with shared application state.
        shutdown_event: A multiprocessing.Event that signals shutdown.
        display_id: Which set of state keys to read/write (e.g. "xray1").
        hdmi_index: Integer passed to pygame.display.set_mode(display=...).
        mock_hardware: If True, open a small window instead of fullscreen
                       and don't pin to a specific HDMI output.
    """
    # Pin to the desired HDMI output under Xwayland. Wayfire on Pi OS exposes
    # Xwayland as DISPLAY=:0 by default; SDL's x11 driver then honors the
    # `display=` arg to pygame.display.set_mode().
    if not mock_hardware:
        os.environ.setdefault("SDL_VIDEODRIVER", "x11")
        os.environ.setdefault("DISPLAY", ":0")

    # Per-process logging (spawn start method doesn't inherit handlers)
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(processName)s] %(name)s %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )

    logger.info("[%s] X-ray viewer starting (hdmi_index=%d, mock=%s)",
                display_id, hdmi_index, mock_hardware)

    pygame.init()

    if mock_hardware:
        screen = pygame.display.set_mode((480, 320))
        pygame.display.set_caption(f"X-Ray Viewer ({display_id}, mock)")
    else:
        # pygame.display.set_mode accepts `display=N` (SDL2.0.16+) to open
        # the window on a specific output. FULLSCREEN then covers that screen.
        try:
            screen = pygame.display.set_mode(
                (0, 0), pygame.FULLSCREEN, display=hdmi_index
            )
        except (pygame.error, TypeError):
            # Fallback for older SDL: just go fullscreen on whatever SDL picks.
            logger.warning(
                "[%s] pygame.display.set_mode(display=%d) failed; falling back to default output",
                display_id, hdmi_index,
            )
            screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)

    screen_width, screen_height = screen.get_size()
    logger.info("[%s] display is %dx%d", display_id, screen_width, screen_height)

    pygame.mouse.set_visible(False)

    slideshow = Slideshow(state, display_id)
    swipe_detector = SwipeDetector()
    clock = pygame.time.Clock()

    cached_path = None
    cached_surface = None
    last_list_check = time.time()

    state[f"{display_id}_running"] = True

    try:
        while not shutdown_event.is_set():

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    shutdown_event.set()
                    break

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

                gesture = swipe_detector.process_event(event)
                if gesture == "swipe_left":
                    slideshow.next_image()
                elif gesture == "swipe_right":
                    slideshow.prev_image()
                elif gesture == "tap":
                    slideshow.toggle_auto_play()

            if shutdown_event.is_set():
                break

            slideshow.check_auto_advance()

            now = time.time()
            if now - last_list_check >= IMAGE_LIST_CHECK_INTERVAL:
                last_list_check = now
                images = list(state.get(f"{display_id}_images", []))
                state[f"{display_id}_status"] = "running" if images else "no_images"

            current_path = slideshow.get_current_path()
            if current_path and os.path.exists(current_path):
                if current_path != cached_path:
                    try:
                        raw_surface = pygame.image.load(current_path)
                        cached_surface = _scale_to_fit(
                            raw_surface, screen_width, screen_height
                        )
                        cached_path = current_path
                        logger.debug("[%s] loaded image: %s", display_id,
                                     os.path.basename(current_path))
                    except Exception as e:
                        logger.warning("[%s] failed to load %s: %s",
                                       display_id, current_path, e)
                        cached_surface = None
                        cached_path = None

                screen.fill(COLOR_BLACK)
                if cached_surface:
                    img_rect = cached_surface.get_rect(
                        center=(screen_width // 2, screen_height // 2)
                    )
                    screen.blit(cached_surface, img_rect)
            else:
                screen.fill(COLOR_BLACK)
                _draw_no_images_message(screen, screen_width, screen_height, display_id)

            pygame.display.flip()
            clock.tick(XRAY_SLIDESHOW_FPS)

    except KeyboardInterrupt:
        logger.info("[%s] keyboard interrupt", display_id)
    except Exception as e:
        logger.error("[%s] viewer error: %s", display_id, e, exc_info=True)
    finally:
        state[f"{display_id}_running"] = False
        pygame.quit()
        logger.info("[%s] viewer stopped", display_id)


def _scale_to_fit(surface, max_width, max_height):
    """Scale a pygame surface to fit within max_width x max_height, keeping aspect ratio."""
    img_width, img_height = surface.get_size()
    scale = min(max_width / img_width, max_height / img_height)
    new_width = int(img_width * scale)
    new_height = int(img_height * scale)
    return pygame.transform.smoothscale(surface, (new_width, new_height))


def _draw_no_images_message(screen, width, height, display_id):
    """Centered placeholder when the display has no images yet."""
    try:
        font = pygame.font.SysFont("dejavusansmono", 20)
    except Exception:
        font = pygame.font.Font(None, 24)

    lines = [
        f"No X-Ray Images ({display_id})",
        "",
        "Upload images via the",
        "web portal to begin.",
    ]
    y_start = height // 2 - (len(lines) * 28) // 2
    for i, line in enumerate(lines):
        if not line:
            continue
        color = COLOR_WHITE if i == 0 else COLOR_DARK_GRAY
        text_surface = font.render(line, True, color)
        text_rect = text_surface.get_rect(center=(width // 2, y_start + i * 28))
        screen.blit(text_surface, text_rect)
