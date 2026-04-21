# Medical-Diorama

Medical Diorama runs three operator-facing subsystems on a Raspberry Pi:
- a SPI patient monitor display
- two HDMI X-ray displays
- a web dashboard for control, uploads, and status

## Hardware pinout

Wiring uses **BCM** GPIO numbers in code (`config.py`). The table lists the
**40-pin header** pin numbers on a full-size Raspberry Pi (Pi 4 / Pi 5 style).

Enable **SPI** (`SPI0`, `CE0`) in Raspberry Pi configuration before first boot
with the display attached. Connect the LCD **GND** to any Pi **GND** pin (for
example pin 6). **VCC** must match your module (often 3.3 V on pin 1 or 17, or
5 V on pin 2 or 4—check the display datasheet).

### Patient monitor (SPI, ST7789V)

Uses `spidev0.0` (`SPI_PORT = 0`, `SPI_CS = 0`).

| LCD signal | Pi function | BCM | Physical pin |
|------------|-------------|-----|--------------|
| MOSI / SDA | SPI0 MOSI | GPIO10 | 19 |
| SCLK / SCL | SPI0 SCLK | GPIO11 | 23 |
| CS | SPI0 CE0 | GPIO8 | 24 |
| DC | GPIO out | GPIO25 | 22 |
| RST | GPIO out | GPIO22 | 15 |
| BL (backlight) | GPIO out | GPIO24 | 18 |

### Physical ransomware trigger

Input with internal pull-down in software; assert **high** to trigger.

| Function | BCM | Physical pin |
|----------|-----|--------------|
| `RANSOMWARE_GPIO_PIN` | GPIO23 | 16 |

Typical wiring: **3.3 V → switch → GPIO23**, other side of switch to **GND**
(use a momentary or maintained contact as needed).

### HDMI X-ray displays

No GPIO: use **HDMI-A-1** / **HDMI-A-2** (Wayland names). **xray1** is the HDMI
port closest to the Pi 5 USB-C power input; **xray2** is the other port.

More detail and an ASCII block diagram: [docs/WIRING_DIAGRAM.md](docs/WIRING_DIAGRAM.md).

## Installer script

For repeatable setup on another Pi, use:

```bash
sudo ./deploy/install_pi.sh
```

This script:
- installs OS packages
- adds the install user to likely-required hardware/display groups
- creates `.venv`
- installs `requirements.txt`
- creates `.env` if one does not exist
- patches and installs `medical-diorama.service` for the current Linux user
- enables and starts the service
- appends Wayfire rotation entries if they are not already present

Useful options:

```bash
sudo ./deploy/install_pi.sh --user pi --admin-password 'replace-me'
sudo ./deploy/install_pi.sh --skip-wayfire
sudo ./deploy/install_pi.sh --skip-apt
```

See help for the full option list:

```bash
sudo ./deploy/install_pi.sh --help
```

The installer also adds the chosen Linux user to these groups when present:
- `gpio`
- `spi`
- `video`
- `input`
- `render`
- `i2c`

After install, reboot or log out and back in so those group memberships take effect.

## Access point helper

If you want the Pi to broadcast its own setup/control Wi-Fi network, use the
NetworkManager helper script:

```bash
sudo ./deploy/setup_ap.sh --ssid MedicalDioramaSetup --password 'replace-me'
```

This creates a persistent Wi-Fi hotspot profile on `wlan0` using
NetworkManager and brings it up immediately.

Other useful commands:

```bash
sudo ./deploy/setup_ap.sh --status
sudo ./deploy/setup_ap.sh --stop
sudo ./deploy/setup_ap.sh --delete
```

Notes:
- This helper assumes Raspberry Pi OS with NetworkManager / `nmcli`
- It does not replace normal Wi-Fi client setup unless you bring the AP up
- Use an 8-63 character password

## Booting the system

If `medical-diorama.service` is installed and enabled, the app starts
automatically at boot.

Power-on checklist:
- Connect the SPI monitor
- Connect `xray1` to the HDMI port nearest the Pi 5 USB-C power connector
- Connect `xray2` to the other HDMI port
- Connect network by Ethernet or preconfigured Wi-Fi
- Power on the Pi

