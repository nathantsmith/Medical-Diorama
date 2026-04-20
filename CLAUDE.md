# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Medical Diorama is a Raspberry Pi 5 application that drives a prop medical display for dioramas or film sets. It runs three concurrent processes:

1. **Patient Monitor** — renders a live ECG/SpO2 display onto a Waveshare 2" SPI LCD (ST7789V, 240×320) using Pillow at ~30 FPS
2. **X-Ray Viewer** — shows a fullscreen slideshow on a 4" HDMI touchscreen using pygame with swipe gesture navigation
3. **Web Portal** — a Flask/SocketIO control panel (port 5000) for changing vitals, triggering alarms, and uploading X-ray images

## Running the Application

```bash
# Production (real hardware)
python main.py

# Development (no Pi hardware needed)
python main.py --mock-hardware

# Skip specific processes
python main.py --no-monitor --no-xray   # web portal only
python main.py --mock-hardware --debug  # dev + Flask debug mode
```

Set `DIORAMA_DEV=1` in the environment as an alternative to `--mock-hardware`.

## Running Tests

```bash
# All tests
python -m pytest tests/

# Single test file
python -m pytest tests/test_web.py

# Single test
python -m pytest tests/test_web.py::TestMonitorAPI::test_set_vitals
```

Tests require no real hardware — they use `multiprocessing.Manager` directly and Flask's test client. Web tests set env vars (`ADMIN_USERNAME`, `ADMIN_PASSWORD`, `SECRET_KEY`) at the top of the file before importing app modules.

## Architecture

### Process Model

`main.py` uses `multiprocessing.set_start_method("spawn")` and a `multiprocessing.Manager().dict()` as the single shared state store. All three child processes receive a reference to this proxy dict and read/write it to communicate.

**Critical Manager dict gotcha:** nested mutables (lists) must be re-assigned to trigger cross-process sync:
```python
# WRONG — won't propagate to other processes
state["xray_images"].append("new.jpg")

# RIGHT — copy, mutate, re-assign
imgs = list(state["xray_images"])
imgs.append("new.jpg")
state["xray_images"] = imgs
```

### Shared State Keys (`shared/state.py`)

All state keys and their defaults live in `DEFAULT_STATE`. Monitor process reads `monitor_hr`, `monitor_spo2`, `monitor_alarm` and writes `monitor_fps`, `monitor_running`. X-ray process reads `xray_images`, `xray_current_index`, `xray_auto_play`, `xray_interval` and writes `xray_running`, `xray_status`. Web portal reads everything and writes most keys.

### Monitor Process (`monitor/`)

- `process.py` — render loop: read state → check alarm thresholds → render frame → push to SPI display → sleep
- `renderer.py` — composes each 240×320 PIL Image (HR section, ECG waveform, SpO2 section, pleth waveform, alarm bar)
- `waveforms.py` — generates ECG and plethysmograph waveform point arrays as a function of BPM and time offset
- `spi_display.py` — `SPIDisplay` (real hardware) and `MockSPIDisplay` (no-op); display receives PIL Images

Alarm logic: the monitor auto-triggers alarms when vitals cross thresholds in `ALARM_THRESHOLDS` (config.py), but only when no alarm is already set — this prevents the threshold check from overriding manually-triggered alarms from the web UI.

### X-Ray Process (`xray/`)

- `process.py` — pygame event loop with image caching; re-checks image list every second to pick up web portal uploads
- `slideshow.py` — manages current image index, auto-advance timer, next/prev navigation
- `gestures.py` — `SwipeDetector` translates raw pygame touch events into `"swipe_left"`, `"swipe_right"`, `"tap"`

### Web Portal (`web/`)

- `app.py` — Flask app factory (`create_app`), SocketIO setup, background thread that emits `status_update` every second
- `auth.py` — single-user Flask-Login auth; credentials from `ADMIN_USERNAME`/`ADMIN_PASSWORD` env vars (`.env` file)
- `routes_monitor.py` — `POST /monitor/set` (vitals), `POST /monitor/alarm`, `GET /monitor/status`
- `routes_xray.py` — `GET /xray/list`, `POST /xray/upload`, `POST /xray/delete`, `POST /xray/toggle-auto`, `POST /xray/set-interval`
- `routes_status.py` — `GET /status`, `GET /dashboard`

Real-time browser updates use Flask-SocketIO: the background emitter thread pushes `status_update` events; the dashboard JS listens and updates the UI without polling.

## Configuration

All hardware pins, display dimensions, FPS targets, file paths, alarm thresholds, and color constants are in `config.py`. The `DEVELOPMENT` flag is set by `DIORAMA_DEV=1` env var or `--mock-hardware` CLI flag.

## Environment / Secrets

Create a `.env` file in the project root (loaded by `python-dotenv`):
```
ADMIN_USERNAME=admin
ADMIN_PASSWORD=yourpassword
SECRET_KEY=a-random-secret-key
```

## Dependencies

Install with `pip install -r requirements.txt`. Hardware-only packages (`st7789`, `spidev`, `gpiod`) will fail to install on non-Pi systems — use `--mock-hardware` to avoid importing them.
