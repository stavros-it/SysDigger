"""Generate the 4 Tools category icons (saved as PNGs in the icons/ folder).

Categories and their accent colors (matching the QSS in gui.py):
  - System Repair            -> red    (#e07b7b)  wrench + screwdriver crossed
  - Maintenance              -> yellow (#f0c040)  broom sweeping
  - Hardware & Diagnostics   -> blue   (#60cdff)  chip with magnifying glass
  - System Info & Status     -> green  (#5fcf80)  monitor with info "i"

Rendered at 4x (256px) then downsampled to 64px for smooth edges.
Transparent background, single accent color per icon (matching the
category's left-border accent in the GUI).

Run:  python make_category_icons.py
Output: icons/<key>.png  (64x64 RGBA, transparent background)
        icons/<key>_preview.png  (256x256 for easy viewing)
"""

from __future__ import annotations

import math
import os

from PIL import Image, ImageDraw, ImageFilter

# ---------------------------------------------------------------------------
#  Configuration
# ---------------------------------------------------------------------------
SS = 4
CANVAS = 64 * SS              # 256 — high-res render canvas
TARGET = 64                  # final icon size

# Accent colors (must match the QSS for the [cat="..."] selectors in gui.py)
COLORS = {
    "repair":       (224, 123, 123),   # red    #e07b7b
    "maintenance":  (240, 192, 64),    # yellow #f0c040
    "diagnostics":  (96, 205, 255),    # blue   #60cdff
    "status":       (95, 207, 128),    # green  #5fcf80
}

ICONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------
def _new_canvas() -> Image.Image:
    return Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))


def _filled(draw: ImageDraw.ImageDraw, color: tuple, shape) -> None:
    """Draw a filled shape (aliasing-friendly; supersampling smooths it)."""
    draw.draw(shape, "F", color) if hasattr(draw, "draw") else draw.point(shape, fill=color)


def _rounded_polygon(draw: ImageDraw.ImageDraw, points, color,
                     width: int = 0) -> None:
    """Draw a thick rounded line through the given points (a 'stroke').
    width=0 means filled polygon instead."""
    if width == 0:
        draw.polygon(points, fill=color)
    else:
        draw.line(points, fill=color, width=width)


def _save(icon: Image.Image, key: str) -> None:
    """Downsample to TARGET and save .png + a 256px preview."""
    small = icon.resize((TARGET, TARGET), Image.LANCZOS)
    os.makedirs(ICONS_DIR, exist_ok=True)
    path = os.path.join(ICONS_DIR, f"{key}.png")
    small.save(path, format="PNG")
    preview = os.path.join(ICONS_DIR, f"{key}_preview.png")
    icon.save(preview, format="PNG")
    print(f"  {key:14s} -> {path}  ({os.path.getsize(path):,} bytes)")


