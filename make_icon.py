"""Generate the SysPeek application icon (app.ico).

Design: "System Info Monitor"
  - Dark rounded square background with subtle radial gradient
    (matching the app's dark theme: #2d2d2d center -> #0d0d0d edges)
  - Blue monitor outline (the app's accent color #60cdff)
  - Three horizontal data bars inside (representing the info cards)
  - Blue accent segment on the top bar (matching card headers)
  - Subtle blue glow around the monitor

Rendered at 4x resolution (2048px) then downsampled to 512px for
smooth anti-aliased edges. Saved as a multi-size .ico (16, 32, 48,
64, 128, 256) so Windows can pick the best size for any context.

Run:  python make_icon.py
Output: app.ico  (next to this script)
"""

from __future__ import annotations

import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

# ---------------------------------------------------------------------------
#  Configuration
# ---------------------------------------------------------------------------
# High-res canvas for supersampling (4x the target 512px).
SS = 4
CANVAS = 512 * SS          # 2048
TARGET = 512              # final icon size before multi-size export

# Colors from the app's dark theme
BG_CENTER = np.array([45, 45, 45], dtype=np.float32)     # #2d2d2d
BG_EDGE   = np.array([10, 10, 10], dtype=np.float32)     # #0a0a0a
ACCENT    = (96, 205, 255)                               # #60cdff
ACCENT_DIM = (30, 80, 100)                               # glow color
WHITE     = (255, 255, 255)
BAR_DIM   = (170, 170, 170)                              # dimmer bars
CARD_BG   = (20, 20, 20)                                # monitor interior

ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.ico")

# Monitor geometry (fractions of canvas size)
MON_INSET_X = 0.18       # left/right margin
MON_INSET_TOP = 0.16     # top margin
MON_INSET_BOT = 0.28     # bottom margin (leaves room for stand)
MON_RADIUS = 0.06         # corner radius
STAND_WIDTH = 0.14
STAND_HEIGHT = 0.05
STAND_GAP = 0.02

# Data bar geometry (fractions of monitor interior)
BAR_MARGIN_X = 0.08
BAR_MARGIN_TOP = 0.12
BAR_GAP = 0.06
BAR_HEIGHT = 0.16
ACCENT_SEG_WIDTH = 0.25  # blue accent segment on first bar


