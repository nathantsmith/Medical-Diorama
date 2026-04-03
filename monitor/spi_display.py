"""
monitor/spi_display.py - Hardware abstraction for the ST7789V SPI display.

Provides two classes:
  - SPIDisplay: Drives the real Waveshare 2" LCD via SPI using the st7789 library.
  - MockSPIDisplay: A fake display for development on non-Pi machines. Saves frames
    to a file or prints a status message instead of talking to real hardware.

Usage:
    display = SPIDisplay()      # On Raspberry Pi with real hardware
    display = MockSPIDisplay()  # On a dev machine for testing
    display.show(pil_image)     # Push a 240x320 PIL Image to the screen
    display.cleanup()           # Release hardware resources
"""

import logging

from config import (
    SPI_PORT, SPI_CS, SPI_DC_PIN, SPI_RST_PIN, SPI_BL_PIN,
    SPI_SPEED_HZ, MONITOR_WIDTH, MONITOR_HEIGHT, MONITOR_ROTATION,
)

logger = logging.getLogger(__name__)


class SPIDisplay:
    """
    Real ST7789V display driver using the Pimoroni st7789 Python library.

    This class initializes the SPI bus and display, and provides a simple
    interface to push PIL Image frames to the screen.
    """

    def __init__(self):
        """Initialize the ST7789V display over SPI."""
        try:
            import st7789 as st7789_lib

            # Create the display instance with our pin configuration.
            # The st7789 library handles all the low-level SPI setup.
            self._display = st7789_lib.ST7789(
                port=SPI_PORT,
                cs=SPI_CS,
                dc=SPI_DC_PIN,
                rst=SPI_RST_PIN,
                backlight=SPI_BL_PIN,
                width=MONITOR_WIDTH,
                height=MONITOR_HEIGHT,
                rotation=MONITOR_ROTATION,
                spi_speed_hz=SPI_SPEED_HZ,
            )

            # Turn on the backlight so we can see the display
            self._display.begin()
            logger.info(
                "ST7789V display initialized: %dx%d @ %d Hz SPI",
                MONITOR_WIDTH, MONITOR_HEIGHT, SPI_SPEED_HZ
            )

        except ImportError:
            raise RuntimeError(
                "The 'st7789' library is not installed. "
                "Install it with: pip install st7789\n"
                "Or use MockSPIDisplay for development without hardware."
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to initialize ST7789V display: {e}\n"
                "Check your wiring and pin assignments in config.py."
            )

    def show(self, image):
        """
        Push a PIL Image to the display.

        The image should be a 240x320 RGB PIL Image. The st7789 library
        handles the conversion from RGB888 to the display's native RGB565
        format internally.

        Args:
            image: A PIL.Image.Image in RGB mode, sized MONITOR_WIDTH x MONITOR_HEIGHT.
        """
        self._display.display(image)

    def backlight(self, on):
        """
        Turn the display backlight on or off.

        Args:
            on: True to turn backlight on, False to turn it off.
        """
        if on:
            self._display.set_backlight(True)
        else:
            self._display.set_backlight(False)

    def cleanup(self):
        """Turn off the backlight and release SPI resources."""
        try:
            self._display.set_backlight(False)
        except Exception:
            pass
        logger.info("ST7789V display cleaned up")


class MockSPIDisplay:
    """
    Mock display for development and testing without real hardware.

    Instead of pushing frames to an SPI display, this class optionally
    saves the most recent frame to a temp file for visual inspection,
    and logs frame updates to the console.
    """

    def __init__(self):
        """Initialize the mock display."""
        self._frame_count = 0
        logger.info(
            "MockSPIDisplay initialized (no real hardware). "
            "Frames will be logged, not displayed."
        )

    def show(self, image):
        """
        Accept a PIL Image frame (does not display it on real hardware).

        Every 100 frames, saves the image to /tmp/monitor_frame.png
        so you can visually inspect what the monitor would look like.

        Args:
            image: A PIL.Image.Image in RGB mode.
        """
        self._frame_count += 1

        # Save a snapshot every 100 frames for visual debugging
        if self._frame_count % 100 == 0:
            try:
                image.save("/tmp/monitor_frame.png")
                logger.debug(
                    "Mock frame #%d saved to /tmp/monitor_frame.png",
                    self._frame_count
                )
            except Exception as e:
                logger.warning("Could not save mock frame: %s", e)

    def backlight(self, on):
        """Mock backlight control (just logs the state)."""
        logger.debug("Mock backlight: %s", "ON" if on else "OFF")

    def cleanup(self):
        """Mock cleanup (nothing to release)."""
        logger.info("MockSPIDisplay cleaned up (frame count: %d)", self._frame_count)