# ---------------------------------------------------------------------------
#  Icon 1: System Repair — crossed wrench + screwdriver
# ---------------------------------------------------------------------------
def _icon_repair() -> Image.Image:
    color = COLORS["repair"]
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    S = CANVAS
    T = int(S * 0.10)  # stroke thickness

    # Wrench: a thick diagonal bar with an open jaw at the top-left.
    # Drawn as a rotated rectangle.
    def _rotated_bar(cx0, cy0, cx1, cy1, thickness, fill):
        # Endpoints of the bar's centerline
        dx, dy = cx1 - cx0, cy1 - cy0
        length = math.hypot(dx, dy)
        if length == 0:
            return
        angle = math.atan2(dy, dx)
        # Four corners of the rectangle (perpendicular offset)
        nx, ny = -math.sin(angle), math.cos(angle)
        ht = thickness / 2
        p1 = (cx0 + nx * ht, cy0 + ny * ht)
        p2 = (cx0 - nx * ht, cy0 - ny * ht)
        p3 = (cx1 - nx * ht, cy1 - ny * ht)
        p4 = (cx1 + nx * ht, cy1 + ny * ht)
        d.polygon([p1, p2, p3, p4], fill=fill)

    # Wrench body (diagonal from bottom-right to top-left)
    _rotated_bar(S * 0.78, S * 0.78, S * 0.30, S * 0.30, T, color)
    # Wrench jaw (circle at top-left with a notch)
    jx, jy, jr = S * 0.26, S * 0.26, int(S * 0.14)
    d.ellipse([jx - jr, jy - jr, jx + jr, jy + jr], fill=color)
    # Notch (cut-out: draw transparent circle)
    d.ellipse([jx - jr * 0.45, jy - jr * 0.45,
               jx + jr * 0.45, jy + jr * 0.45], fill=(0, 0, 0, 0))

    # Screwdriver body (diagonal crossing the wrench, bottom-left to top-right)
    sc_color = (color[0] // 2, color[1] // 2, color[2] // 2, 255)  # darker shade
    _rotated_bar(S * 0.22, S * 0.78, S * 0.70, S * 0.30, int(T * 0.7), sc_color)
    # Screwdriver handle (rounded rectangle at bottom-left)
    hx, hy = S * 0.22, S * 0.78
    hr = int(S * 0.10)
    d.rounded_rectangle([hx - hr, hy - hr * 0.8, hx + hr, hy + hr * 0.8],
                        radius=int(hr * 0.4), fill=color)
    # Screwdriver tip (small triangle at top-right)
    tx, ty = S * 0.70, S * 0.30
    d.polygon([(tx - S * 0.04, ty - S * 0.04),
               (tx + S * 0.04, ty + S * 0.04),
               (tx + S * 0.08, ty - S * 0.02)], fill=color)

    return img


# ---------------------------------------------------------------------------
#  Icon 2: Maintenance — broom sweeping
# ---------------------------------------------------------------------------
def _icon_maintenance() -> Image.Image:
    color = COLORS["maintenance"]
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    S = CANVAS

    # Handle: thick diagonal line from top-right to center
    handle = (color[0] // 2, color[1] // 2, color[2] // 2, 255)
    d.line([(S * 0.72, S * 0.18), (S * 0.42, S * 0.48)],
           fill=handle, width=int(S * 0.08))

    # Broom head: trapezoid at the bottom-left, angled to match the handle
    # Define the brush block as a polygon
    bx, by = S * 0.42, S * 0.48   # top of brush block
    bw, bh = S * 0.22, S * 0.16   # block size
    # The block is rotated ~45 degrees; draw as a parallelogram
    pts = [
        (bx - bw * 0.3, by - bh * 0.2),         # top-left
        (bx + bw * 0.7, by - bh * 0.9),         # top-right
        (bx + bw * 0.3, by + bh * 0.8),         # bottom-right
        (bx - bw * 0.7, by + bh * 0.1),         # bottom-left
    ]
    d.polygon(pts, fill=color)

    # Bristles: several thin lines extending downward-left from the block
    bristle_color = (color[0], color[1], color[2], 255)
    for i in range(6):
        t = i / 5.0
        sx = (bx - bw * 0.7) * (1 - t) + (bx + bw * 0.3) * t
        sy = (by + bh * 0.1) * (1 - t) + (by + bh * 0.8) * t
        # Bristle extends diagonally down-left
        d.line([(sx, sy), (sx - S * 0.10, sy + S * 0.16)],
               fill=bristle_color, width=max(2, int(S * 0.022)))

    # Small sparkle dots to suggest "clean"
    for (px, py, pr) in [(S * 0.20, S * 0.20, S * 0.025),
                          (S * 0.16, S * 0.34, S * 0.018),
                          (S * 0.30, S * 0.16, S * 0.015)]:
        d.ellipse([px - pr, py - pr, px + pr, py + pr], fill=color)

    return img


# ---------------------------------------------------------------------------
#  Icon 3: Hardware & Diagnostics — chip with magnifying glass overlay
# ---------------------------------------------------------------------------
def _icon_diagnostics() -> Image.Image:
    color = COLORS["diagnostics"]
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    S = CANVAS

    # Chip body (square with rounded corners, top-left area)
    cx0, cy0, cx1, cy1 = S * 0.18, S * 0.18, S * 0.58, S * 0.58
    d.rounded_rectangle([cx0, cy0, cx1, cy1],
                        radius=int(S * 0.04), fill=color)

    # Chip inner square (darker, "die")
    inner = (color[0] // 3, color[1] // 3, color[2] // 3, 255)
    ix0 = cx0 + S * 0.10
    iy0 = cy0 + S * 0.10
    ix1 = cx1 - S * 0.10
    iy1 = cy1 - S * 0.10
    d.rounded_rectangle([ix0, iy0, ix1, iy1],
                        radius=int(S * 0.02), fill=inner)

    # Pin legs on all 4 sides of the chip
    pin_w = int(S * 0.04)
    pin_l = int(S * 0.06)
    for i in range(3):
        t = (i + 1) / 4.0
        # Top pins
        px = cx0 + (cx1 - cx0) * t
        d.rectangle([px - pin_w // 2, cy0 - pin_l,
                      px + pin_w // 2, cy0], fill=color)
        # Bottom pins
        d.rectangle([px - pin_w // 2, cy1,
                      px + pin_w // 2, cy1 + pin_l], fill=color)
        # Left pins
        py = cy0 + (cy1 - cy0) * t
        d.rectangle([cx0 - pin_l, py - pin_w // 2,
                      cx0, py + pin_w // 2], fill=color)
        # Right pins
        d.rectangle([cx1, py - pin_w // 2,
                      cx1 + pin_l, py + pin_w // 2], fill=color)

    # Magnifying glass (bottom-right, overlapping the chip)
    lx, ly = S * 0.66, S * 0.66     # lens center
    lr = int(S * 0.16)             # lens radius
    lt = max(3, int(S * 0.035))    # lens ring thickness
    # Lens ring (outer circle in accent, inner transparent)
    d.ellipse([lx - lr, ly - lr, lx + lr, ly + lr], fill=color)
    d.ellipse([lx - lr + lt, ly - lr + lt,
               lx + lr - lt, ly + lr - lt], fill=(0, 0, 0, 0))
    # Handle (thick line from lens to bottom-right corner)
    hx0, hy0 = lx + lr * 0.7, ly + lr * 0.7
    hx1, hy1 = S * 0.88, S * 0.88
    d.line([(hx0, hy0), (hx1, hy1)], fill=color,
           width=max(4, int(S * 0.06)))

    return img


# ---------------------------------------------------------------------------
#  Icon 4: System Info & Status — monitor with an "i" info symbol
# ---------------------------------------------------------------------------
def _icon_status() -> Image.Image:
    color = COLORS["status"]
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    S = CANVAS

    # Monitor outline (rounded rectangle)
    mx0, my0, mx1, my1 = S * 0.18, S * 0.16, S * 0.82, S * 0.66
    t = max(3, int(S * 0.035))  # border thickness
    d.rounded_rectangle([mx0, my0, mx1, my1],
                        radius=int(S * 0.05), fill=color)
    # Cut out interior
    d.rounded_rectangle([mx0 + t, my0 + t, mx1 - t, my1 - t],
                        radius=int(S * 0.04), fill=(0, 0, 0, 0))

    # Stand (vertical bar + base)
    sx = S * 0.50
    d.line([(sx, my1), (sx, my1 + S * 0.10)],
           fill=color, width=max(4, int(S * 0.05)))
    d.rounded_rectangle([sx - S * 0.14, my1 + S * 0.10,
                         sx + S * 0.14, my1 + S * 0.14],
                        radius=int(S * 0.015), fill=color)

    # Info "i" inside the monitor screen
    # Dot above the stem
    iy = (my0 + my1) / 2
    dot_r = int(S * 0.05)
    d.ellipse([sx - dot_r, iy - S * 0.13 - dot_r,
               sx + dot_r, iy - S * 0.13 + dot_r], fill=color)
    # Stem (vertical bar)
    d.rounded_rectangle([sx - dot_r * 0.7, iy - S * 0.06,
                         sx + dot_r * 0.7, iy + S * 0.10],
                        radius=int(dot_r * 0.5), fill=color)

    return img


# ---------------------------------------------------------------------------
#  Main
# ---------------------------------------------------------------------------
ICONS = {
    "repair": _icon_repair,
    "maintenance": _icon_maintenance,
    "diagnostics": _icon_diagnostics,
    "status": _icon_status,
}


def main() -> None:
    print(f"Rendering 4 category icons at {CANVAS}x{CANVAS} (4x SS)...")
    print(f"Output dir: {ICONS_DIR}")
    for key, fn in ICONS.items():
        hi = fn()
        _save(hi, key)
    print("Done!")


if __name__ == "__main__":
    main()
