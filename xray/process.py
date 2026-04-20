import logging
import glob
import os
import re
import subprocess
import time

import pygame

from config import (
    XRAY_SLIDESHOW_FPS,
    COLOR_BLACK, COLOR_WHITE, COLOR_DARK_GRAY,
)
from shared.logging_utils import configure_logging
from shared.ransomware import get_image_path
from xray.slideshow import Slideshow
from xray.gestures import SwipeDetector

logger = logging.getLogger(__name__)

IMAGE_LIST_CHECK_INTERVAL = 1.0  # seconds between re-scans of the shared state
OUTPUT_PROBE_INTERVAL = 2.0  # seconds between output binding checks


def _find_wayland_display_name(runtime_dir=None):
    """Return the first available Wayland socket name under XDG_RUNTIME_DIR."""
    runtime_dir = runtime_dir or os.environ.get("XDG_RUNTIME_DIR")
    if not runtime_dir or not os.path.isdir(runtime_dir):
        return None

    try:
        entries = sorted(os.listdir(runtime_dir))
    except OSError:
        return None

    for entry in entries:
        if entry.startswith("wayland-"):
            return entry
    return None


def _candidate_runtime_dirs():
    """Return plausible runtime dirs for discovering a Wayland session."""
    runtime_dirs = []

    env_runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if env_runtime_dir:
        runtime_dirs.append(env_runtime_dir)

    default_runtime_dir = f"/run/user/{os.getuid()}"
    if default_runtime_dir not in runtime_dirs:
        runtime_dirs.append(default_runtime_dir)

    return runtime_dirs


def _resolve_display_backend():
    """
    Choose the best available SDL video backend for the current session.

    Returns:
        tuple[str, dict]: Backend name ("x11", "wayland", or "direct") and
        environment variables that should be present before (re)initializing
        pygame's display module.
    """
    display_name = os.environ.get("DISPLAY")
    if display_name:
        return "x11", {
            "DISPLAY": display_name,
            "SDL_VIDEODRIVER": "x11",
        }

    requested_wayland = os.environ.get("WAYLAND_DISPLAY")
    for runtime_dir in _candidate_runtime_dirs():
        wayland_name = requested_wayland or _find_wayland_display_name(runtime_dir)
        if wayland_name:
            return "wayland", {
                "XDG_RUNTIME_DIR": runtime_dir,
                "WAYLAND_DISPLAY": wayland_name,
                "SDL_VIDEODRIVER": "wayland",
            }

    return "direct", {}


def _iter_drm_connector_statuses(base_path="/sys/class/drm"):
    """Yield connector names and status strings from sysfs DRM entries."""
    pattern = os.path.join(base_path, "card*-*/status")
    for status_path in sorted(glob.glob(pattern)):
        connector_dir = os.path.basename(os.path.dirname(status_path))
        connector_name = connector_dir.split("-", 1)[1]
        if connector_name.startswith("Writeback-"):
            continue
        try:
            with open(status_path, "r", encoding="utf-8") as handle:
                status = handle.read().strip().lower()
        except OSError:
            continue
        yield connector_name, status


def _read_drm_outputs(base_path="/sys/class/drm"):
    """Read connector state directly from sysfs DRM entries."""
    outputs = {}
    for connector_name, status in _iter_drm_connector_statuses(base_path):
        outputs[connector_name] = {
            "name": connector_name,
            "connected": status == "connected",
            "width": None,
            "height": None,
            "x": None,
            "y": None,
            "source": "drm-sysfs",
        }
    return outputs


def _connected_output_index(outputs, preferred_name):
    """Return the SDL display index implied by connected DRM connector order."""
    connected_names = [
        name for name in sorted(outputs)
        if outputs[name].get("connected")
    ]
    try:
        return connected_names.index(preferred_name)
    except ValueError:
        return None


