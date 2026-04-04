#!/usr/bin/env python3
"""
main.py - Entry point for the Medical Diorama application.

This script is the single command you run to start everything:
    python main.py                  # Full production mode on Raspberry Pi
    python main.py --mock-hardware  # Development mode without real displays
    python main.py --no-monitor     # Skip the patient monitor process
    python main.py --no-xray        # Skip the X-ray viewer process

It creates a shared state (via multiprocessing.Manager), scans for existing
X-ray images, and spawns three child processes:
    1. Patient Monitor  - drives the Waveshare 2" SPI display
    2. X-Ray Viewer     - drives the 4" HDMI touchscreen via pygame
    3. Web Portal       - Flask server on port 5000

All three processes communicate through the shared state dict.
Press Ctrl+C to gracefully shut down all processes.
"""

import argparse
import logging
import multiprocessing
import os
import signal
import sys
import time

# Add the project root to the Python path so all imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import XRAY_DIR
from shared.state import create_state, scan_xray_images


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Medical Diorama - Raspberry Pi display controller"
    )
    parser.add_argument(
        "--mock-hardware",
        action="store_true",
        help="Use mock display drivers (for development without Pi hardware)",
    )
    parser.add_argument(
        "--no-monitor",
        action="store_true",
        help="Don't start the patient monitor display process",
    )
    parser.add_argument(
        "--no-xray",
        action="store_true",
        help="Don't start the X-ray viewer display process",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable Flask debug mode for the web portal",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set the logging level (default: INFO)",
    )
    return parser.parse_args()


def setup_logging(level_name):
    """
    Configure logging for all processes.

    Each log message includes the process name so you can tell which
    process (Monitor, XRay, Web) generated it.
    """
    level = getattr(logging, level_name)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(processName)s] %(name)s %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main():
    """
    Main function: set up shared state, spawn processes, and wait for shutdown.
    """
    args = parse_args()
    setup_logging(args.log_level)
    logger = logging.getLogger("main")

    logger.info("=" * 60)
    logger.info("  Medical Diorama starting up")
    logger.info("=" * 60)

    if args.mock_hardware:
        logger.info("Running in MOCK HARDWARE mode (no real displays)")
        # Also set the environment variable so config.py picks it up
        os.environ["DIORAMA_DEV"] = "1"

    # =========================================================================
    # Step 1: Create the shared state via multiprocessing.Manager
    # =========================================================================
    # The Manager runs a background server process that provides a proxy dict.
    # All child processes get a reference to this same dict and can read/write
    # it safely across process boundaries.
    logger.info("Creating shared state manager...")
    manager = multiprocessing.Manager()
    state = create_state(manager)

    # =========================================================================
    # Step 2: Scan for existing X-ray images
    # =========================================================================
    os.makedirs(XRAY_DIR, exist_ok=True)
    scan_xray_images(state)
    image_count = len(list(state.get("xray_images", [])))
    logger.info("Found %d X-ray image(s) in %s", image_count, XRAY_DIR)

    # =========================================================================
    # Step 3: Create the shutdown event
    # =========================================================================
    # This event is shared across all processes. When set, each process's
    # main loop will exit gracefully.
    shutdown_event = multiprocessing.Event()

    # =========================================================================
    # Step 4: Spawn child processes
    # =========================================================================
    processes = []

    # --- Patient Monitor Process ---
    if not args.no_monitor:
        from monitor.process import run as monitor_run
        monitor_proc = multiprocessing.Process(
            target=monitor_run,
            args=(state, shutdown_event, args.mock_hardware),
            name="Monitor",
            daemon=True,
        )
        processes.append(("Monitor", monitor_proc))
    else:
        logger.info("Patient monitor process SKIPPED (--no-monitor)")

    # --- X-Ray Viewer Process ---
    if not args.no_xray:
        from xray.process import run as xray_run
        xray_proc = multiprocessing.Process(
            target=xray_run,
            args=(state, shutdown_event, args.mock_hardware),
            name="XRay",
            daemon=True,
        )
        processes.append(("XRay", xray_proc))
    else:
        logger.info("X-ray viewer process SKIPPED (--no-xray)")

    # --- Web Portal Process ---
    from web.app import run_server as web_run
    web_proc = multiprocessing.Process(
        target=web_run,
        args=(state, shutdown_event, args.debug),
        name="Web",
        daemon=True,
    )
    processes.append(("Web", web_proc))

    # Start all processes
    for name, proc in processes:
        proc.start()
        logger.info("Started %s process (PID %d)", name, proc.pid)

    logger.info("-" * 60)
    logger.info("  All processes running!")
    logger.info("  Web portal: http://0.0.0.0:5000")
    logger.info("  Press Ctrl+C to shut down")
    logger.info("-" * 60)

    # =========================================================================
    # Step 5: Wait for shutdown signal
    # =========================================================================
    # Register signal handlers so Ctrl+C and kill signals trigger graceful shutdown
    def signal_handler(signum, frame):
        logger.info("Received signal %d, shutting down...", signum)
        shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Wait until the shutdown event is set (by signal handler or child crash)
    try:
        while not shutdown_event.is_set():
            # Check if any process has died unexpectedly
            for name, proc in processes:
                if not proc.is_alive() and not shutdown_event.is_set():
                    logger.warning("%s process died unexpectedly!", name)
                    # Don't shut down everything — the other processes can continue
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        shutdown_event.set()

    # =========================================================================
    # Step 6: Graceful shutdown
    # =========================================================================
    logger.info("Shutting down all processes...")
    shutdown_event.set()

    # Give processes time to clean up (5 second timeout)
    for name, proc in processes:
        proc.join(timeout=5)
        if proc.is_alive():
            logger.warning("%s process didn't stop in time, terminating", name)
            proc.terminate()
            proc.join(timeout=2)

    # Shut down the Manager
    try:
        manager.shutdown()
    except Exception:
        pass

    logger.info("Medical Diorama shut down complete. Goodbye!")


if __name__ == "__main__":
    # Use 'spawn' start method for multiprocessing (required on some platforms
    # and recommended on Pi 5 for compatibility with pygame and SPI)
    multiprocessing.set_start_method("spawn", force=True)
    main()
