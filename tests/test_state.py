"""
tests/test_state.py - Tests for shared state management.
"""

import multiprocessing
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from shared.ransomware import recompute_active, ransomware_targets, set_gpio_asserted, set_web_enabled
from shared.state import DEFAULT_STATE, create_state, scan_xray_images


class TestDefaultState:
    """Tests for the DEFAULT_STATE dictionary."""

    def test_has_monitor_keys(self):
        assert "monitor_hr" in DEFAULT_STATE
        assert "monitor_spo2" in DEFAULT_STATE
        assert "monitor_alarm" in DEFAULT_STATE

    def test_has_per_display_xray_keys(self):
        for display in config.XRAY_DISPLAYS:
            display_id = display["id"]
            assert f"{display_id}_images" in DEFAULT_STATE
            assert f"{display_id}_current_index" in DEFAULT_STATE
            assert f"{display_id}_auto_play" in DEFAULT_STATE
            assert f"{display_id}_interval" in DEFAULT_STATE
            assert f"{display_id}_running" in DEFAULT_STATE
            assert f"{display_id}_status" in DEFAULT_STATE

    def test_has_ransomware_keys(self):
        assert "ransomware_web_enabled" in DEFAULT_STATE
        assert "ransomware_gpio_asserted" in DEFAULT_STATE
        assert "ransomware_active" in DEFAULT_STATE
        for target in ransomware_targets():
            assert f"ransomware_{target}_image" in DEFAULT_STATE


class TestCreateState:
    """Tests for state creation and ransomware merge behavior."""

    def setup_method(self):
        self.manager = multiprocessing.Manager()
        self.state = create_state(self.manager)

    def teardown_method(self):
        self.manager.shutdown()

    def test_creates_state_with_all_default_keys(self):
        for key, value in DEFAULT_STATE.items():
            assert key in self.state
            assert self.state[key] == value

    def test_ransomware_either_source_enables(self):
        set_web_enabled(self.state, True)
        assert self.state["ransomware_active"] is True

        set_web_enabled(self.state, False)
        set_gpio_asserted(self.state, True)
        assert self.state["ransomware_active"] is True

    def test_ransomware_gpio_release_falls_back_to_web_state(self):
        set_web_enabled(self.state, True)
        set_gpio_asserted(self.state, True)
        assert self.state["ransomware_active"] is True

        set_gpio_asserted(self.state, False)
        assert self.state["ransomware_active"] is True

        set_web_enabled(self.state, False)
        assert self.state["ransomware_active"] is False

    def test_recompute_active_clears_when_both_sources_off(self):
        self.state["ransomware_web_enabled"] = False
        self.state["ransomware_gpio_asserted"] = False
        assert recompute_active(self.state) is False


class TestScanXrayImages:
    """Tests for per-display x-ray directory scanning."""

    def setup_method(self):
        self.manager = multiprocessing.Manager()
        self.state = create_state(self.manager)

    def teardown_method(self):
        self.manager.shutdown()

    def test_scan_empty_directory(self):
        display_id = config.XRAY_DISPLAYS[0]["id"]
        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = config.XRAY_BASE_DIR
            config.XRAY_BASE_DIR = tmpdir
            try:
                os.makedirs(config.xray_dir_for(display_id), exist_ok=True)
                scan_xray_images(self.state, display_id)
                assert list(self.state[f"{display_id}_images"]) == []
                assert self.state[f"{display_id}_status"] == "no_images"
            finally:
                config.XRAY_BASE_DIR = original_dir

    def test_scan_finds_and_sorts_image_files(self):
        display_id = config.XRAY_DISPLAYS[0]["id"]
        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = config.XRAY_BASE_DIR
            config.XRAY_BASE_DIR = tmpdir
            try:
                xray_dir = config.xray_dir_for(display_id)
                os.makedirs(xray_dir, exist_ok=True)
                for name in ["charlie.jpg", "alpha.png", "notes.txt", "bravo.bmp"]:
                    open(os.path.join(xray_dir, name), "w").close()

                scan_xray_images(self.state, display_id)

                assert list(self.state[f"{display_id}_images"]) == [
                    "alpha.png",
                    "bravo.bmp",
                    "charlie.jpg",
                ]
                assert self.state[f"{display_id}_status"] == "running"
            finally:
                config.XRAY_BASE_DIR = original_dir
