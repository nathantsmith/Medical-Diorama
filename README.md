# Medical-Diorama

Medical Diorama runs three operator-facing subsystems on a Raspberry Pi:
- a SPI patient monitor display
- two HDMI X-ray displays
- a web dashboard for control, uploads, and status

## Raspberry Pi pinout

The patient monitor uses Raspberry Pi SPI0 plus three GPIO control pins. The
physical ransomware trigger uses one GPIO input with the software pull-down
enabled.

| Function | Pi signal | BCM GPIO | Physical pin | Connects to |
|---|---|---:|---:|---|
| SPI data | SPI0 MOSI | `GPIO10` | `19` | LCD `MOSI` / `SDA` |
| SPI clock | SPI0 SCLK | `GPIO11` | `23` | LCD `SCLK` / `SCL` |
| SPI chip select | SPI0 CE0 | `GPIO8` | `24` | LCD `CS` |
| LCD data/command | GPIO | `GPIO25` | `22` | LCD `DC` |
| LCD reset | GPIO | `GPIO22` | `15` | LCD `RST` |
| LCD backlight | GPIO | `GPIO24` | `18` | LCD `BL` |
| Ransomware trigger | GPIO input | `GPIO23` | `16` | Trigger signal, active high |
| Ground | GND | n/a | e.g. `6` | LCD/trigger ground |
| LCD power | 3V3 or 5V | n/a | `1`/`17` or `2`/`4` | LCD `VCC`, per display board |

HDMI mapping:
- `xray1`: HDMI port nearest the Pi 5 USB-C power connector
- `xray2`: the other HDMI port

See [docs/WIRING_DIAGRAM.md](docs/WIRING_DIAGRAM.md) for the full wiring notes
and diagrams.

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
- patches and installs `medical-diorama.service` for the current Linux user,
  install directory, and user runtime directory
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

The systemd unit waits up to 60 seconds for the Pi user's Wayland socket before
starting the app. This keeps the pygame X-ray display processes from starting
before the desktop session is ready during boot.

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
transform = 90

[output:HDMI-A-2]
transform = 90
```

Apply without logging out:

```bash
WAYLAND_DISPLAY=wayland-1 XDG_RUNTIME_DIR=/run/user/$(id -u) \
  wlr-randr --output HDMI-A-1 --transform 90
```

Use `270` instead of `90` if the rotation direction is wrong for how the
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
- `XDG_RUNTIME_DIR`
- `EnvironmentFile`
- `ExecStart`

For most Raspberry Pi OS Bookworm / Wayfire installs, leave `WAYLAND_DISPLAY`
unset so the app can discover the active `wayland-*` socket under
`XDG_RUNTIME_DIR`. Set it manually only if the app selects the wrong desktop
session.
