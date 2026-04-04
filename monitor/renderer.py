"""
monitor/renderer.py - Composes each frame of the patient monitor display.

The monitor screen layout (240 wide x 320 tall, portrait orientation):

    ┌──────────────────────────┐
    │  ♥  HR: 72 BPM     [top]│  <- 40px: heart rate text (green)
    ├──────────────────────────┤
    │                          │
    │   ECG Waveform Area      │  <- 100px: scrolling ECG trace (green)
    │                          │
    ├──────────────────────────┤
    │  SpO2: 98%          [mid]│  <- 40px: blood oxygen text (cyan)
    ├──────────────────────────┤
    │                          │
    │   SpO2 Waveform Area     │  <- 100px: scrolling pleth trace (cyan)
    │                          │
    ├──────────────────────────┤
    │  ALARM STATUS BAR   [bot]│  <- 40px: alarm indicator (red flash)
    └──────────────────────────┘

Each frame is rendered as a fresh PIL Image that gets pushed to the display.
"""

from PIL import Image, ImageDraw, ImageFont

from config import (
    MONITOR_WIDTH, MONITOR_HEIGHT,
    COLOR_BLACK, COLOR_WHITE, COLOR_GREEN, COLOR_CYAN,
    COLOR_RED, COLOR_DARK_RED, COLOR_DARK_GRAY, COLOR_YELLOW,
)
from monitor.waveforms import ECGWaveform, SpO2Waveform

# =============================================================================
# Layout Constants (pixel positions for each section)
# =============================================================================

# Heart rate text section
HR_SECTION_TOP = 0
HR_SECTION_HEIGHT = 40

# ECG waveform drawing area
ECG_SECTION_TOP = HR_SECTION_HEIGHT
ECG_SECTION_HEIGHT = 100

# SpO2 text section
SPO2_SECTION_TOP = ECG_SECTION_TOP + ECG_SECTION_HEIGHT
SPO2_SECTION_HEIGHT = 40

# SpO2 waveform drawing area
PLETH_SECTION_TOP = SPO2_SECTION_TOP + SPO2_SECTION_HEIGHT
PLETH_SECTION_HEIGHT = 100

# Alarm status bar at the bottom
ALARM_SECTION_TOP = PLETH_SECTION_TOP + PLETH_SECTION_HEIGHT
ALARM_SECTION_HEIGHT = MONITOR_HEIGHT - ALARM_SECTION_TOP  # fills remaining space


