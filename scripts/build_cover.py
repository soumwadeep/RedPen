#!/usr/bin/env python3
"""Build the DEV cover image (1000x600) from the real app, not a stock graphic.

The post argues against bolting AI onto things for appearance's sake, so the
cover is composed from an actual screenshot of the running product, in the same
visual language as the UI: dark HUD, monospace, teal and red, corner brackets.

    python3 scripts/build_cover.py [path-to-source-screenshot]

Writes assets/cover.png.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
W, H = 1000, 600

INK = (6, 8, 13)
PANEL = (11, 15, 24)
LINE = (27, 36, 54)
TEXT = (234, 242, 255)
DIM = (111, 127, 156)
TEAL = (57, 230, 196)
RED = (255, 77, 94)
AMBER = (255, 176, 32)


def font(size: int, bold: bool = False):
    candidates = [
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Menlo-Bold.ttc",
        "/System/Library/Fonts/SFMono-Regular.otf",
        "/System/Library/Fonts/Supplemental/Monaco.ttf",
    ]
    if bold:
        candidates.insert(0, "/System/Library/Fonts/SFMono-Bold.otf")
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size, index=1 if bold else 0)
            except OSError:
                try:
                    return ImageFont.truetype(path, size)
                except OSError:
                    continue
    return ImageFont.load_default()


def spaced(draw, xy, text, f, fill, tracking=0):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=f, fill=fill)
        x += draw.textlength(ch, font=f) + tracking
    return x


def bracket(draw, box, color=LINE, size=14, width=1):
    x0, y0, x1, y1 = box
    for cx, cy, dx, dy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        draw.line([cx, cy, cx + dx * size, cy], fill=color, width=width)
        draw.line([cx, cy, cx, cy + dy * size], fill=color, width=width)


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ASSETS / "shot-01-verdict.png"
    if not src.exists():
        print(f"no source screenshot at {src}", file=sys.stderr)
        return 1

    im = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(im)

    # background: scanlines, a faint grid, and two soft glows
    for y in range(0, H, 4):
        d.line([0, y, W, y], fill=(9, 12, 19))
    for x in range(0, W, 50):
        d.line([x, 0, x, H], fill=(11, 15, 23))
    for cx, cy, r, col in ((180, 120, 320, (16, 44, 40)), (880, 520, 300, (46, 16, 22))):
        glow = Image.new("RGB", (W, H), INK)
        gd = ImageDraw.Draw(glow)
        gd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
        im = Image.blend(im, glow, 0.35)
    d = ImageDraw.Draw(im)

    # ---- right: the real UI, cropped to the verdict + findings column -------
    shot = Image.open(src).convert("RGB")
    # take the gauge + clause-map + first findings, which is the informative part
    crop = shot.crop((int(shot.width * 0.28), int(shot.height * 0.05),
                      int(shot.width * 0.66), int(shot.height * 0.52)))
    box_w, box_h = 452, 452
    scale = min(box_w / crop.width, box_h / crop.height)
    crop = crop.resize((int(crop.width * scale), int(crop.height * scale)), Image.LANCZOS)
    px, py = 512, 74
    panel = Image.new("RGB", (box_w, box_h), PANEL)
    ox = (box_w - crop.width) // 2
    oy = (box_h - crop.height) // 2
    panel.paste(crop, (ox, oy))
    # Fade the right edge so the interface reads as bleeding past the frame
    # rather than being sliced off mid-row.
    fade = Image.new("L", (box_w, box_h), 0)
    fd = ImageDraw.Draw(fade)
    for x in range(box_w):
        a = 0 if x < box_w - 90 else int(255 * (x - (box_w - 90)) / 90)
        fd.line([x, 0, x, box_h], fill=a)
    panel = Image.composite(Image.new("RGB", (box_w, box_h), PANEL), panel, fade)
    im.paste(panel, (px, py))
    d.rectangle([px, py, px + box_w - 1, py + box_h - 1], outline=LINE, width=1)
    bracket(d, (px - 5, py - 5, px + box_w + 4, py + box_h + 4), LINE, 16)
    d.text((px + 12, py + box_h + 12), "the real app · northgate_msa.pdf · 36 findings",
           font=font(13), fill=DIM)

    # ---- left: title block --------------------------------------------------
    end = spaced(d, (48, 96), "REDPEN", font(64), TEXT, tracking=2)
    # the cursor is placed from the measured end of the word, not a guessed offset
    d.rectangle([end + 10, 108, end + 20, 152], fill=RED)
    spaced(d, (50, 176), "OFFLINE CONTRACT REVIEW", font(17), TEAL, tracking=3)
    d.text((50, 208), "for freelancers who sign things", font=font(19), fill=DIM)

    d.line([48, 258, 470, 258], fill=LINE)

    rows = [
        ("65", "open rules decide", "what is dangerous", TEAL),
        ("1B", "Gemma runs locally ·", "8 GB RAM · no GPU", AMBER),
        ("0", "uploads · accounts ·", "API keys · per-review cost", RED),
    ]
    y = 282
    for big, l1, l2, col in rows:
        d.text((50, y), big, font=font(30), fill=col)
        d.text((112, y + 6), l1, font=font(15), fill=(201, 212, 232))
        d.text((112, y + 27), l2, font=font(15), fill=(201, 212, 232))
        y += 62

    d.line([48, 470, 470, 470], fill=LINE)
    d.text((50, 486), "rules judge · the model writes", font=font(15), fill=TEAL)
    d.text((50, 512), "MIT · github.com/soumwadeep/RedPen", font=font(14), fill=DIM)
    d.text((50, 536), "a pattern library, not a lawyer", font=font(13), fill=(79, 92, 116))

    out = ASSETS / "cover.png"
    im.save(out, optimize=True)
    print(f"{out}  {im.size}  {out.stat().st_size/1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
