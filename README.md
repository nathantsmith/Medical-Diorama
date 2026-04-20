# Medical-Diorama

## HDMI display orientation

The X-ray panels are physically landscape but report a portrait native mode
(480×800). Rotation is handled at the compositor level (Wayfire) so pygame
just sees a landscape surface.

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
panel is mounted. Check current state with `wlr-randr` (same env vars).

## systemd startup

A repo-local unit file is checked in at
`deploy/systemd/medical-diorama.service`. It starts the app from the
project `.venv`, uses the repo as `WorkingDirectory`, and loads `.env`
automatically if present.

Install it as a system service:

```bash
sudo cp /home/bhv/Medical-Diorama/deploy/systemd/medical-diorama.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now medical-diorama.service
```

Useful commands:

```bash
sudo systemctl status medical-diorama.service
sudo journalctl -u medical-diorama.service -f
sudo systemctl restart medical-diorama.service
```

If you move the repo or run it as a different Linux user, update `User`,
`Group`, `WorkingDirectory`, `EnvironmentFile`, and `ExecStart` in the unit
before installing it.

If the X-ray windows need the desktop session's Wayland or X11 environment,
uncomment the example `Environment=` lines in the unit and adjust them for
the Pi user session.