def _parse_xrandr_outputs(output_text):
    """Parse `xrandr --query` output into a mapping of output metadata."""
    outputs = {}
    line_pattern = re.compile(
        r"^(?P<name>\S+)\s+"
        r"(?P<state>connected|disconnected)"
        r"(?:\s+primary)?"
        r"(?:\s+(?P<geometry>\d+x\d+\+\d+\+\d+))?"
    )

    for raw_line in output_text.splitlines():
        line = raw_line.strip()
        match = line_pattern.match(line)
        if not match:
            continue

        geometry = match.group("geometry")
        width = height = x = y = None
        if geometry:
            width_s, height_s, x_s, y_s = re.match(
                r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", geometry
            ).groups()
            width = int(width_s)
            height = int(height_s)
            x = int(x_s)
            y = int(y_s)

        outputs[match.group("name")] = {
            "name": match.group("name"),
            "connected": match.group("state") == "connected",
            "width": width,
            "height": height,
            "x": x,
            "y": y,
            "source": "xrandr",
        }

    return outputs


def _parse_wlr_randr_outputs(output_text):
    """Parse `wlr-randr` output into a mapping of output metadata."""
    outputs = {}
    current = None

    for raw_line in output_text.splitlines():
        if raw_line and not raw_line.startswith(" "):
            name = raw_line.split()[0]
            current = {
                "name": name,
                "connected": True,
                "width": None,
                "height": None,
                "x": None,
                "y": None,
                "source": "wlr-randr",
            }
            outputs[name] = current
            continue

        if current is None:
            continue

        line = raw_line.strip()
        if line.startswith("Enabled:"):
            current["connected"] = line.partition(":")[2].strip().lower() == "yes"
            continue

        if line.startswith("Position:"):
            position = line.partition(":")[2].strip()
            try:
                x_s, y_s = [part.strip() for part in position.split(",", 1)]
                current["x"] = int(x_s)
                current["y"] = int(y_s)
            except (TypeError, ValueError):
                pass
            continue

        if "(current" in line and "x" in line:
            mode_match = re.search(r"(\d+)x(\d+)", line)
            if mode_match:
                current["width"] = int(mode_match.group(1))
                current["height"] = int(mode_match.group(2))

    return outputs


def _query_outputs(command, parser, extra_env=None):
    """Run an output-discovery command and parse the results."""
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            env=env,
            timeout=2,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return {}

    return parser(result.stdout)


def _discover_outputs():
    """Discover available display outputs from Wayland and X11 tooling."""
    outputs = _read_drm_outputs()
    outputs.update(_query_outputs(["wlr-randr"], _parse_wlr_randr_outputs))

    display_name = os.environ.get("DISPLAY", ":0")
    outputs.update(
        _query_outputs(
            ["xrandr", "--query"],
            _parse_xrandr_outputs,
            extra_env={"DISPLAY": display_name},
        )
    )
    return outputs


def _resolve_output(preferred_names):
    """Return metadata for the first matching configured connector name."""
    outputs = _discover_outputs()

    for name in preferred_names:
        output = outputs.get(name)
        if output:
            output = dict(output)
            output["sdl_display_index"] = _connected_output_index(outputs, name)
            return output

    return None


def _open_bound_window(display_id, output_info):
    """Create a borderless window at the exact coordinates of the target output."""
    width = output_info.get("width")
    height = output_info.get("height")
    x = output_info.get("x")
    y = output_info.get("y")

    if None in (width, height, x, y):
        raise RuntimeError(
            f"{output_info['name']} is connected but missing geometry information"
        )

    os.environ["SDL_VIDEO_WINDOW_POS"] = f"{x},{y}"
    pygame.display.quit()
    pygame.display.init()
    screen = pygame.display.set_mode((width, height), pygame.NOFRAME)
    pygame.display.set_caption(f"X-Ray Viewer ({display_id} -> {output_info['name']})")
    pygame.mouse.set_visible(False)
    return screen


def _open_direct_window(display_id, output_info):
    """Open a fullscreen SDL window on the resolved direct-rendering display."""
    display_index = output_info.get("sdl_display_index")
    if display_index is None:
        raise RuntimeError(f"{output_info['name']} is not currently mapped to an SDL display")

    pygame.display.quit()
    pygame.display.init()

    try:
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN, display=display_index)
    except TypeError:
        if display_index != 0:
            raise RuntimeError("SDL display selection is unavailable on this pygame build")
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)

    pygame.display.set_caption(f"X-Ray Viewer ({display_id} -> {output_info['name']})")
    pygame.mouse.set_visible(False)
    return screen


