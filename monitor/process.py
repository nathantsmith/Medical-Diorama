"""
monitor/process.py - Patient monitor display process.

This module runs as a separate process (spawned by main.py) and is responsible
for continuously rendering the patient monitor display on the Waveshare 2" LCD
via SPI. It runs at ~30 FPS, reading vital signs from the shared state dict
and pushing rendered frames to the display.

The main loop:
  1. Read current HR, SpO2, and alarm state from shared state
  2. Check if vitals have crossed alarm thresholds (auto-trigger alarms)
  3. Render a frame using the MonitorRenderer
  4. Push the frame to the SPI display
  5. Sleep for the remainder of the frame time budget
"""

import time
import logging

from config import MONITOR_TARGET_FPS, ALARM_THRESHOLDS

logger = logging.getLogger(__name__)


def run(state, shutdown_event, mock_hardware=False):
    """
    Main entry point for the patient monitor process.

    This function runs in its own process and does not return until
    the shutdown_event is set (triggered by main.py on SIGINT/SIGTERM).

    Args:
        state: A multiprocessing Manager dict with shared application state.
        shutdown_event: A multiprocessing.Event that signals shutdown.
        mock_hardware: If True, use MockSPIDisplay instead of real hardware.
    """
    # Import display and renderer here (inside the process) because
    # the SPI hardware should only be initialized in this process.
    from monitor.renderer import MonitorRenderer

    if mock_hardware:
        from monitor.spi_display import MockSPIDisplay as DisplayClass
    else:
        from monitor.spi_display import SPIDisplay as DisplayClass

    # Initialize display hardware and renderer
    try:
        display = DisplayClass()
        renderer = MonitorRenderer()
    except Exception as e:
        logger.error("Failed to initialize patient monitor: %s", e)
        state["monitor_running"] = False
        return

    # Mark the monitor as running in shared state
    state["monitor_running"] = True
    logger.info("Patient monitor process started (target %d FPS)", MONITOR_TARGET_FPS)

    # Time tracking for smooth animation
    time_offset = 0.0                            # Waveform scroll position
    frame_time = 1.0 / MONITOR_TARGET_FPS        # Target time per frame
    fps_counter = 0                               # Frames since last FPS update
    fps_timer = time.time()                       # When we last updated the FPS counter

    try:
        # === Main render loop ===
        while not shutdown_event.is_set():
            frame_start = time.time()

            # --- Step 1: Read current state ---
            hr = state.get("monitor_hr", 72)
            spo2 = state.get("monitor_spo2", 98)
            current_alarm = state.get("monitor_alarm", None)

            # --- Step 2: Auto-check alarm thresholds ---
            # If no alarm is manually set, check if vitals have crossed thresholds
            new_alarm = _check_alarm_thresholds(hr, spo2, current_alarm)
            if new_alarm != current_alarm:
                state["monitor_alarm"] = new_alarm

            # --- Step 3: Build a state snapshot for the renderer ---
            # We pass a plain dict (not the Manager proxy) to avoid repeated
            # proxy lookups during rendering, which would be slow.
            state_snapshot = {
                "monitor_hr": hr,
                "monitor_spo2": spo2,
                "monitor_alarm": new_alarm,
            }

            # --- Step 4: Render the frame ---
            frame = renderer.render_frame(state_snapshot, time_offset)

            # --- Step 5: Push frame to the display ---
            display.show(frame)

            # --- Step 6: Advance the waveform scroll position ---
            time_offset += frame_time

            # --- Step 7: Update FPS counter ---
            fps_counter += 1
            now = time.time()
            if now - fps_timer >= 1.0:
                # Update the reported FPS in shared state once per second
                state["monitor_fps"] = fps_counter
                fps_counter = 0
                fps_timer = now

            # --- Step 8: Sleep for the remainder of the frame budget ---
            elapsed = time.time() - frame_start
            sleep_time = frame_time - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        logger.info("Patient monitor received keyboard interrupt")
    except Exception as e:
        logger.error("Patient monitor error: %s", e, exc_info=True)
    finally:
        # Clean up hardware resources
        display.cleanup()
        state["monitor_running"] = False
        logger.info("Patient monitor process stopped")


def _check_alarm_thresholds(hr, spo2, current_alarm):
    """
    Check if vital signs have crossed alarm thresholds.

    Auto-triggers alarms when vitals go out of range. If vitals return
    to normal range, the alarm is automatically cleared.

    Args:
        hr: Current heart rate in BPM.
        spo2: Current SpO2 percentage.
        current_alarm: Currently active alarm string or None.

    Returns:
        The alarm string that should be active, or None if all vitals are normal.
    """
    # Check each threshold in priority order (most critical first)
    if hr >= ALARM_THRESHOLDS["hr_high"]:
        return "hr_high"
    elif hr <= ALARM_THRESHOLDS["hr_low"]:
        return "hr_low"
    elif spo2 <= ALARM_THRESHOLDS["spo2_low"]:
        return "spo2_low"
    else:
        # All vitals are within normal range — clear any auto-triggered alarm
        return None
