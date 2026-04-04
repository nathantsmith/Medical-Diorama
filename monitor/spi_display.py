"""
monitor/spi_display.py - Hardware abstraction for the Seengreat 2" ST7789V SPI display.

Based on the Seengreat demo code (https://github.com/seengreat/2inch-LCD-Display)
but rewritten to use gpiod (Pi 5 compatible) instead of the deprecated wiringpi.

The Seengreat 2" LCD uses:
  - Hardware SPI0 (spidev0.0) for data transfer (MOSI/SCLK/CS)
  - GPIO pins for control signals (DC, RST, BL)
  - ST7789V controller at 240x320 pixels, RGB565 color

Pin mapping (BCM GPIO numbers):
  DC  = GPIO 25 (Data/Command select)
  RST = GPIO 22 (Reset, active low)
  BL  = GPIO 24 (Backlight)
  SPI MOSI = GPIO 10 (SPI0 MOSI, fixed)
  SPI SCLK = GPIO 11 (SPI0 SCLK, fixed)
  SPI CS   = GPIO 8  (SPI0 CE0, fixed)

Provides two classes:
  - SPIDisplay: Drives the real hardware via SPI + GPIO.
  - MockSPIDisplay: Fake display for development on non-Pi machines.

Usage:
    display = SPIDisplay()
    display.show(pil_image)     # Push a 240x320 PIL Image to the screen
    display.cleanup()           # Release hardware resources
"""

import time
import logging
import numpy as np
from PIL import Image

from config import (
    SPI_PORT, SPI_CS, SPI_DC_PIN, SPI_RST_PIN, SPI_BL_PIN,
    SPI_SPEED_HZ, MONITOR_WIDTH, MONITOR_HEIGHT,
)

logger = logging.getLogger(__name__)


