"""
tests/test_web.py - Tests for the Flask web portal.
"""

import io
import multiprocessing
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["ADMIN_USERNAME"] = "testadmin"
os.environ["ADMIN_PASSWORD"] = "testpass"
os.environ["SECRET_KEY"] = "test-secret-key"

import config
from shared.state import create_state
from web.app import create_app, _get_state_snapshot


def _make_test_app():
    """Create a test Flask app with temp storage for image uploads."""
    manager = multiprocessing.Manager()
    state = create_state(manager)
    app, socketio = create_app(state)
    app.config["TESTING"] = True

    temp_root = tempfile.mkdtemp(prefix="medical-diorama-tests-")
    original_xray_dir = config.XRAY_BASE_DIR
    original_ransomware_dir = config.RANSOMWARE_BASE_DIR
    config.XRAY_BASE_DIR = os.path.join(temp_root, "xrays")
    config.RANSOMWARE_BASE_DIR = os.path.join(temp_root, "ransomware")

    for display in config.XRAY_DISPLAYS:
        os.makedirs(config.xray_dir_for(display["id"]), exist_ok=True)
    for target in ["monitor"] + [display["id"] for display in config.XRAY_DISPLAYS]:
        os.makedirs(config.ransomware_dir_for(target), exist_ok=True)

    return (
        app,
        state,
        manager,
        temp_root,
        original_xray_dir,
        original_ransomware_dir,
    )


class _BaseWebTest:
    """Shared setup/teardown for web tests."""

    def setup_method(self):
        (
            self.app,
            self.state,
            self.manager,
            self.temp_root,
            self.original_xray_dir,
            self.original_ransomware_dir,
        ) = _make_test_app()
        self.client = self.app.test_client()

    def teardown_method(self):
        config.XRAY_BASE_DIR = self.original_xray_dir
        config.RANSOMWARE_BASE_DIR = self.original_ransomware_dir
        self.manager.shutdown()
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def login(self):
        return self.client.post(
            "/login",
            data={"username": "testadmin", "password": "testpass"},
            follow_redirects=True,
        )


class TestAuth(_BaseWebTest):
    """Tests for authentication."""

    def test_login_page_loads(self):
        resp = self.client.get("/login")
        assert resp.status_code == 200
        assert b"Login" in resp.data or b"login" in resp.data

    def test_login_success(self):
        resp = self.login()
        assert resp.status_code == 200

    def test_unauthenticated_redirect(self):
        resp = self.client.get("/dashboard")
        assert resp.status_code == 302


class TestMonitorAPI(_BaseWebTest):
    """Tests for the patient monitor control API."""

    def setup_method(self):
        super().setup_method()
        self.login()

    def test_set_vitals(self):
        resp = self.client.post(
            "/monitor/set",
            json={"hr": 80, "spo2": 95},
            content_type="application/json",
        )
        data = resp.get_json()
        assert data["ok"] is True
        assert self.state["monitor_hr"] == 80
        assert self.state["monitor_spo2"] == 95

    def test_invalid_alarm_type(self):
        resp = self.client.post(
            "/monitor/alarm",
            json={"alarm": "invalid_alarm"},
            content_type="application/json",
        )
        assert resp.status_code == 400


class TestXrayAPI(_BaseWebTest):
    """Tests for per-display X-ray routes."""

    def setup_method(self):
        super().setup_method()
        self.login()
        self.display_id = config.XRAY_DISPLAYS[0]["id"]

    def test_list_empty(self):
        resp = self.client.get(f"/xray/{self.display_id}/list")
        data = resp.get_json()
        assert data["display_id"] == self.display_id
        assert data["images"] == []
        assert data["current_index"] == 0

    def test_toggle_auto_play(self):
        resp = self.client.post(f"/xray/{self.display_id}/toggle-auto")
        data = resp.get_json()
        assert data["ok"] is True
        assert self.state[f"{self.display_id}_auto_play"] is False

    def test_set_interval(self):
        resp = self.client.post(
            f"/xray/{self.display_id}/set-interval",
            json={"interval": 15},
            content_type="application/json",
        )
        data = resp.get_json()
        assert data["ok"] is True
        assert self.state[f"{self.display_id}_interval"] == 15

    def test_upload_image(self):
        resp = self.client.post(
            f"/xray/{self.display_id}/upload",
            data={"image": (io.BytesIO(b"fake-image"), "scan.jpg")},
            content_type="multipart/form-data",
        )
        data = resp.get_json()
        assert data["ok"] is True
        assert data["filename"] == "scan.jpg"
        assert self.state[f"{self.display_id}_images"] == ["scan.jpg"]


