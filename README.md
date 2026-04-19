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