class SPIDisplay:
    """
    ST7789V display driver for the Seengreat 2" LCD module.

    Uses spidev for SPI data transfer and gpiod for GPIO control.
    Implements the ST7789V initialization sequence from the Seengreat
    reference code, with manual RGB888→RGB565 conversion via numpy.
    """

    def __init__(self):
        """Initialize the SPI bus, GPIO pins, and ST7789V display."""
        import spidev
        import gpiod

        # --- GPIO Setup ---
        # On Pi 5, the GPIO chip is "/dev/gpiochip4" (not gpiochip0 like Pi 4)
        # gpiod v2 requires the full /dev/ path
        chip_path = None
        for path in ["/dev/gpiochip4", "/dev/gpiochip0"]:
            try:
                self._chip = gpiod.Chip(path)
                chip_path = path
                break
            except (FileNotFoundError, OSError, PermissionError):
                continue

        if chip_path is None:
            raise RuntimeError("Could not open any GPIO chip (tried /dev/gpiochip4, /dev/gpiochip0)")

        logger.info("Using GPIO chip: %s", chip_path)

        # Request the DC, RST, and BL pins as outputs
        # gpiod v2 API (used on Pi 5 with bookworm)
        try:
            # Try gpiod v2 API first
            self._dc_line = self._chip.request_lines(
                consumer="lcd-dc",
                config={SPI_DC_PIN: gpiod.LineSettings(direction=gpiod.line.Direction.OUTPUT)}
            )
            self._rst_line = self._chip.request_lines(
                consumer="lcd-rst",
                config={SPI_RST_PIN: gpiod.LineSettings(direction=gpiod.line.Direction.OUTPUT)}
            )
            self._bl_line = self._chip.request_lines(
                consumer="lcd-bl",
                config={SPI_BL_PIN: gpiod.LineSettings(direction=gpiod.line.Direction.OUTPUT)}
            )
            self._gpiod_v2 = True
            logger.info("Using gpiod v2 API")
        except (AttributeError, TypeError):
            # Fall back to gpiod v1 API
            self._dc_line = self._chip.get_line(SPI_DC_PIN)
            self._dc_line.request(consumer="lcd-dc", type=gpiod.LINE_REQ_DIR_OUT)
            self._rst_line = self._chip.get_line(SPI_RST_PIN)
            self._rst_line.request(consumer="lcd-rst", type=gpiod.LINE_REQ_DIR_OUT)
            self._bl_line = self._chip.get_line(SPI_BL_PIN)
            self._bl_line.request(consumer="lcd-bl", type=gpiod.LINE_REQ_DIR_OUT)
            self._gpiod_v2 = False
            logger.info("Using gpiod v1 API")

        # --- SPI Setup ---
        self._spi = spidev.SpiDev()
        self._spi.open(SPI_PORT, SPI_CS)
        self._spi.max_speed_hz = SPI_SPEED_HZ
        self._spi.mode = 0b00

        # Display dimensions
        self._width = MONITOR_WIDTH    # 240
        self._height = MONITOR_HEIGHT  # 320

        # Turn on the backlight
        self._gpio_write(self._bl_line, SPI_BL_PIN, 1)

        # Initialize the ST7789V controller
        self._lcd_init()

        logger.info(
            "ST7789V display initialized: %dx%d @ %d Hz SPI (DC=%d, RST=%d, BL=%d)",
            self._width, self._height, SPI_SPEED_HZ,
            SPI_DC_PIN, SPI_RST_PIN, SPI_BL_PIN,
        )

    def _gpio_write(self, line, offset, value):
        """
        Write a value (0 or 1) to a GPIO pin.

        Handles both gpiod v1 and v2 APIs.

        Args:
            line: The gpiod line or line request object.
            offset: The BCM GPIO pin number.
            value: 0 (low) or 1 (high).
        """
        if self._gpiod_v2:
            import gpiod
            line.set_value(offset, gpiod.line.Value(value))
        else:
            line.set_value(value)

    def _write_cmd(self, cmd):
        """
        Send a command byte to the ST7789V.

        Sets DC pin LOW (command mode), then sends the byte over SPI.

        Args:
            cmd: Command byte (0x00 - 0xFF).
        """
        self._gpio_write(self._dc_line, SPI_DC_PIN, 0)
        self._spi.writebytes([cmd])

    def _write_data(self, value):
        """
        Send a data byte to the ST7789V.

        Sets DC pin HIGH (data mode), then sends the byte over SPI.

        Args:
            value: Data byte (0x00 - 0xFF).
        """
        self._gpio_write(self._dc_line, SPI_DC_PIN, 1)
        self._spi.writebytes([value])

    def _reset(self):
        """
        Hardware reset the ST7789V display.

        Pulses the RST pin low for 20ms to trigger a reset.
        """
        self._gpio_write(self._rst_line, SPI_RST_PIN, 1)
        time.sleep(0.02)
        self._gpio_write(self._rst_line, SPI_RST_PIN, 0)
        time.sleep(0.02)
        self._gpio_write(self._rst_line, SPI_RST_PIN, 1)
        time.sleep(0.02)

    def _lcd_init(self):
        """
        Initialize the ST7789V controller with the Seengreat register sequence.

        This sets up the display timing, gamma correction, color mode (RGB565),
        and turns on the display. Derived from the Seengreat reference code.
        """
        self._reset()

        self._write_cmd(0x36)     # Memory Access Control (MADCTL)
        self._write_data(0x00)    # Normal orientation

        self._write_cmd(0x3A)     # Interface Pixel Format
        self._write_data(0x05)    # 16-bit color (RGB565)

        self._write_cmd(0x21)     # Display Inversion On

        self._write_cmd(0x2A)     # Column Address Set (X: 0 to 319)
        self._write_data(0x00)
        self._write_data(0x00)
        self._write_data(0x01)
        self._write_data(0x3F)

        self._write_cmd(0x2B)     # Row Address Set (Y: 0 to 239)
        self._write_data(0x00)
        self._write_data(0x00)
        self._write_data(0x00)
        self._write_data(0xEF)

        self._write_cmd(0xB2)     # Porch Control
        self._write_data(0x0C)
        self._write_data(0x0C)
        self._write_data(0x00)
        self._write_data(0x33)
        self._write_data(0x33)

        self._write_cmd(0xB7)     # Gate Control
        self._write_data(0x35)

        self._write_cmd(0xBB)     # VCOMS Setting
        self._write_data(0x1F)

        self._write_cmd(0xC0)     # LCM Control
        self._write_data(0x2C)

        self._write_cmd(0xC2)     # VDV and VRH Command Enable
        self._write_data(0x01)

        self._write_cmd(0xC3)     # VRH Set
        self._write_data(0x12)

        self._write_cmd(0xC4)     # VDV Set
        self._write_data(0x20)

        self._write_cmd(0xC6)     # Frame Rate Control
        self._write_data(0x0F)

        self._write_cmd(0xD0)     # Power Control 1
        self._write_data(0xA4)
        self._write_data(0xA1)

        self._write_cmd(0xE0)     # Positive Voltage Gamma Control
        for val in [0xD0, 0x08, 0x11, 0x08, 0x0C, 0x15,
                     0x39, 0x33, 0x50, 0x36, 0x13, 0x14, 0x29, 0x2D]:
            self._write_data(val)

        self._write_cmd(0xE1)     # Negative Voltage Gamma Control
        for val in [0xD0, 0x08, 0x10, 0x08, 0x06, 0x06,
                     0x39, 0x44, 0x51, 0x0B, 0x16, 0x14, 0x2F, 0x31]:
            self._write_data(val)

        self._write_cmd(0x21)     # Display Inversion On
        self._write_cmd(0x11)     # Sleep Out
        time.sleep(0.12)          # Wait for sleep out to complete
        self._write_cmd(0x29)     # Display On

    def _set_window(self, x0, y0, x1, y1):
        """
        Set the drawing window on the display.

        Args:
            x0, y0: Top-left corner.
            x1, y1: Bottom-right corner (exclusive).
        """
        self._write_cmd(0x2A)     # Column Address Set
        self._write_data(x0 >> 8)
        self._write_data(x0 & 0xFF)
        self._write_data((x1 - 1) >> 8)
        self._write_data((x1 - 1) & 0xFF)

        self._write_cmd(0x2B)     # Row Address Set
        self._write_data(y0 >> 8)
        self._write_data(y0 & 0xFF)
        self._write_data((y1 - 1) >> 8)
        self._write_data((y1 - 1) & 0xFF)

        self._write_cmd(0x2C)     # Memory Write

    def show(self, image):
        """
        Push a PIL Image to the display.

        Accepts a 240x320 RGB PIL Image (portrait). The image is automatically
        transposed and rotated to match the Seengreat display's native landscape
        orientation (320x240), with MADCTL set to 0x70.

        Args:
            image: A PIL.Image.Image in RGB mode, sized 240x320.
        """
        # The Seengreat display expects 320x240 landscape data with MADCTL=0x70.
        # Transpose the 240x320 portrait image: rotate 90° CCW then flip,
        # matching the Seengreat reference which does img.rotate(180) on a
        # (320, 240) source image.
        img = image.transpose(Image.TRANSPOSE).rotate(180).transpose(Image.FLIP_LEFT_RIGHT)

        # Convert PIL image to numpy array for fast RGB565 conversion
        # Shape: (height, width, 3) with values 0-255 for R, G, B
        rgb = np.asarray(img, dtype=np.uint8)

        # Convert RGB888 to RGB565 (16-bit color):
        #   High byte: RRRRRGGG (top 5 bits of R + top 3 bits of G)
        #   Low byte:  GGGBBBBB (bottom 3 bits of G + top 5 bits of B)
        # rgb shape is (height, width, 3) — numpy uses row-major (height first)
        pixel = np.zeros((rgb.shape[0], rgb.shape[1], 2), dtype=np.uint8)
        pixel[..., 0] = np.add(
            np.bitwise_and(rgb[..., 0], 0xF8),
            np.right_shift(rgb[..., 1], 5)
        )
        pixel[..., 1] = np.add(
            np.bitwise_and(np.left_shift(rgb[..., 1], 3), 0xE0),
            np.right_shift(rgb[..., 2], 3)
        )

        # Flatten to a 1D list for SPI transfer
        pixel_data = pixel.flatten().tolist()

        # Set MADCTL for landscape-rotated write (0x70), matching Seengreat code
        self._write_cmd(0x36)
        self._write_data(0x70)

        # Set the drawing window to the full display
        self._set_window(0, 0, self._height, self._width)

        # Send pixel data over SPI in chunks (SPI has a max transfer size)
        self._gpio_write(self._dc_line, SPI_DC_PIN, 1)  # Data mode
        for i in range(0, len(pixel_data), 4096):
            self._spi.writebytes(pixel_data[i:i + 4096])

    def backlight(self, on):
        """
        Turn the display backlight on or off.

        Args:
            on: True for on, False for off.
        """
        self._gpio_write(self._bl_line, SPI_BL_PIN, 1 if on else 0)

    def cleanup(self):
        """Turn off backlight and release SPI/GPIO resources."""
        try:
            self._gpio_write(self._bl_line, SPI_BL_PIN, 0)
        except Exception:
            pass
        try:
            self._spi.close()
        except Exception:
            pass
        try:
            if self._gpiod_v2:
                self._dc_line.release()
                self._rst_line.release()
                self._bl_line.release()
            else:
                self._dc_line.release()
                self._rst_line.release()
                self._bl_line.release()
            self._chip.close()
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
