"""
tests/test_ransomware.py - Tests for ransomware helper behavior and rendering.
"""

import os
import sys
import tempfile

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monitor.renderer import MonitorRenderer
from shared.ransomware import get_image_path


class TestMonitorRendererRansomware:
    """Tests for the monitor ransomware rendering path."""

    def test_render_fallback_frame(self):
        renderer = MonitorRenderer()
        frame = renderer.render_ransomware_frame()
        assert frame.size == (320, 240)

    def test_render_uploaded_image_frame(self):
        renderer = MonitorRenderer()
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = os.path.join(tmpdir, "screen.png")
            Image.new("RGB", (640, 480), (255, 0, 0)).save(image_path)

            frame = renderer.render_ransomware_frame(image_path)
            assert frame.size == (320, 240)
            assert frame.getpixel((160, 120)) == (255, 0, 0)


class TestMonitorRendererNormalMode:
    """Tests for the normal monitor renderer layout."""

    def test_alarm_frame_renders_without_geometry_error(self):
        renderer = MonitorRenderer()
        frame = renderer.render_frame(
            {
                "monitor_hr": 180,
                "monitor_spo2": 92,
                "monitor_alarm": "hr_high",
            },
            time_offset=0.0,
        )
        assert frame.size == (320, 240)


class TestRansomwareImagePath:
    """Tests for ransomware asset path resolution."""

    def test_missing_filename_returns_none(self):
        state = {}
        assert get_image_path(state, "monitor") is None
