"""Generate 13 sidebar navigation icons (saved as PNGs in icons/nav/).

One icon per page in the app's sidebar:
  OS, Hardware, Sensors, Network, External IP, Processes, Software,
  Updates, Health, Speed Test, Devices, Diagnostics, Tools

All icons use a single light-gray color (#b0b0b0) that is visible on
the dark sidebar background (#252525) in both normal and checked states.
The checked state is indicated by the blue text + left border accent.

Rendered at 4x (96px) then downsampled to 24px for smooth edges.
Transparent background, 24x24 RGBA.

Run:  python make_nav_icons.py
Output: icons/nav/<key>.png  (24x24 RGBA, transparent background)
"""

from __future__ import annotations

import math
import os

from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
#  Configuration
# ---------------------------------------------------------------------------
SS = 4
CANVAS = 24 * SS    # 96px high-res render canvas
TARGET = 24         # final icon size

# Light gray — visible on dark sidebar in both normal and checked states
COLOR = (176, 176, 176, 255)

ICONS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "icons", "nav"
)

S = CANVAS  # shorthand


def _new() -> Image.Image:
    return Image.new("RGBA", (S, S), (0, 0, 0, 0))


def _save(icon: Image.Image, key: str) -> None:
    small = icon.resize((TARGET, TARGET), Image.LANCZOS)
    os.makedirs(ICONS_DIR, exist_ok=True)
    path = os.path.join(ICONS_DIR, f"{key}.png")
    small.save(path, format="PNG")
    print(f"  {key:14s} -> {path}  ({os.path.getsize(path):,} bytes)")


# ---------------------------------------------------------------------------
#  Icon 1: OS — Windows logo (4 panes)
# ---------------------------------------------------------------------------
def _icon_os() -> Image.Image:
    img = _new()
    d = ImageDraw.Draw(img)
    gap = int(S * 0.06)
    pane_w = (S - gap * 3) // 2
    # 4 squares in a 2x2 grid with a gap
    positions = [
        (gap, gap),                           # top-left
        (gap * 2 + pane_w, gap),               # top-right
        (gap, gap * 2 + pane_w),               # bottom-left
        (gap * 2 + pane_w, gap * 2 + pane_w),  # bottom-right
    ]
    for px, py in positions:
        d.rectangle([px, py, px + pane_w, py + pane_w], fill=COLOR)
    return img


