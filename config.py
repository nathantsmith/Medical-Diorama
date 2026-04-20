"""
config.py - Central configuration for the Medical Diorama project.

All hardware pin assignments, display settings, color constants, alarm
thresholds, and file paths live here so they're easy to find and change.
"""

import os

# =============================================================================
# SPI Display Pin Assignments (Waveshare 2" LCD, ST7789V)
# =============================================================================
# These are the BCM GPIO pin numbers for the Waveshare 2" LCD module.
# Adjust if your wiring differs. Default assumes the standard Waveshare
# connection for Raspberry Pi.

SPI_PORT = 0          # SPI bus number (0 = /dev/spidev0.x)
SPI_CS = 0            # SPI chip-select (0 = CE0)
SPI_DC_PIN = 25       # Data/Command pin (BCM 25 = WiringPi 6)
SPI_RST_PIN = 22      # Reset pin (BCM 22 = WiringPi 3)
SPI_BL_PIN = 24       # Backlight control pin (BCM 24 = WiringPi 5)
SPI_SPEED_HZ = 40_000_000  # SPI clock speed in Hz (40 MHz, Seengreat default is 4MHz)

# =============================================================================
# Patient Monitor Display Settings
# =============================================================================

MONITOR_WIDTH = 320       # Display width in pixels (landscape)
MONITOR_HEIGHT = 240      # Display height in pixels (landscape)
MONITOR_TARGET_FPS = 30   # Target frames per second for animation
MONITOR_ROTATION = 0      # Display rotation (0=portrait, 90/180/270)

# =============================================================================
# X-Ray Viewer Display Settings
# =============================================================================

# The Pi 5 has two HDMI outputs. We run one slideshow process per output, each
# with its own image directory and independent playback state.
#
# `connector_names` lists stable output names to probe at runtime. Different
# display stacks report slightly different names for the same physical port:
#   - Wayland / wlroots: HDMI-A-1, HDMI-A-2
#   - X11 / Xwayland:    HDMI-1, HDMI-2
#
# The ordering here is physical, not "currently connected monitor #N":
#   - xray1 = the port nearest USB-C power
#   - xray2 = the other HDMI port
XRAY_DISPLAYS = [
    {
        "id": "xray1",
        "hdmi_index": 0,
        "label": "X-Ray Display 1",
        "connector_names": ["HDMI-A-1", "HDMI-1", "HDMI1"],
    },
    {
        "id": "xray2",
        "hdmi_index": 1,
        "label": "X-Ray Display 2",
        "connector_names": ["HDMI-A-2", "HDMI-2", "HDMI2"],
    },
]

XRAY_SLIDESHOW_FPS = 15       # FPS for the X-ray viewer (low is fine for stills)
XRAY_DEFAULT_INTERVAL = 8     # Default seconds between auto-advance
XRAY_SWIPE_THRESHOLD = 50     # Minimum pixels for a swipe gesture

# =============================================================================
# Web Portal Settings
# =============================================================================

WEB_HOST = "0.0.0.0"     # Listen on all interfaces (accessible on local network)
WEB_PORT = 5000           # HTTP port for the web portal

# =============================================================================
# Ransomware Trigger Settings
# =============================================================================

RANSOMWARE_GPIO_PIN = 23   # BCM GPIO input for physical ransomware trigger

# =============================================================================
# File Paths
# =============================================================================

# Base directory of the project (where main.py lives)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Base directory for all X-ray images. Each display has its own subdirectory
# (e.g. data/xrays/xray1/, data/xrays/xray2/).
XRAY_BASE_DIR = os.path.join(BASE_DIR, "data", "xrays")

# Base directory for ransomware images. Each physical display has its own
# subdirectory: monitor/, xray1/, xray2/.
RANSOMWARE_BASE_DIR = os.path.join(BASE_DIR, "data", "ransomware")

# Persistent settings cache written by the web/UI control layer so the app can
# restore operator-selected values after restart.
SETTINGS_CACHE_PATH = os.path.join(BASE_DIR, "data", "settings.json")


def xray_dir_for(display_id):
    """Return the image directory for a specific xray display."""
    return os.path.join(XRAY_BASE_DIR, display_id)


def ransomware_dir_for(target):
    """Return the ransomware image directory for a specific display target."""
    return os.path.join(RANSOMWARE_BASE_DIR, target)

# Allowed image file extensions for X-ray uploads
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}

# =============================================================================
# Alarm Thresholds
# =============================================================================
# When vitals cross these thresholds, alarms auto-trigger on the monitor.

ALARM_THRESHOLDS = {
    "hr_high": 150,    # Heart rate above this triggers high-HR alarm
    "hr_low": 40,      # Heart rate below this triggers low-HR alarm
    "spo2_low": 90,    # SpO2 below this triggers low-SpO2 alarm
}

# =============================================================================
# Color Constants (RGB tuples for Pillow / display rendering)
# =============================================================================

COLOR_BLACK = (0, 0, 0)
COLOR_WHITE = (255, 255, 255)
COLOR_GREEN = (0, 255, 0)          # ECG waveform and heart rate text
COLOR_CYAN = (0, 255, 255)         # SpO2 waveform and text
COLOR_RED = (255, 0, 0)            # Alarm indicators
COLOR_DARK_RED = (128, 0, 0)       # Alarm background
COLOR_YELLOW = (255, 255, 0)       # Warning text
COLOR_DARK_GRAY = (40, 40, 40)     # Separator lines

# =============================================================================
# Development / Debug Settings
# =============================================================================

# Set to True to use mock display classes (no real hardware needed).
# Can also be set via --mock-hardware command-line flag in main.py.
DEVELOPMENT = os.environ.get("DIORAMA_DEV", "0") == "1"