class MonitorRenderer:
    """
    Renders the patient monitor display frame by frame.

    Creates a 240x320 PIL Image each frame containing:
    - Heart rate reading and label
    - Scrolling ECG waveform
    - SpO2 reading and label
    - Scrolling plethysmograph waveform
    - Alarm status bar (flashes red when alarm is active)
    """

    def __init__(self):
        """Set up the waveform generators and load fonts."""
        # Create waveform generators
        self._ecg = ECGWaveform()
        self._spo2 = SpO2Waveform()

        # Track frame count for alarm flash toggling
        self._frame_count = 0

        # Try to load a nice monospace font; fall back to PIL default
        self._font_large = self._load_font(24)
        self._font_medium = self._load_font(18)
        self._font_small = self._load_font(14)

    def _load_font(self, size):
        """
        Try to load a TrueType font at the given size.

        Attempts several common font paths on Linux/Raspberry Pi.
        Falls back to PIL's built-in bitmap font if none are found.

        Args:
            size: Font size in pixels.

        Returns:
            A PIL ImageFont object.
        """
        # Common font paths on Raspberry Pi OS / Debian
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        ]

        for path in font_paths:
            try:
                return ImageFont.truetype(path, size)
            except (IOError, OSError):
                continue

        # Fall back to PIL default font (bitmap, ignores size parameter)
        return ImageFont.load_default()

    def render_frame(self, state, time_offset):
        """
        Render one complete frame of the patient monitor display.

        Args:
            state: Dict-like object with current monitor values:
                   - monitor_hr (int): heart rate BPM
                   - monitor_spo2 (int): SpO2 percentage
                   - monitor_alarm (str or None): alarm type
                   - monitor_alarm_active (bool): alarm flash state
            time_offset: Current time in seconds (for waveform scrolling).

        Returns:
            A PIL.Image.Image (240x320, RGB mode) ready to push to the display.
        """
        self._frame_count += 1

        # Read current values from shared state
        hr = state.get("monitor_hr", 72)
        spo2 = state.get("monitor_spo2", 98)
        alarm = state.get("monitor_alarm", None)

        # Create a fresh black canvas
        image = Image.new("RGB", (MONITOR_WIDTH, MONITOR_HEIGHT), COLOR_BLACK)
        draw = ImageDraw.Draw(image)

        # Draw each section
        self._draw_hr_section(draw, hr, alarm)
        self._draw_ecg_waveform(draw, hr, time_offset)
        self._draw_separator(draw, SPO2_SECTION_TOP)
        self._draw_spo2_section(draw, spo2, alarm)
        self._draw_pleth_waveform(draw, hr, time_offset)
        self._draw_separator(draw, ALARM_SECTION_TOP)
        self._draw_alarm_bar(draw, alarm)

        return image

    def _draw_hr_section(self, draw, hr, alarm):
        """
        Draw the heart rate text section at the top of the screen.

        Shows a heart symbol and the current BPM. Text flashes red
        if a heart rate alarm is active.

        Args:
            draw: PIL ImageDraw object.
            hr: Current heart rate in BPM.
            alarm: Current alarm type string or None.
        """
        # Choose text color: flash red/white for HR alarms
        if alarm in ("hr_high", "hr_low") and self._frame_count % 20 < 10:
            text_color = COLOR_RED
        else:
            text_color = COLOR_GREEN

        # Draw the heart symbol and BPM value
        # Use a heart character (or "HR" if font doesn't support it)
        draw.text((8, 8), "HR", fill=text_color, font=self._font_medium)
        draw.text((50, 4), f"{hr}", fill=text_color, font=self._font_large)
        draw.text((130, 12), "BPM", fill=text_color, font=self._font_small)

    def _draw_ecg_waveform(self, draw, bpm, time_offset):
        """
        Draw the scrolling ECG waveform trace.

        Gets waveform points from the ECG generator and draws them as
        a connected polyline (green on black background).

        Args:
            draw: PIL ImageDraw object.
            bpm: Current heart rate for waveform timing.
            time_offset: Current time for scroll position.
        """
        # Get normalized waveform points (y values are 0.0 to 1.0)
        raw_points = self._ecg.get_points(MONITOR_WIDTH, bpm, time_offset)

        # Convert normalized y-values to pixel coordinates within the ECG section
        pixel_points = []
        for x, y_norm in raw_points:
            # Map y from [0,1] to pixel range within the ECG section
            # Add a small margin (4px) top and bottom
            y_pixel = ECG_SECTION_TOP + 4 + int(y_norm * (ECG_SECTION_HEIGHT - 8))
            pixel_points.append((x, y_pixel))

        # Draw the waveform as a connected line
        # Need at least 2 points to draw a line
        if len(pixel_points) >= 2:
            draw.line(pixel_points, fill=COLOR_GREEN, width=2)

    def _draw_spo2_section(self, draw, spo2, alarm):
        """
        Draw the SpO2 text section in the middle of the screen.

        Shows "SpO2" label and the current percentage. Text flashes
        red if a low-SpO2 alarm is active.

        Args:
            draw: PIL ImageDraw object.
            spo2: Current SpO2 percentage.
            alarm: Current alarm type string or None.
        """
        # Choose text color: flash for SpO2 alarm
        if alarm == "spo2_low" and self._frame_count % 20 < 10:
            text_color = COLOR_RED
        else:
            text_color = COLOR_CYAN

        # Draw the SpO2 label and value
        draw.text((8, SPO2_SECTION_TOP + 8), "SpO2", fill=text_color, font=self._font_medium)
        draw.text((80, SPO2_SECTION_TOP + 4), f"{spo2}", fill=text_color, font=self._font_large)
        draw.text((150, SPO2_SECTION_TOP + 12), "%", fill=text_color, font=self._font_small)

    def _draw_pleth_waveform(self, draw, bpm, time_offset):
        """
        Draw the scrolling SpO2 plethysmograph waveform trace.

        Similar to ECG but drawn in cyan and uses the pleth waveform shape.

        Args:
            draw: PIL ImageDraw object.
            bpm: Current heart rate for waveform timing.
            time_offset: Current time for scroll position.
        """
        # Get normalized waveform points
        raw_points = self._spo2.get_points(MONITOR_WIDTH, bpm, time_offset)

        # Convert to pixel coordinates within the pleth section
        pixel_points = []
        for x, y_norm in raw_points:
            y_pixel = PLETH_SECTION_TOP + 4 + int(y_norm * (PLETH_SECTION_HEIGHT - 8))
            pixel_points.append((x, y_pixel))

        # Draw the waveform line in cyan
        if len(pixel_points) >= 2:
            draw.line(pixel_points, fill=COLOR_CYAN, width=2)

    def _draw_alarm_bar(self, draw, alarm):
        """
        Draw the alarm status bar at the bottom of the screen.

        When no alarm is active, shows "Normal" in green.
        When an alarm is active, flashes between red background with
        white "ALARM" text and black background (creates flashing effect).

        Args:
            draw: PIL ImageDraw object.
            alarm: Current alarm type string or None.
        """
        if alarm is None:
            # No alarm — show calm "Normal" status
            draw.text(
                (8, ALARM_SECTION_TOP + 10),
                "Status: Normal",
                fill=COLOR_GREEN,
                font=self._font_medium,
            )
        else:
            # Alarm active — flash the bar red every 10 frames
            is_flash_on = (self._frame_count % 20) < 10

            if is_flash_on:
                # Red background with white alarm text
                draw.rectangle(
                    [0, ALARM_SECTION_TOP, MONITOR_WIDTH, MONITOR_HEIGHT],
                    fill=COLOR_RED,
                )
                # Show which alarm is active
                alarm_labels = {
                    "hr_high": "HIGH HR",
                    "hr_low": "LOW HR",
                    "spo2_low": "LOW SpO2",
                }
                label = alarm_labels.get(alarm, "ALARM")
                draw.text(
                    (8, ALARM_SECTION_TOP + 4),
                    f"!! ALARM !!",
                    fill=COLOR_WHITE,
                    font=self._font_large,
                )
                draw.text(
                    (8, ALARM_SECTION_TOP + 28),
                    label,
                    fill=COLOR_YELLOW,
                    font=self._font_medium,
                )
            else:
                # Flash off — black bar (creates blinking effect)
                draw.rectangle(
                    [0, ALARM_SECTION_TOP, MONITOR_WIDTH, MONITOR_HEIGHT],
                    fill=COLOR_BLACK,
                )

    def _draw_separator(self, draw, y):
        """
        Draw a thin horizontal separator line.

        Args:
            draw: PIL ImageDraw object.
            y: Vertical pixel position for the line.
        """
        draw.line([(0, y), (MONITOR_WIDTH, y)], fill=COLOR_DARK_GRAY, width=1)