def _set_display_backend(current_backend, desired_backend, env_updates):
    """Apply backend env vars and report whether the backend changed."""
    for key, value in env_updates.items():
        os.environ[key] = value

    if desired_backend == "direct":
        os.environ.pop("SDL_VIDEODRIVER", None)

    return current_backend != desired_backend


def run(
    state,
    shutdown_event,
    display_id,
    hdmi_index,
    mock_hardware=False,
    connector_names=None,
    log_level="INFO",
):
    """
    Main entry point for one X-ray viewer process.

    Args:
        state: A multiprocessing Manager dict with shared application state.
        shutdown_event: A multiprocessing.Event that signals shutdown.
        display_id: Which set of state keys to read/write (e.g. "xray1").
        hdmi_index: Legacy HDMI index retained for logging and compatibility.
        mock_hardware: If True, open a small window instead of fullscreen
                       and don't pin to a specific HDMI output.
        connector_names: Ordered list of output names that map to the physical
                         connector for this display.
        log_level: Root logging level name for this child process.
    """
    connector_names = list(connector_names or [])
    display_backend = "direct"
    if not mock_hardware:
        display_backend, env_updates = _resolve_display_backend()
        _set_display_backend(None, display_backend, env_updates)

    # Per-process logging (spawn start method doesn't inherit handlers)
    configure_logging(log_level)

    logger.info(
        "[%s] X-ray viewer starting (hdmi_index=%d, connectors=%s, mock=%s, display=%s, wayland=%s, sdl=%s)",
        display_id,
        hdmi_index,
        connector_names or ["<index-only>"],
        mock_hardware,
        os.environ.get("DISPLAY", "<unset>"),
        os.environ.get("WAYLAND_DISPLAY", "<unset>"),
        os.environ.get("SDL_VIDEODRIVER", "<default>"),
    )

    pygame.init()
    logger.info(
        "[%s] SDL video driver=%s, displays=%d",
        display_id,
        pygame.display.get_driver(),
        pygame.display.get_num_displays(),
    )

    screen = None
    screen_width = 0
    screen_height = 0
    bound_output_name = None
    bound_output_x = None
    bound_output_y = None
    binding_mode = None
    last_output_probe = 0.0

    if mock_hardware:
        screen = pygame.display.set_mode((480, 320))
        pygame.display.set_caption(f"X-Ray Viewer ({display_id}, mock)")
        screen_width, screen_height = screen.get_size()
        logger.info("[%s] display is %dx%d", display_id, screen_width, screen_height)

    slideshow = Slideshow(state, display_id)
    swipe_detector = SwipeDetector()
    clock = pygame.time.Clock()

    cached_path = None
    cached_surface = None
    last_list_check = time.time()

    state[f"{display_id}_running"] = True

    try:
        while not shutdown_event.is_set():
            if not mock_hardware:
                desired_backend, env_updates = _resolve_display_backend()
                backend_changed = _set_display_backend(
                    display_backend,
                    desired_backend,
                    env_updates,
                )
                if backend_changed:
                    logger.info(
                        "[%s] switching SDL backend from %s to %s",
                        display_id,
                        display_backend,
                        desired_backend,
                    )
                    display_backend = desired_backend
                    pygame.display.quit()
                    pygame.display.init()
                    screen = None
                    screen_width = 0
                    screen_height = 0
                    binding_mode = None
                    bound_output_name = None
                    bound_output_x = None
                    bound_output_y = None

                now = time.time()
                if screen is None or now - last_output_probe >= OUTPUT_PROBE_INTERVAL:
                    last_output_probe = now
                    output_info = _resolve_output(connector_names)
                    if display_backend == "x11":
                        connector_ready = (
                            output_info
                            and output_info.get("connected")
                            and None not in (
                                output_info.get("width"),
                                output_info.get("height"),
                                output_info.get("x"),
                                output_info.get("y"),
                            )
                        )
                    else:
                        connector_ready = (
                            output_info
                            and output_info.get("connected")
                            and output_info.get("sdl_display_index") is not None
                        )

                    if not connector_ready:
                        if screen is not None:
                            logger.info(
                                "[%s] output %s became unavailable; releasing window",
                                display_id,
                                bound_output_name,
                            )
                            pygame.display.quit()
                            screen = None
                            screen_width = 0
                            screen_height = 0
                            binding_mode = None
                            bound_output_name = None
                            bound_output_x = None
                            bound_output_y = None

                        state[f"{display_id}_status"] = "disconnected"
                        state[f"{display_id}_running"] = True
                        time.sleep(0.2)
                        continue

                    needs_rebind = screen is None
                    if connector_ready and binding_mode == "connector" and screen is not None:
                        needs_rebind = (
                            bound_output_name != output_info["name"]
                            or (
                                display_backend == "x11" and (
                                    screen_width != output_info["width"]
                                    or screen_height != output_info["height"]
                                    or bound_output_x != output_info["x"]
                                    or bound_output_y != output_info["y"]
                                )
                            )
                        )

                    if needs_rebind:
                        try:
                            if display_backend == "x11":
                                screen = _open_bound_window(display_id, output_info)
                            else:
                                screen = _open_direct_window(display_id, output_info)
                            binding_mode = "connector"
                            bound_output_name = output_info["name"]
                            bound_output_x = output_info.get("x")
                            bound_output_y = output_info.get("y")
                        except (pygame.error, RuntimeError) as exc:
                            logger.warning(
                                "[%s] connector binding for %s failed (%s); marking display disconnected",
                                display_id,
                                output_info["name"],
                                exc,
                            )
                            pygame.display.quit()
                            screen = None
                            screen_width = 0
                            screen_height = 0
                            binding_mode = None
                            bound_output_name = None
                            bound_output_x = None
                            bound_output_y = None
                            state[f"{display_id}_status"] = "disconnected"
                            state[f"{display_id}_running"] = True
                            time.sleep(0.2)
                            continue

                        screen_width, screen_height = screen.get_size()
                        if display_backend == "x11":
                            logger.info(
                                "[%s] bound to %s at %dx%d+%d+%d via %s",
                                display_id,
                                bound_output_name,
                                screen_width,
                                screen_height,
                                output_info["x"],
                                output_info["y"],
                                output_info["source"],
                            )
                        else:
                            logger.info(
                                "[%s] bound to %s on SDL display %d at %dx%d via %s",
                                display_id,
                                bound_output_name,
                                output_info["sdl_display_index"],
                                screen_width,
                                screen_height,
                                output_info["source"],
                            )

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

            ransomware_active = state.get("ransomware_active", False)

            if not ransomware_active:
                slideshow.check_auto_advance()

            now = time.time()
            if now - last_list_check >= IMAGE_LIST_CHECK_INTERVAL:
                last_list_check = now
                images = list(state.get(f"{display_id}_images", []))
                if ransomware_active:
                    state[f"{display_id}_status"] = "ransomware"
                else:
                    state[f"{display_id}_status"] = "running" if images else "no_images"

            current_path = (
                get_image_path(state, display_id)
                if ransomware_active
                else slideshow.get_current_path()
            )
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
                if ransomware_active:
                    _draw_ransomware_message(screen, screen_width, screen_height, display_id)
                else:
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


def _draw_ransomware_message(screen, width, height, display_id):
    """Centered fallback when ransomware mode is active without an uploaded image."""
    try:
        font = pygame.font.SysFont("dejavusansmono", 24)
        small_font = pygame.font.SysFont("dejavusansmono", 18)
    except Exception:
        font = pygame.font.Font(None, 28)
        small_font = pygame.font.Font(None, 22)

    lines = [
        "RANSOMWARE ACTIVE",
        f"Display: {display_id}",
        "Upload an image in the web portal",
    ]
    y_start = height // 2 - 44
    for index, line in enumerate(lines):
        use_font = font if index == 0 else small_font
        color = COLOR_WHITE if index == 0 else COLOR_DARK_GRAY
        text_surface = use_font.render(line, True, color)
        text_rect = text_surface.get_rect(center=(width // 2, y_start + index * 32))
        screen.blit(text_surface, text_rect)
