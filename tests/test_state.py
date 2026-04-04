"""
tests/test_state.py - Tests for shared state management.

Verifies that:
  - Default state has all expected keys
  - State creation works with a Manager
  - scan_xray_images finds image files correctly
"""

import multiprocessing
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.state import DEFAULT_STATE, create_state, scan_xray_images
import config


class TestDefaultState:
    """Tests for the DEFAULT_STATE dictionary."""

    def test_has_monitor_keys(self):
        """Default state should include all patient monitor keys."""
        assert "monitor_hr" in DEFAULT_STATE
        assert "monitor_spo2" in DEFAULT_STATE
        assert "monitor_alarm" in DEFAULT_STATE
        assert "monitor_alarm_active" in DEFAULT_STATE

    def test_has_xray_keys(self):
        """Default state should include all X-ray viewer keys."""
        assert "xray_images" in DEFAULT_STATE
        assert "xray_current_index" in DEFAULT_STATE
        assert "xray_auto_play" in DEFAULT_STATE
        assert "xray_interval" in DEFAULT_STATE

    def test_has_status_keys(self):
        """Default state should include status tracking keys."""
        assert "monitor_fps" in DEFAULT_STATE
        assert "monitor_running" in DEFAULT_STATE
        assert "xray_running" in DEFAULT_STATE
        assert "xray_status" in DEFAULT_STATE

    def test_default_hr_is_reasonable(self):
        """Default heart rate should be a normal resting value."""
        assert 60 <= DEFAULT_STATE["monitor_hr"] <= 100

    def test_default_spo2_is_reasonable(self):
        """Default SpO2 should be a normal value."""
        assert 95 <= DEFAULT_STATE["monitor_spo2"] <= 100

    def test_default_alarm_is_none(self):
        """No alarm should be active by default."""
        assert DEFAULT_STATE["monitor_alarm"] is None

    def test_default_xray_images_is_empty_list(self):
        """X-ray image list should start empty."""
        assert DEFAULT_STATE["xray_images"] == []


class TestCreateState:
    """Tests for the create_state function."""

    def test_creates_state_with_all_keys(self):
        """Created state should have all keys from DEFAULT_STATE."""
        manager = multiprocessing.Manager()
        try:
            state = create_state(manager)
            for key in DEFAULT_STATE:
                assert key in state, f"Missing key: {key}"
        finally:
            manager.shutdown()

    def test_state_values_match_defaults(self):
        """Created state values should match the defaults."""
        manager = multiprocessing.Manager()
        try:
            state = create_state(manager)
            assert state["monitor_hr"] == DEFAULT_STATE["monitor_hr"]
            assert state["monitor_spo2"] == DEFAULT_STATE["monitor_spo2"]
            assert state["monitor_alarm"] == DEFAULT_STATE["monitor_alarm"]
        finally:
            manager.shutdown()


class TestScanXrayImages:
    """Tests for the scan_xray_images function."""

    def test_scan_empty_directory(self):
        """Scanning an empty directory should result in an empty image list."""
        manager = multiprocessing.Manager()
        try:
            state = create_state(manager)

            # Use a temporary empty directory
            with tempfile.TemporaryDirectory() as tmpdir:
                original_dir = config.XRAY_DIR
                config.XRAY_DIR = tmpdir
                try:
                    scan_xray_images(state)
                    assert list(state["xray_images"]) == []
                    assert state["xray_status"] == "no_images"
                finally:
                    config.XRAY_DIR = original_dir
        finally:
            manager.shutdown()

    def test_scan_finds_image_files(self):
        """Scanning should find .jpg, .png, and other image files."""
        manager = multiprocessing.Manager()
        try:
            state = create_state(manager)

            with tempfile.TemporaryDirectory() as tmpdir:
                # Create some test files
                for name in ["xray1.jpg", "xray2.png", "notes.txt", "scan.bmp"]:
                    open(os.path.join(tmpdir, name), "w").close()

                original_dir = config.XRAY_DIR
                config.XRAY_DIR = tmpdir
                try:
                    scan_xray_images(state)
                    images = list(state["xray_images"])

                    # Should find the image files but not the text file
                    assert "xray1.jpg" in images
                    assert "xray2.png" in images
                    assert "scan.bmp" in images
                    assert "notes.txt" not in images
                    assert state["xray_status"] == "running"
                finally:
                    config.XRAY_DIR = original_dir
        finally:
            manager.shutdown()

    def test_scan_sorts_alphabetically(self):
        """Images should be sorted alphabetically."""
        manager = multiprocessing.Manager()
        try:
            state = create_state(manager)

            with tempfile.TemporaryDirectory() as tmpdir:
                for name in ["charlie.jpg", "alpha.jpg", "bravo.jpg"]:
                    open(os.path.join(tmpdir, name), "w").close()

                original_dir = config.XRAY_DIR
                config.XRAY_DIR = tmpdir
                try:
                    scan_xray_images(state)
                    images = list(state["xray_images"])
                    assert images == ["alpha.jpg", "bravo.jpg", "charlie.jpg"]
                finally:
                    config.XRAY_DIR = original_dir
        finally:
            manager.shutdown()
