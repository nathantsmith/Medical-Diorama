"""
shared/logging_utils.py - Common logging configuration helpers.
"""

import logging
import sys


NOISY_LOGGERS = {
    "PIL": logging.WARNING,
    "PIL.Image": logging.WARNING,
    "PIL.PngImagePlugin": logging.WARNING,
    "werkzeug": logging.WARNING,
    "engineio": logging.WARNING,
    "socketio": logging.WARNING,
}


def configure_logging(level_name="INFO"):
    """
    Configure root logging and suppress noisy third-party debug loggers.
    """
    level = getattr(logging, str(level_name).upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(processName)s] %(name)s %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
        force=True,
    )
    suppress_noisy_loggers()


def suppress_noisy_loggers():
    """Raise log levels for noisy third-party libraries."""
    for logger_name, level in NOISY_LOGGERS.items():
        logging.getLogger(logger_name).setLevel(level)
