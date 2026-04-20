"""
tests/test_xray_process.py - Tests for X-ray display binding helpers.
"""

from xray.process import (
    _candidate_runtime_dirs,
    _connected_output_index,
    _parse_wlr_randr_outputs,
    _parse_xrandr_outputs,
    _resolve_display_backend,
)


def test_parse_xrandr_outputs_reads_geometry_and_connection_state():
    sample = """
Screen 0: minimum 320 x 200, current 3840 x 1080, maximum 16384 x 16384
HDMI-1 connected primary 1920x1080+0+0 (normal left inverted right x axis y axis)
HDMI-2 disconnected (normal left inverted right x axis y axis)
"""

    outputs = _parse_xrandr_outputs(sample)

    assert outputs["HDMI-1"]["connected"] is True
    assert outputs["HDMI-1"]["width"] == 1920
    assert outputs["HDMI-1"]["height"] == 1080
    assert outputs["HDMI-1"]["x"] == 0
    assert outputs["HDMI-1"]["y"] == 0
    assert outputs["HDMI-2"]["connected"] is False


def test_parse_wlr_randr_outputs_reads_enabled_output_geometry():
    sample = """
HDMI-A-1 "Dell Inc. DELL U2412M 123456"
  Enabled: yes
  Modes:
    1920x1200 px, 59.950001 Hz (current, preferred)
  Position: 1920,0
HDMI-A-2 "Unknown"
  Enabled: no
"""

    outputs = _parse_wlr_randr_outputs(sample)

    assert outputs["HDMI-A-1"]["connected"] is True
    assert outputs["HDMI-A-1"]["width"] == 1920
    assert outputs["HDMI-A-1"]["height"] == 1200
    assert outputs["HDMI-A-1"]["x"] == 1920
    assert outputs["HDMI-A-1"]["y"] == 0
    assert outputs["HDMI-A-2"]["connected"] is False


def test_connected_output_index_tracks_connected_hdmi_order():
    outputs = {
        "HDMI-A-1": {"connected": False},
        "HDMI-A-2": {"connected": True},
    }

    assert _connected_output_index(outputs, "HDMI-A-1") is None
    assert _connected_output_index(outputs, "HDMI-A-2") == 0


def test_connected_output_index_keeps_stable_order_when_both_connected():
    outputs = {
        "HDMI-A-1": {"connected": True},
        "HDMI-A-2": {"connected": True},
    }

    assert _connected_output_index(outputs, "HDMI-A-1") == 0
    assert _connected_output_index(outputs, "HDMI-A-2") == 1


def test_candidate_runtime_dirs_prefers_env_and_includes_default(monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/tmp/runtime-custom")
    monkeypatch.setattr("os.getuid", lambda: 1000)

    runtime_dirs = _candidate_runtime_dirs()

    assert runtime_dirs == ["/tmp/runtime-custom", "/run/user/1000"]


def test_resolve_display_backend_uses_wayland_socket_when_present(monkeypatch, tmp_path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "wayland-1").touch()

    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime_dir))
    monkeypatch.setattr("os.getuid", lambda: 1000)

    backend, env_updates = _resolve_display_backend()

    assert backend == "wayland"
    assert env_updates["XDG_RUNTIME_DIR"] == str(runtime_dir)
    assert env_updates["WAYLAND_DISPLAY"] == "wayland-1"
    assert env_updates["SDL_VIDEODRIVER"] == "wayland"


def test_resolve_display_backend_falls_back_to_direct_without_session(monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr("xray.process._candidate_runtime_dirs", lambda: [])

    backend, env_updates = _resolve_display_backend()

    assert backend == "direct"
    assert env_updates == {}