After boot, verify the service:

```bash
sudo systemctl status medical-diorama.service
```

Useful service commands:

```bash
sudo systemctl restart medical-diorama.service
sudo journalctl -u medical-diorama.service -f
```

If the service is not installed yet, see `systemd startup` below.

## Connecting to the system

The web app listens on port `5000`.

From another device on the same network, open:

```text
http://<raspberry-pi-ip>:5000
```

To find the Pi IP address locally:

```bash
hostname -I
```

If mDNS is available on your network, this may also work:

```text
http://raspberrypi.local:5000
```

Login credentials come from environment variables:
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`

If no `.env` override exists, the code defaults are:
- username: `admin`
- password: `changeme`

You should replace those defaults before production use.

## Using the interface

The dashboard has three main areas.

### Patient Monitor

Use this panel to control the SPI patient monitor.

Functions:
- Set heart rate with the `Heart Rate` slider
- Set oxygen saturation with the `SpO2` slider
- Click `Apply Vitals` to push the values to the display
- Trigger alarms with `High HR`, `Low HR`, or `Low SpO2`
- Clear alarms with `Clear Alarm`

Status shown:
- monitor running/stopped state
- current FPS
- active alarm

### Ransomware Simulation

Use this panel to control the ransomware overlay behavior.

Functions:
- Toggle dashboard-controlled ransomware mode on or off
- Upload one ransomware image for each target:
  - `Patient Monitor`
  - `X-Ray Display 1`
  - `X-Ray Display 2`
- Remove the currently assigned ransomware image for a target

Notes:
- The image upload/display section is collapsible
- It is collapsed by default
- Its open/closed state is remembered in the browser
- If the physical GPIO trigger is asserted, the source badge will show that

### X-Ray Displays

There is one panel for each HDMI X-ray display.

Functions:
- Upload X-ray images into that display's rotation
- Click an image thumbnail to make it the current image
- Remove images from rotation
- Toggle auto-play on or off
- Change the auto-advance interval and click `Set`

Status shown:
- whether the assigned HDMI output is running
- whether the output is disconnected
- whether ransomware mode is overriding normal slideshow content

## First-boot behavior to verify

After the system comes up, check:
- the SPI monitor is lit and rendering
- both HDMI X-ray screens are active
- the dashboard opens from another device
- the login page appears
- X-ray uploads and interval changes work

If one HDMI screen does not appear immediately, check the service logs:

```bash
sudo journalctl -u medical-diorama.service -f
```

## HDMI display orientation

The X-ray panels are physically landscape but report a portrait native mode
(`480x800`). Rotation is handled at the compositor level (Wayfire) so pygame
sees a landscape surface.

Add to `~/.config/wayfire.ini`:

```ini
[output:HDMI-A-1]
transform = 270

[output:HDMI-A-2]
transform = 270
```

Apply without logging out:

```bash
WAYLAND_DISPLAY=wayland-1 XDG_RUNTIME_DIR=/run/user/$(id -u) \
  wlr-randr --output HDMI-A-1 --transform 270
```

Use `90` or `180` instead of `270` if the rotation is wrong for how the
panel is mounted. Check current state with `wlr-randr` using the same
environment variables.

## systemd startup

A repo-local unit file is checked in at
`deploy/systemd/medical-diorama.service`. It starts the app from the project
`.venv`, uses the repo as `WorkingDirectory`, and loads `.env` automatically
if present.

Install it as a system service:

```bash
sudo cp /home/bhv/Medical-Diorama/deploy/systemd/medical-diorama.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now medical-diorama.service
```

If you move the repo or run it as a different Linux user, update these fields
in the unit before installing it:
- `User`
- `Group`
- `WorkingDirectory`
- `EnvironmentFile`
- `ExecStart`

If the X-ray windows need the desktop session's Wayland or X11 environment,
uncomment the example `Environment=` lines in the unit and adjust them for
the Pi user session.

The installer also deploys a udev-triggered helper that restarts
`medical-diorama.service` when the DRM subsystem reports a display topology
change, so HDMI hotplug events can recover the X-ray windows without a manual
restart.