def _rounded_rect_mask(size: int, x0: float, y0: float, x1: float, y1: float,
                       radius: float) -> Image.Image:
    """Return an 'L' mode mask with a filled rounded rectangle."""
    mask = Image.new('L', (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle(
        [x0 * size, y0 * size, x1 * size, y1 * size],
        radius=radius * size, fill=255,
    )
    return mask


def _radial_gradient(size: int, center: np.ndarray, edge: np.ndarray) -> Image.Image:
    """Create an RGB radial gradient (center -> edge) via numpy."""
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    cx = cy = size / 2.0
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    max_dist = math.sqrt(cx ** 2 + cy ** 2)
    t = np.clip(dist / max_dist, 0, 1)[:, :, np.newaxis]  # (H, W, 1)
    colors = center * (1 - t) + edge * t  # (H, W, 3)
    arr = np.clip(colors, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, 'RGB')


def _glow(size: int, shape_mask: Image.Image, color: tuple,
          blur: int = 0, opacity: float = 1.0) -> Image.Image:
    """Create a colored glow from a shape mask."""
    glow = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    colored = Image.new('RGBA', (size, size), color + (0,))
    colored.putalpha(shape_mask)
    glow.alpha_composite(colored)
    if blur > 0:
        glow = glow.filter(ImageFilter.GaussianBlur(blur))
    if opacity < 1.0:
        alpha = glow.split()[3].point(lambda a: int(a * opacity))
        glow.putalpha(alpha)
    return glow


def render_icon() -> Image.Image:
    """Render the icon at CANVAS resolution, return RGBA Image."""
    S = CANVAS

    # --- 1. Background: dark rounded square with radial gradient ---------
    bg_grad = _radial_gradient(S, BG_CENTER, BG_EDGE).convert('RGBA')
    # Round the corners
    corner_radius = 0.18  # fraction of size
    bg_mask = _rounded_rect_mask(S, 0, 0, 1, 1, corner_radius)
    bg = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    bg.paste(bg_grad, (0, 0), bg_mask)

    # --- 2. Monitor outline geometry -------------------------------------
    mx0 = MON_INSET_X
    my0 = MON_INSET_TOP
    mx1 = 1.0 - MON_INSET_X
    my1 = 1.0 - MON_INSET_BOT
    mon_w = mx1 - mx0
    mon_h = my1 - my0

    # Monitor interior (filled dark)
    interior_mask = _rounded_rect_mask(S, mx0, my0, mx1, my1, MON_RADIUS)
    interior = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    interior.paste(CARD_BG + (255,), (0, 0), interior_mask)

    # Monitor border (blue ring) — draw a slightly larger filled rounded rect,
    # then cut out the interior to leave a ring.
    border_thickness = 0.018  # fraction of canvas
    outer_mask = _rounded_rect_mask(
        S,
        mx0 - border_thickness, my0 - border_thickness,
        mx1 + border_thickness, my1 + border_thickness,
        MON_RADIUS + border_thickness,
    )
    ring_mask = outer_mask.copy()
    # Subtract interior
    ring_arr = np.array(ring_mask)
    interior_arr = np.array(interior_mask)
    ring_arr = np.where(interior_arr > 0, 0, ring_arr)
    ring_mask = Image.fromarray(ring_arr, 'L')

    monitor_ring = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    ring_color = Image.new('RGBA', (S, S), ACCENT + (255,))
    ring_color.putalpha(ring_mask)
    monitor_ring.alpha_composite(ring_color)

    # --- 3. Monitor stand ------------------------------------------------
    stand_cx = 0.5
    stand_w_half = STAND_WIDTH / 2
    sy0 = my1 + STAND_GAP
    sy1 = sy0 + STAND_HEIGHT
    stand_mask = _rounded_rect_mask(
        S, stand_cx - stand_w_half, sy0,
        stand_cx + stand_w_half, sy1, 0.01,
    )
    stand = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    stand_col = Image.new('RGBA', (S, S), ACCENT + (255,))
    stand_col.putalpha(stand_mask)
    stand.alpha_composite(stand_col)

    # Stand base (wider bar below)
    base_h = 0.018
    by0 = sy1 + STAND_GAP * 1.5
    by1 = by0 + base_h
    base_mask = _rounded_rect_mask(
        S, stand_cx - STAND_WIDTH * 0.9, by0,
        stand_cx + STAND_WIDTH * 0.9, by1, 0.008,
    )
    base = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    base_col = Image.new('RGBA', (S, S), ACCENT + (255,))
    base_col.putalpha(base_mask)
    base.alpha_composite(base_col)

    # --- 4. Data bars inside the monitor --------------------------------
    bar_x0 = mx0 + mon_w * BAR_MARGIN_X
    bar_x1 = mx1 - mon_w * BAR_MARGIN_X
    bar_w = bar_x1 - bar_x0

    bars: list[tuple[float, float, tuple[int, int, int], float]] = []
    # (y_start, accent_seg_fraction_or_None, color, opacity)
    bar_y = my0 + mon_h * BAR_MARGIN_TOP
    for i in range(3):
        bars.append((bar_y, bar_w, BAR_DIM if i > 0 else WHITE, 1.0))
        bar_y += mon_h * (BAR_HEIGHT + BAR_GAP)

    bar_layer = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bar_layer)
    for i, (by, bw, color, op) in enumerate(bars):
        by1 = by + mon_h * BAR_HEIGHT
        # Main bar (rounded)
        bd.rounded_rectangle(
            [bar_x0 * S, by * S, bar_x1 * S, by1 * S],
            radius=mon_h * BAR_HEIGHT * S * 0.3,
            fill=color + (int(255 * op),),
        )
        # Blue accent segment on the first bar (left side)
        if i == 0:
            seg_w = bw * ACCENT_SEG_WIDTH
            bd.rounded_rectangle(
                [bar_x0 * S, by * S, (bar_x0 + seg_w) * S, by1 * S],
                radius=mon_h * BAR_HEIGHT * S * 0.3,
                fill=ACCENT + (255,),
            )

    # --- 5. Blue glow behind the monitor --------------------------------
    glow_blur = int(S * 0.025)
    glow_img = _glow(S, outer_mask, ACCENT_DIM, blur=glow_blur, opacity=0.5)

    # --- 6. Composite all layers ----------------------------------------
    result = bg.copy()
    result.alpha_composite(glow_img)
    result.alpha_composite(interior)
    result.alpha_composite(monitor_ring)
    result.alpha_composite(stand)
    result.alpha_composite(base)
    result.alpha_composite(bar_layer)

    return result


def main() -> None:
    print(f"Rendering icon at {CANVAS}x{CANVAS} (4x supersampling)...")
    hi_res = render_icon()

    # Downsample to target size with high-quality Lanczos resampling
    print(f"Downsampling to {TARGET}x{TARGET}...")
    icon = hi_res.resize((TARGET, TARGET), Image.LANCZOS)

    # Export as multi-size .ico
    # PIL's .ico save supports sizes= parameter for embedding multiple
    # resolutions in a single file.
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
             (128, 128), (256, 256)]
    print(f"Saving multi-size .ico to: {ICON_PATH}")
    print(f"  Sizes: {[s[0] for s in sizes]}")
    icon.save(ICON_PATH, format='ICO', sizes=sizes)

    file_size = os.path.getsize(ICON_PATH)
    print(f"Done! {ICON_PATH} ({file_size:,} bytes)")

    # Also save a preview PNG for easy viewing
    preview_path = ICON_PATH.replace('.ico', '_preview.png')
    icon.save(preview_path, format='PNG')
    print(f"Preview saved: {preview_path}")


if __name__ == '__main__':
    main()
