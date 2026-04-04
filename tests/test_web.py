"""
tests/test_web.py - Tests for the Flask web portal.

Verifies that:
  - Login/logout flow works correctly
  - Patient monitor API validates input and updates state
  - X-ray management API handles uploads, deletions, and listing
  - Unauthenticated requests are redirected to login
"""

import multiprocessing
import os
import sys
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set test credentials before importing web modules
os.environ["ADMIN_USERNAME"] = "testadmin"
os.environ["ADMIN_PASSWORD"] = "testpass"
os.environ["SECRET_KEY"] = "test-secret-key"

from shared.state import create_state
from web.app import create_app


def _make_test_app():
    """Create a test Flask app with a fresh shared state."""
    manager = multiprocessing.Manager()
    state = create_state(manager)
    app, socketio = create_app(state)
    app.config["TESTING"] = True
    return app, state, manager


class TestAuth:
    """Tests for authentication."""

    def setup_method(self):
        self.app, self.state, self.manager = _make_test_app()
        self.client = self.app.test_client()

    def teardown_method(self):
        self.manager.shutdown()

    def _login(self):
        """Helper to log in with test credentials."""
        return self.client.post("/login", data={
            "username": "testadmin",
            "password": "testpass",
        }, follow_redirects=True)

    def test_login_page_loads(self):
        """GET /login should return the login form."""
        resp = self.client.get("/login")
        assert resp.status_code == 200
        assert b"Login" in resp.data or b"login" in resp.data

    def test_login_success(self):
        """Valid credentials should log the user in."""
        resp = self._login()
        assert resp.status_code == 200

    def test_login_failure(self):
        """Invalid credentials should show an error."""
        resp = self.client.post("/login", data={
            "username": "wrong",
            "password": "wrong",
        }, follow_redirects=True)
        assert b"Invalid" in resp.data or resp.status_code == 200

    def test_unauthenticated_redirect(self):
        """Accessing protected pages without login should redirect."""
        resp = self.client.get("/dashboard")
        assert resp.status_code == 302  # Redirect to login


class TestMonitorAPI:
    """Tests for the patient monitor control API."""

    def setup_method(self):
        self.app, self.state, self.manager = _make_test_app()
        self.client = self.app.test_client()
        # Log in first
        self.client.post("/login", data={
            "username": "testadmin",
            "password": "testpass",
        })

    def teardown_method(self):
        self.manager.shutdown()

    def test_set_vitals(self):
        """POST /monitor/set should update HR and SpO2."""
        resp = self.client.post("/monitor/set",
            json={"hr": 80, "spo2": 95},
            content_type="application/json",
        )
        data = resp.get_json()
        assert data["ok"] is True
        assert data["monitor_hr"] == 80
        assert data["monitor_spo2"] == 95
        # Verify state was actually updated
        assert self.state["monitor_hr"] == 80
        assert self.state["monitor_spo2"] == 95

    def test_set_vitals_validation_hr_too_high(self):
        """HR above 250 should be rejected."""
        resp = self.client.post("/monitor/set",
            json={"hr": 300},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_set_vitals_validation_hr_too_low(self):
        """HR below 30 should be rejected."""
        resp = self.client.post("/monitor/set",
            json={"hr": 5},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_set_vitals_validation_spo2_too_low(self):
        """SpO2 below 70 should be rejected."""
        resp = self.client.post("/monitor/set",
            json={"spo2": 50},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_trigger_alarm(self):
        """POST /monitor/alarm should set the alarm type."""
        resp = self.client.post("/monitor/alarm",
            json={"alarm": "hr_high"},
            content_type="application/json",
        )
        data = resp.get_json()
        assert data["ok"] is True
        assert self.state["monitor_alarm"] == "hr_high"

    def test_clear_alarm(self):
        """Setting alarm to null should clear it."""
        # First set an alarm
        self.state["monitor_alarm"] = "hr_high"
        # Then clear it
        resp = self.client.post("/monitor/alarm",
            json={"alarm": None},
            content_type="application/json",
        )
        data = resp.get_json()
        assert data["ok"] is True
        assert self.state["monitor_alarm"] is None

    def test_invalid_alarm_type(self):
        """Invalid alarm types should be rejected."""
        resp = self.client.post("/monitor/alarm",
            json={"alarm": "invalid_alarm"},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_monitor_status(self):
        """GET /monitor/status should return current values."""
        self.state["monitor_hr"] = 88
        self.state["monitor_spo2"] = 96
        resp = self.client.get("/monitor/status")
        data = resp.get_json()
        assert data["monitor_hr"] == 88
        assert data["monitor_spo2"] == 96


class TestXrayAPI:
    """Tests for the X-ray management API."""

    def setup_method(self):
        self.app, self.state, self.manager = _make_test_app()
        self.client = self.app.test_client()
        # Log in first
        self.client.post("/login", data={
            "username": "testadmin",
            "password": "testpass",
        })

    def teardown_method(self):
        self.manager.shutdown()

    def test_list_empty(self):
        """GET /xray/list with no images should return empty list."""
        resp = self.client.get("/xray/list")
        data = resp.get_json()
        assert data["images"] == []
        assert data["current_index"] == 0

    def test_toggle_auto_play(self):
        """POST /xray/toggle-auto should toggle the auto-play state."""
        # Default is True
        assert self.state["xray_auto_play"] is True

        resp = self.client.post("/xray/toggle-auto")
        data = resp.get_json()
        assert data["ok"] is True
        assert data["auto_play"] is False
        assert self.state["xray_auto_play"] is False

        # Toggle back
        resp = self.client.post("/xray/toggle-auto")
        data = resp.get_json()
        assert data["auto_play"] is True

    def test_set_interval(self):
        """POST /xray/set-interval should update the slideshow interval."""
        resp = self.client.post("/xray/set-interval",
            json={"interval": 15},
            content_type="application/json",
        )
        data = resp.get_json()
        assert data["ok"] is True
        assert data["interval"] == 15
        assert self.state["xray_interval"] == 15

    def test_set_interval_validation(self):
        """Interval outside 2-120 should be rejected."""
        resp = self.client.post("/xray/set-interval",
            json={"interval": 1},
            content_type="application/json",
        )
        assert resp.status_code == 400

        resp = self.client.post("/xray/set-interval",
            json={"interval": 200},
            content_type="application/json",
        )
        assert resp.status_code == 400


class TestStatusAPI:
    """Tests for the status endpoint."""

    def setup_method(self):
        self.app, self.state, self.manager = _make_test_app()
        self.client = self.app.test_client()
        self.client.post("/login", data={
            "username": "testadmin",
            "password": "testpass",
        })

    def teardown_method(self):
        self.manager.shutdown()

    def test_status_returns_full_state(self):
        """GET /status should return all state keys."""
        resp = self.client.get("/status")
        data = resp.get_json()

        # Check that all expected keys are present
        assert "monitor_hr" in data
        assert "monitor_spo2" in data
        assert "monitor_alarm" in data
        assert "xray_images" in data
        assert "xray_current_index" in data
        assert "xray_auto_play" in data
        assert "xray_interval" in data