class TestRansomwareAPI(_BaseWebTest):
    """Tests for ransomware controls and uploads."""

    def setup_method(self):
        super().setup_method()
        self.login()

    def test_toggle_updates_web_state(self):
        resp = self.client.post("/ransomware/toggle")
        data = resp.get_json()
        assert data["ransomware_web_enabled"] is True
        assert data["ransomware_active"] is True

    def test_gpio_high_keeps_mode_active_after_web_toggle_off(self):
        self.state["ransomware_gpio_asserted"] = True
        self.state["ransomware_active"] = True

        self.client.post("/ransomware/toggle", json={"enabled": True})
        resp = self.client.post("/ransomware/toggle", json={"enabled": False})
        data = resp.get_json()

        assert data["ransomware_web_enabled"] is False
        assert data["ransomware_gpio_asserted"] is True
        assert data["ransomware_active"] is True

    def test_upload_replaces_existing_target_image(self):
        target = "monitor"

        first = self.client.post(
            f"/ransomware/{target}/upload",
            data={"image": (io.BytesIO(b"first"), "first.png")},
            content_type="multipart/form-data",
        )
        assert first.status_code == 200
        assert self.state["ransomware_monitor_image"] == "first.png"

        second = self.client.post(
            f"/ransomware/{target}/upload",
            data={"image": (io.BytesIO(b"second"), "second.png")},
            content_type="multipart/form-data",
        )
        data = second.get_json()
        target_dir = config.ransomware_dir_for(target)

        assert data["filename"] == "second.png"
        assert self.state["ransomware_monitor_image"] == "second.png"
        assert sorted(os.listdir(target_dir)) == ["second.png"]

    def test_delete_clears_target_image(self):
        target = "xray1"
        self.client.post(
            f"/ransomware/{target}/upload",
            data={"image": (io.BytesIO(b"fake"), "screen.jpg")},
            content_type="multipart/form-data",
        )

        resp = self.client.delete(f"/ransomware/{target}")
        data = resp.get_json()

        assert data["ok"] is True
        assert self.state["ransomware_xray1_image"] is None
        assert os.listdir(config.ransomware_dir_for(target)) == []

    def test_invalid_target_returns_404(self):
        resp = self.client.post(
            "/ransomware/not-a-target/upload",
            data={"image": (io.BytesIO(b"fake"), "screen.jpg")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 404


class TestStatusAPI(_BaseWebTest):
    """Tests for status snapshots."""

    def setup_method(self):
        super().setup_method()
        self.login()

    def test_status_returns_ransomware_and_xray_state(self):
        resp = self.client.get("/status")
        data = resp.get_json()

        assert "ransomware_web_enabled" in data
        assert "ransomware_gpio_asserted" in data
        assert "ransomware_active" in data
        assert "ransomware_monitor_image" in data
        for display in config.XRAY_DISPLAYS:
            display_id = display["id"]
            assert f"{display_id}_images" in data
            assert f"{display_id}_current_index" in data
            assert f"ransomware_{display_id}_image" in data

    def test_socket_snapshot_contains_ransomware_fields(self):
        self.state["ransomware_web_enabled"] = True
        self.state["ransomware_active"] = True
        self.state["ransomware_monitor_image"] = "monitor.png"

        data = _get_state_snapshot(self.state)

        assert data["ransomware_web_enabled"] is True
        assert data["ransomware_active"] is True
        assert data["ransomware_monitor_image"] == "monitor.png"
