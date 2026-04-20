"""
tests/test_settings_store.py - Tests for persistent settings caching.
"""

import multiprocessing
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from shared.settings_store import load_settings, save_settings
from shared.state import create_state


class TestSettingsStore:
    """Tests for settings persistence across restart."""

    def test_save_and_reload_settings(self):
        manager = multiprocessing.Manager()
        original_path = config.SETTINGS_CACHE_PATH

        with tempfile.TemporaryDirectory() as tmpdir:
            config.SETTINGS_CACHE_PATH = os.path.join(tmpdir, "settings.json")

            try:
                state = create_state(manager)
                state["monitor_hr"] = 88
                state["monitor_spo2"] = 94
                state["monitor_alarm"] = "hr_high"
                state["ransomware_web_enabled"] = True
                state["xray1_interval"] = 17
                state["xray1_auto_play"] = False
                state["ransomware_monitor_image"] = "warning.png"

                save_settings(state)

                restored = create_state(manager)
                assert load_settings(restored) is True

                assert restored["monitor_hr"] == 88
                assert restored["monitor_spo2"] == 94
                assert restored["monitor_alarm"] == "hr_high"
                assert restored["ransomware_web_enabled"] is True
                assert restored["ransomware_active"] is True
                assert restored["xray1_interval"] == 17
                assert restored["xray1_auto_play"] is False
                assert restored["ransomware_monitor_image"] == "warning.png"
            finally:
                config.SETTINGS_CACHE_PATH = original_path
                manager.shutdown()
