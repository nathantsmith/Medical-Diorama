"""
ransomware_gpio.py - Physical GPIO watcher for ransomware mode.
"""

import logging

import config
from shared.ransomware import set_gpio_asserted

logger = logging.getLogger(__name__)


def start_watcher(state, shutdown_event, mock_hardware=False):
    """
    Watch the configured GPIO line and update ransomware state on transitions.

    In mock mode or when gpiod is unavailable, the physical trigger is disabled
    and the dashboard remains the only control path.
    """
    set_gpio_asserted(state, False)

    if mock_hardware:
        logger.info("Ransomware GPIO watcher skipped in mock mode")
        return None

    try:
        import gpiod
    except ImportError:
        logger.warning("gpiod unavailable; ransomware GPIO trigger disabled")
        return None

    request = None
    try:
        request = _request_line(gpiod, config.RANSOMWARE_GPIO_PIN)
        initial_value = bool(request.get_value(config.RANSOMWARE_GPIO_PIN))
        set_gpio_asserted(state, initial_value)
        logger.info(
            "Ransomware GPIO watcher started on BCM %d (initial=%s)",
            config.RANSOMWARE_GPIO_PIN,
            initial_value,
        )

        while not shutdown_event.is_set():
            if request.wait_edge_events(timeout=0.2):
                for event in request.read_edge_events():
                    asserted = (
                        event.event_type == gpiod.EdgeEvent.Type.RISING_EDGE
                    )
                    set_gpio_asserted(state, asserted)
                    logger.info(
                        "Ransomware GPIO transition on BCM %d: %s",
                        config.RANSOMWARE_GPIO_PIN,
                        "HIGH" if asserted else "LOW",
                    )
    except Exception as exc:
        logger.warning("Ransomware GPIO watcher stopped: %s", exc)
    finally:
        if request is not None:
            try:
                request.release()
            except Exception:
                pass

    return None


def _request_line(gpiod, pin):
    """Request the configured GPIO line with edge detection."""
    settings = gpiod.LineSettings(
        direction=gpiod.line.Direction.INPUT,
        edge_detection=gpiod.line.Edge.BOTH,
        bias=gpiod.line.Bias.PULL_DOWN,
    )

    last_error = None
    for path in ["/dev/gpiochip4", "/dev/gpiochip0"]:
        try:
            return gpiod.request_lines(
                path,
                consumer="medical-diorama-ransomware",
                config={pin: settings},
            )
        except Exception as exc:
            last_error = exc
            continue

    raise RuntimeError(f"unable to request BCM {pin}: {last_error}")