# ---------------------------------------------------------------------------
#  Icon 2: Hardware — CPU chip
# ---------------------------------------------------------------------------
def _icon_hardware() -> Image.Image:
    img = _new()
    d = ImageDraw.Draw(img)
    # Chip body (rounded square)
    m = int(S * 0.22)
    d.rounded_rectangle([m, m, S - m, S - m], radius=int(S * 0.06), fill=COLOR)
    # Inner die (darker — cut out)
    dm = int(S * 0.10)
    d.rounded_rectangle([m + dm, m + dm, S - m - dm, S - m - dm],
                        radius=int(S * 0.03), fill=(0, 0, 0, 0))
    # Pin legs on all 4 sides
    pin_w = int(S * 0.05)
    pin_l = int(S * 0.08)
    for i in range(3):
        t = (i + 1) / 4.0
        cx = m + (S - 2 * m) * t
        cy = m + (S - 2 * m) * t
        d.rectangle([cx - pin_w // 2, m - pin_l, cx + pin_w // 2, m], fill=COLOR)
        d.rectangle([cx - pin_w // 2, S - m, cx + pin_w // 2, S - m + pin_l], fill=COLOR)
        d.rectangle([m - pin_l, cy - pin_w // 2, m, cy + pin_w // 2], fill=COLOR)
        d.rectangle([S - m, cy - pin_w // 2, S - m + pin_l, cy + pin_w // 2], fill=COLOR)
    return img


# ---------------------------------------------------------------------------
#  Icon 3: Sensors — thermometer
# ---------------------------------------------------------------------------
def _icon_sensors() -> Image.Image:
    img = _new()
    d = ImageDraw.Draw(img)
    # Tube (vertical rounded rectangle, top half)
    tw = int(S * 0.16)
    tx = S // 2 - tw // 2
    ty0 = int(S * 0.12)
    ty1 = int(S * 0.62)
    d.rounded_rectangle([tx, ty0, tx + tw, ty1], radius=tw // 2, fill=COLOR)
    # Bulb (circle at bottom)
    br = int(S * 0.16)
    bx = S // 2
    by = int(S * 0.72)
    d.ellipse([bx - br, by - br, bx + br, by + br], fill=COLOR)
    # Cut out the tube interior (make it look like an outline)
    inner_w = max(2, tw - int(S * 0.06))
    ix = S // 2 - inner_w // 2
    d.rounded_rectangle([ix, ty0 + int(S * 0.04), ix + inner_w, by],
                        radius=inner_w // 2, fill=(0, 0, 0, 0))
    # Mercury fill inside the bulb (solid)
    mr = max(2, br - int(S * 0.04))
    d.ellipse([bx - mr, by - mr + int(S * 0.02), bx + mr, by + mr + int(S * 0.02)],
              fill=COLOR)
    return img


# ---------------------------------------------------------------------------
#  Icon 4: Network — connected nodes
# ---------------------------------------------------------------------------
def _icon_network() -> Image.Image:
    img = _new()
    d = ImageDraw.Draw(img)
    lw = max(2, int(S * 0.05))
    # Central node
    cx, cy = S // 2, S // 2
    cr = int(S * 0.10)
    # 4 outer nodes
    nodes = [
        (int(S * 0.18), int(S * 0.18)),  # top-left
        (int(S * 0.82), int(S * 0.18)),  # top-right
        (int(S * 0.18), int(S * 0.82)),  # bottom-left
        (int(S * 0.82), int(S * 0.82)),  # bottom-right
    ]
    nr = int(S * 0.09)
    # Lines from center to each node
    for nx, ny in nodes:
        d.line([(cx, cy), (nx, ny)], fill=COLOR, width=lw)
    # Draw nodes (circles) on top of lines
    for nx, ny in nodes:
        d.ellipse([nx - nr, ny - nr, nx + nr, ny + nr], fill=COLOR)
    d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=COLOR)
    return img


# ---------------------------------------------------------------------------
#  Icon 5: External IP — globe
# ---------------------------------------------------------------------------
def _icon_external_ip() -> Image.Image:
    img = _new()
    d = ImageDraw.Draw(img)
    lw = max(2, int(S * 0.05))
    # Outer circle (globe outline)
    r = int(S * 0.38)
    cx = cy = S // 2
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=COLOR, width=lw)
    # Vertical meridian (ellipse)
    d.ellipse([cx - r // 3, cy - r, cx + r // 3, cy + r], outline=COLOR, width=lw)
    # Horizontal parallels
    for offset in [r * 0.45, -r * 0.45]:
        y = cy + int(offset)
        half_w = int(math.sqrt(max(0, r * r - offset * offset)))
        d.line([(cx - half_w, y), (cx + half_w, y)], fill=COLOR, width=lw)
    # Center equator (full width)
    d.line([(cx - r, cy), (cx + r, cy)], fill=COLOR, width=lw)
    return img


# ---------------------------------------------------------------------------
#  Icon 6: Processes — list with lines
# ---------------------------------------------------------------------------
def _icon_processes() -> Image.Image:
    img = _new()
    d = ImageDraw.Draw(img)
    sq = int(S * 0.10)
    line_w = max(2, int(S * 0.045))
    line_h = int(S * 0.04)
    y0 = int(S * 0.18)
    gap = int(S * 0.20)
    line_len = int(S * 0.45)
    for i in range(3):
        y = y0 + i * gap
        # Small square bullet
        d.rectangle([int(S * 0.14), y, int(S * 0.14) + sq, y + sq], fill=COLOR)
        # Line (text placeholder)
        d.rectangle([int(S * 0.14) + sq + int(S * 0.06), y + sq // 2 - line_h // 2,
                      int(S * 0.14) + sq + int(S * 0.06) + line_len, y + sq // 2 + line_h // 2 + 1],
                     fill=COLOR)
    return img


# ---------------------------------------------------------------------------
#  Icon 7: Software — box/package
# ---------------------------------------------------------------------------
def _icon_software() -> Image.Image:
    img = _new()
    d = ImageDraw.Draw(img)
    # Box body
    bx0, by0 = int(S * 0.20), int(S * 0.30)
    bx1, by1 = int(S * 0.80), int(S * 0.82)
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=int(S * 0.03), fill=COLOR)
    # Lid (top rectangle)
    lid_h = int(S * 0.12)
    d.rounded_rectangle([bx0, by0 - lid_h, bx1, by0 + lid_h // 2],
                        radius=int(S * 0.02), fill=COLOR)
    # Vertical tape line down the middle
    tw = int(S * 0.06)
    cx = S // 2
    d.rectangle([cx - tw // 2, by0 - lid_h, cx + tw // 2, by1], fill=COLOR)
    # Cut out box interior to make it look hollow
    d.rounded_rectangle([bx0 + int(S * 0.06), by0 + lid_h // 2 + int(S * 0.02),
                         bx1 - int(S * 0.06), by1 - int(S * 0.06)],
                        radius=int(S * 0.02), fill=(0, 0, 0, 0))
    return img


# ---------------------------------------------------------------------------
#  Icon 8: Updates — download arrow into tray
# ---------------------------------------------------------------------------
def _icon_updates() -> Image.Image:
    img = _new()
    d = ImageDraw.Draw(img)
    lw = max(2, int(S * 0.07))
    # Arrow shaft (vertical line)
    cx = S // 2
    shaft_top = int(S * 0.18)
    shaft_bot = int(S * 0.58)
    d.line([(cx, shaft_top), (cx, shaft_bot)], fill=COLOR, width=lw)
    # Arrowhead (two diagonal lines)
    ah = int(S * 0.16)
    d.line([(cx - ah, shaft_bot - ah), (cx, shaft_bot)], fill=COLOR, width=lw)
    d.line([(cx + ah, shaft_bot - ah), (cx, shaft_bot)], fill=COLOR, width=lw)
    # Tray (horizontal bar at bottom)
    tray_y = int(S * 0.74)
    tray_w = int(S * 0.50)
    d.line([(cx - tray_w // 2, tray_y), (cx + tray_w // 2, tray_y)], fill=COLOR, width=lw)
    # Tray sides (short verticals)
    ts = int(S * 0.10)
    d.line([(cx - tray_w // 2, tray_y), (cx - tray_w // 2, tray_y + ts)], fill=COLOR, width=lw)
    d.line([(cx + tray_w // 2, tray_y), (cx + tray_w // 2, tray_y + ts)], fill=COLOR, width=lw)
    return img


# ---------------------------------------------------------------------------
#  Icon 9: Health — shield with checkmark
# ---------------------------------------------------------------------------
def _icon_health() -> Image.Image:
    img = _new()
    d = ImageDraw.Draw(img)
    # Shield outline (polygon)
    cx = S // 2
    top = int(S * 0.14)
    mid = int(S * 0.50)
    bot = int(S * 0.86)
    half_w = int(S * 0.32)
    # Shield shape: top corners -> sides -> pointed bottom
    shield = [
        (cx, top),                           # top center
        (cx + half_w, top + int(S * 0.06)),  # top-right
        (cx + half_w, mid),                   # right mid
        (cx, bot),                            # bottom point
        (cx - half_w, mid),                   # left mid
        (cx - half_w, top + int(S * 0.06)),  # top-left
    ]
    d.polygon(shield, fill=COLOR)
    # Cut out interior (make it an outline)
    inset = int(S * 0.06)
    inner = [(p[0], p[1] + (inset if i in (0,) else 0)) for i, p in enumerate(shield)]
    # Simpler: just scale the shield inward
    d.polygon([
        (cx, top + inset),
        (cx + half_w - inset, top + int(S * 0.06) + inset),
        (cx + half_w - inset, mid),
        (cx, bot - inset),
        (cx - half_w + inset, mid),
        (cx - half_w + inset, top + int(S * 0.06) + inset),
    ], fill=(0, 0, 0, 0))
    # Checkmark inside
    clw = max(2, int(S * 0.06))
    cm_y = int(S * 0.52)
    d.line([(cx - int(S * 0.12), cm_y), (cx - int(S * 0.03), cm_y + int(S * 0.10))],
           fill=COLOR, width=clw)
    d.line([(cx - int(S * 0.03), cm_y + int(S * 0.10)), (cx + int(S * 0.14), cm_y - int(S * 0.10))],
           fill=COLOR, width=clw)
    return img


# ---------------------------------------------------------------------------
#  Icon 10: Speed Test — speedometer/gauge
# ---------------------------------------------------------------------------
def _icon_speed_test() -> Image.Image:
    img = _new()
    d = ImageDraw.Draw(img)
    lw = max(2, int(S * 0.05))
    cx = S // 2
    cy = int(S * 0.72)
    r = int(S * 0.32)
    # Arc (semicircle) — draw as pie, then cut bottom half
    d.pieslice([cx - r, cy - r, cx + r, cy + r], 180, 360, fill=COLOR)
    # Cut out inner semicircle to make it an arc
    ir = r - lw
    d.pieslice([cx - ir, cy - ir, cx + ir, cy + ir], 180, 360, fill=(0, 0, 0, 0))
    # Needle (line from center to upper-right)
    angle = math.radians(-45)  # 45 degrees from vertical
    nx = cx + int(r * 0.65 * math.sin(angle))
    ny = cy + int(r * 0.65 * math.cos(angle))
    d.line([(cx, cy), (nx, ny)], fill=COLOR, width=lw + 1)
    # Center pivot dot
    pr = int(S * 0.05)
    d.ellipse([cx - pr, cy - pr, cx + pr, cy + pr], fill=COLOR)
    return img


# ---------------------------------------------------------------------------
#  Icon 11: Devices — USB connector
# ---------------------------------------------------------------------------
def _icon_devices() -> Image.Image:
    img = _new()
    d = ImageDraw.Draw(img)
    # USB plug body (rectangle at top)
    pw = int(S * 0.36)
    ph = int(S * 0.22)
    px = S // 2 - pw // 2
    py = int(S * 0.12)
    d.rounded_rectangle([px, py, px + pw, py + ph], radius=int(S * 0.02), fill=COLOR)
    # USB symbol: line going down from plug
    lw = max(2, int(S * 0.06))
    cx = S // 2
    ly0 = py + ph
    ly1 = int(S * 0.58)
    d.line([(cx, ly0), (cx, ly1)], fill=COLOR, width=lw)
    # Branch left (circle)
    bl_y = int(S * 0.42)
    d.line([(cx, bl_y), (cx - int(S * 0.20), bl_y)], fill=COLOR, width=lw)
    lr = int(S * 0.07)
    lx = cx - int(S * 0.20)
    d.ellipse([lx - lr, bl_y - lr, lx + lr, bl_y + lr], fill=COLOR)
    # Branch right (arrow up)
    d.line([(cx, bl_y), (cx + int(S * 0.20), bl_y)], fill=COLOR, width=lw)
    rx = cx + int(S * 0.20)
    # Small arrow at end of right branch
    d.line([(rx, bl_y), (rx, bl_y - int(S * 0.10))], fill=COLOR, width=lw)
    d.line([(rx - int(S * 0.04), bl_y - int(S * 0.06)),
            (rx, bl_y - int(S * 0.10))], fill=COLOR, width=lw)
    d.line([(rx + int(S * 0.04), bl_y - int(S * 0.06)),
            (rx, bl_y - int(S * 0.10))], fill=COLOR, width=lw)
    # Bottom: square endpoint
    sq = int(S * 0.12)
    d.rounded_rectangle([cx - sq // 2, ly1, cx + sq // 2, ly1 + sq],
                        radius=int(S * 0.02), fill=COLOR)
    return img


# ---------------------------------------------------------------------------
#  Icon 12: Diagnostics — magnifying glass over gear
# ---------------------------------------------------------------------------
def _icon_diagnostics() -> Image.Image:
    img = _new()
    d = ImageDraw.Draw(img)
    lw = max(2, int(S * 0.05))
    # Gear (top-left, small)
    gx, gy = int(S * 0.34), int(S * 0.34)
    gr = int(S * 0.14)
    # Gear body (circle)
    d.ellipse([gx - gr, gy - gr, gx + gr, gy + gr], fill=COLOR)
    # Gear teeth (8 small rectangles around)
    tooth_l = int(S * 0.05)
    tooth_w = int(S * 0.04)
    for i in range(8):
        angle = i * math.pi / 4
        tx = gx + int((gr + tooth_l / 2) * math.cos(angle))
        ty = gy + int((gr + tooth_l / 2) * math.sin(angle))
        d.rectangle([tx - tooth_w, ty - tooth_w, tx + tooth_w, ty + tooth_w], fill=COLOR)
    # Cut out gear center
    cr = int(S * 0.05)
    d.ellipse([gx - cr, gy - cr, gx + cr, gy + cr], fill=(0, 0, 0, 0))

    # Magnifying glass (bottom-right)
    lx, ly = int(S * 0.64), int(S * 0.64)
    lr = int(S * 0.16)
    lt = max(2, int(S * 0.04))
    d.ellipse([lx - lr, ly - lr, lx + lr, ly + lr], fill=COLOR)
    d.ellipse([lx - lr + lt, ly - lr + lt, lx + lr - lt, ly + lr - lt],
              fill=(0, 0, 0, 0))
    # Handle
    hx0, hy0 = lx + int(lr * 0.65), ly + int(lr * 0.65)
    hx1, hy1 = int(S * 0.86), int(S * 0.86)
    d.line([(hx0, hy0), (hx1, hy1)], fill=COLOR, width=lw + 1)
    return img


# ---------------------------------------------------------------------------
#  Icon 13: Tools — wrench
# ---------------------------------------------------------------------------
def _icon_tools() -> Image.Image:
    img = _new()
    d = ImageDraw.Draw(img)
    # Wrench body: thick diagonal bar
    lw = int(S * 0.10)
    # Diagonal from bottom-left to top-right
    d.line([(int(S * 0.22), int(S * 0.78)), (int(S * 0.68), int(S * 0.32))],
           fill=COLOR, width=lw)
    # Jaw (circle at top-right with notch)
    jx, jy = int(S * 0.70), int(S * 0.30)
    jr = int(S * 0.14)
    d.ellipse([jx - jr, jy - jr, jx + jr, jy + jr], fill=COLOR)
    # Notch (cut-out)
    d.ellipse([jx - jr * 0.40, jy - jr * 0.40, jx + jr * 0.40, jy + jr * 0.40],
              fill=(0, 0, 0, 0))
    # Handle end (rounded cap at bottom-left)
    hx, hy = int(S * 0.22), int(S * 0.78)
    hr = int(S * 0.08)
    d.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=COLOR)
    return img


# ---------------------------------------------------------------------------
#  Main
# ---------------------------------------------------------------------------
ICONS = {
    "os":          _icon_os,
    "hardware":    _icon_hardware,
    "sensors":     _icon_sensors,
    "network":     _icon_network,
    "external_ip": _icon_external_ip,
    "processes":   _icon_processes,
    "software":    _icon_software,
    "updates":     _icon_updates,
    "health":      _icon_health,
    "speed_test":  _icon_speed_test,
    "devices":     _icon_devices,
    "diagnostics": _icon_diagnostics,
    "tools":       _icon_tools,
}


def main() -> None:
    print(f"Rendering {len(ICONS)} nav icons at {CANVAS}x{CANVAS} (4x SS)...")
    print(f"Output dir: {ICONS_DIR}")
    for key, fn in ICONS.items():
        hi = fn()
        _save(hi, key)
    print("Done!")


if __name__ == "__main__":
    main()
