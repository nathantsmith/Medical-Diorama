# Wiring Diagram

This document describes the hardware wiring implied by the current repo
configuration.

Source of truth:
- [config.py](/home/bhv/Medical-Diorama/config.py:9)
- [monitor/spi_display.py](/home/bhv/Medical-Diorama/monitor/spi_display.py:1)
- [ransomware_gpio.py](/home/bhv/Medical-Diorama/ransomware_gpio.py:1)
- [README.md](/home/bhv/Medical-Diorama/README.md:3)

## System Overview

The project uses:
- 1 SPI patient monitor display on Raspberry Pi SPI0
- 2 HDMI X-ray displays on the Pi 5 HDMI outputs
- 1 GPIO input on BCM 23 for the physical ransomware trigger

```text
                         Medical Diorama Hardware

                   +----------------------------------+
                   |         Raspberry Pi 5           |
                   |                                  |
                   | SPI0 MOSI  GPIO10  ------------+ | 
                   | SPI0 SCLK  GPIO11  ----------+ | |
                   | SPI0 CE0   GPIO8   --------+ | | |
                   | DC         GPIO25  ------+ | | | |
                   | RST        GPIO22  ----+ | | | | |
                   | BL         GPIO24  --+ | | | | | |
                   | GND                    | | | | | |
                   | 3V3 / 5V               | | | | | |
                   +------------------------|-|-|-|-|-+
                                            | | | | |
                                            | | | | +----> SPI Monitor Backlight
                                            | | | +------> SPI Monitor Reset
                                            | | +--------> SPI Monitor DC
                                            | +----------> SPI Monitor CS
                                            +------------> SPI Monitor SPI bus

                   +----------------------------------+
                   |    BCM23 GPIO input trigger      |
                   |    with pull-down enabled        |
                   +------------------+---------------+
                                      |
                                      +----> physical trigger switch / signal

                   HDMI port nearest USB-C power  ----> X-ray display 1
                   Other HDMI port                ----> X-ray display 2
```

## Patient Monitor SPI Display

The patient monitor is a Seengreat 2" ST7789V SPI LCD.

Repo-defined signal mapping:

| Display Signal | Pi Function | BCM GPIO | Physical Pin |
|---|---|---:|---:|
| `MOSI` | SPI0 MOSI | `GPIO10` | `19` |
| `SCLK` | SPI0 SCLK | `GPIO11` | `23` |
| `CS` | SPI0 CE0 | `GPIO8` | `24` |
| `DC` | Data/Command | `GPIO25` | `22` |
| `RST` | Reset | `GPIO22` | `15` |
| `BL` | Backlight | `GPIO24` | `18` |
| `GND` | Ground | any GND | e.g. `6` |
| `VCC` | Display power | board-dependent | `3V3` or `5V` |

Notes:
- The code uses `SPI_PORT = 0` and `SPI_CS = 0`, so the display is wired to `spidev0.0`.
- Control pins come from [config.py](/home/bhv/Medical-Diorama/config.py:15).
- SPI signal mapping comes from [monitor/spi_display.py](/home/bhv/Medical-Diorama/monitor/spi_display.py:10).
- The app renders the monitor in landscape at `320x240`.

### ASCII Header View

```text
Raspberry Pi 40-pin header connection for SPI monitor

Pi pin   BCM      Connects to
------   ----     ----------------
19       GPIO10   LCD MOSI / SDA
23       GPIO11   LCD SCLK / SCL
24       GPIO8    LCD CS
22       GPIO25   LCD DC
15       GPIO22   LCD RST
18       GPIO24   LCD BL
6        GND      LCD GND
1 or 17  3V3      LCD VCC if 3.3V board
2 or 4   5V       LCD VCC if 5V board
```

Important:
- Confirm the display module's power requirement before wiring `VCC`.
- The repo does not override the module's hardware power design; only the
  signal pins are explicit in code.

## Ransomware Trigger Input

The physical trigger input uses:

| Function | BCM GPIO | Physical Pin |
|---|---:|---:|
| `RANSOMWARE_GPIO_PIN` | `GPIO23` | `16` |

Behavior from code:
- Configured as an input with `PULL_DOWN`
- Edge detection on both rising and falling edges
- Interpreted as asserted when the line goes `HIGH`

Practical wiring:
- One side of a momentary or maintained switch can drive `GPIO23`
- The signal should be pulled high to assert
- Ground reference must be shared with the Pi

Minimal example:

```text
3V3 ---- switch ---- GPIO23
GND ---------------- common ground
```

Because the software enables an internal pull-down, the line rests low until
the switch drives it high.

## HDMI X-ray Displays

The X-ray viewer uses two HDMI outputs:

| App Display | Physical Port |
|---|---|
| `xray1` | HDMI port nearest the Pi 5 USB-C power connector |
| `xray2` | The other HDMI port |

This mapping comes from [config.py](/home/bhv/Medical-Diorama/config.py:41).

Orientation details from [README.md](/home/bhv/Medical-Diorama/README.md:3):
- The panels physically run in landscape
- Native reported mode is portrait `480x800`
- Wayfire rotates them so pygame sees a landscape surface
- Effective app-facing resolution is `480x320`

### HDMI Layout

```text
Pi 5 rear/side HDMI layout

[ USB-C power ] [ HDMI nearest power ] [ other HDMI ]
                    |                        |
                    +--> xray1              +--> xray2
```

## Recommended Checklist

Before power-on:
- Enable SPI on the Pi
- Confirm the SPI monitor `VCC` voltage requirement
- Confirm the monitor is on `SPI0 CE0`, not `CE1`
- Confirm the trigger line is on `GPIO23`
- Confirm `xray1` is connected to the HDMI port nearest USB-C power
- Confirm `xray2` is connected to the other HDMI port

After boot:
- Verify the SPI monitor initializes
- Verify both HDMI panels appear with the expected Wayfire rotation
- Verify the trigger changes state when `GPIO23` is driven high
