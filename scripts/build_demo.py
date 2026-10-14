#!/usr/bin/env python3
"""Build the RedPen demo video from live captures of the running app.

This is not a mockup. Every frame is a headless-Chrome capture of the real app
at a wall-clock offset while Gemma streamed its answer over SSE, so the frames
genuinely differ: the verdict appears first (the rule pass is ~20 ms), then the
brief, then the per-finding explanations, then the negotiation email.

    python3 scripts/build_demo.py            # writes assets/demo.mp4 + demo.gif
    python3 scripts/build_demo.py --serve    # just prints the ffmpeg commands

Requires: the app running on 127.0.0.1:8790, llama-server on 8777, and ffmpeg.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
APP = "http://127.0.0.1:8790"
W, H = 1500, 1150

# (label, url, budget ms, seconds, caption, capture height, crop box or None)
#
# The email panel sits below the fold at 1150px, so that shot captures a tall
# viewport and crops to the panel -- otherwise the caption promises an email and
# the frame shows the top of the page again.
SHOTS = [
    ("rules", f"{APP}/?sample=northgate_msa&nollm=1", 2500, 4.0,
     "65 rules, ~20 ms. No model has run yet.", H, None),
    ("brief", f"{APP}/?sample=northgate_msa", 5000, 4.0,
     "Gemma 3 1B starts streaming, local, over loopback.", H, None),
    ("explain", f"{APP}/?sample=northgate_msa", 11000, 4.0,
     "Per-finding explanations, in the context of this contract.", H, None),
    ("email", f"{APP}/?sample=northgate_msa&shot=email", 24000, 5.0,
     "The negotiation email, written locally. Coverage of the asks is checked before it is shown.", H, None),
    ("clean", f"{APP}/?sample=bright_harbour_fair&nollm=1", 2500, 4.5,
     "A fair contract: zero findings. Precision is the product.", H, None),
    ("offer", f"{APP}/?sample=offer_letter_internship&nollm=1", 2500, 4.5,
     "An offer letter: different document, different rules, blanks counted.", H, None),
]

TITLE = ("RedPen", "offline contract review for freelancers",
         "open weights · open rules · nothing leaves the laptop")
END = ("65 rules · 98 tests", "Gemma 3 1B on an 8 GB MacBook",
       "MIT · github.com/soumwadeep/RedPen")


def font(size: int):
    from PIL import ImageFont
    for path in ("/System/Library/Fonts/Menlo.ttc",
                 "/System/Library/Fonts/Monaco.ttf",
                 "/System/Library/Fonts/SFMono-Regular.otf"):
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def wait_app(timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{APP}/api/status", timeout=2):
                return True
        except Exception:
            time.sleep(0.5)
    return False


def shoot(url: str, budget: int, dest: Path, height: int = H) -> bool:
    cmd = [CHROME, "--headless=new", "--disable-gpu", f"--screenshot={dest}",
           f"--window-size={W},{height}", f"--virtual-time-budget={budget}",
           "--hide-scrollbars", url]
    subprocess.run(cmd, check=True, capture_output=True)
    return dest.exists()


def caption(src: Path, dest: Path, text: str, crop: tuple[int,int,int,int] | None = None) -> None:
    from PIL import Image, ImageDraw
    im = Image.open(src).convert("RGB")
    if crop:
        # Paste the cropped region onto a full-size canvas so every frame in the
        # concat has identical dimensions and the close-up stays legible.
        piece = im.crop(crop)
        canvas = Image.new("RGB", (W, H), (6, 8, 13))
        y = max((H - piece.height) // 2 - 40, 0)
        canvas.paste(piece, ((W - piece.width) // 2, y))
        im = canvas
    draw = ImageDraw.Draw(im)
    f = font(21)
    bar_h = 46
    draw.rectangle([0, H - bar_h, W, H], fill=(8, 11, 18))
    draw.line([0, H - bar_h, W, H - bar_h], fill=(27, 36, 54))
    draw.text((26, H - bar_h + 13), text, font=f, fill=(127, 231, 255))
    im.save(dest)


def card(dest: Path, lines: tuple[str, str, str]) -> None:
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (W, H), (6, 8, 13))
    d = ImageDraw.Draw(im)
    # scanlines + a faint grid, in the language of the app itself
    for y in range(0, H, 4):
        d.line([0, y, W, y], fill=(9, 12, 19))
    for x in range(0, W, 120):
        d.line([x, 0, x, H], fill=(11, 15, 23))
    d.rectangle([60, 60, W - 60, H - 60], outline=(27, 36, 54), width=1)
    big, mid = font(64), font(26)
    d.text((110, H // 2 - 130), lines[0], font=big, fill=(234, 242, 255))
    d.text((112, H // 2 - 30), lines[1], font=mid, fill=(127, 231, 255))
    d.text((112, H // 2 + 14), lines[2], font=mid, fill=(111, 127, 156))
    im.save(dest)


def run(cmd: list[str], dry: bool) -> None:
    print("$", " ".join(str(c) for c in cmd)[:220])
    if not dry:
        subprocess.run(cmd, check=True, capture_output=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true", help="print commands only")
    ap.add_argument("--no-gif", action="store_true")
    args = ap.parse_args()

    if not Path(CHROME).exists():
        print("Chrome not found at", CHROME, file=sys.stderr)
        return 2
    if not shutil.which("ffmpeg"):
        print("ffmpeg not found", file=sys.stderr)
        return 2
    if not args.serve and not wait_app():
        print("app is not running: start it with `redpen`", file=sys.stderr)
        return 2

    OUT.mkdir(exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="redpen-demo-"))
    seq: list[tuple[Path, float]] = []

    card(tmp / "00-title.png", TITLE)
    seq.append((tmp / "00-title.png", 3.0))

    for i, (name, url, budget, secs, cap, height, crop) in enumerate(SHOTS, start=1):
        raw = tmp / f"{i:02d}-{name}-raw.png"
        print(f"  capturing {name:8} @ {budget}ms virtual time, {W}x{height} ...")
        if not shoot(url, budget, raw, height):
            print("  failed:", name, file=sys.stderr)
            continue
        out = tmp / f"{i:02d}-{name}.png"
        caption(raw, out, cap, crop)
        seq.append((out, secs))

    card(tmp / "99-end.png", END)
    seq.append((tmp / "99-end.png", 3.5))

    listfile = tmp / "list.txt"
    listfile.write_text("".join(f"file '{p}'\nduration {s}\n" for p, s in seq)
                        + f"file '{seq[-1][0]}'\n")

    mp4 = OUT / "demo.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
         "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "medium",
         "-crf", "23", "-movflags", "+faststart", str(mp4)], args.serve)

    if not args.no_gif:
        gif = OUT / "demo.gif"
        # palette pass keeps a UI screencast legible at a fraction of the size
        pal = tmp / "palette.png"
        run(["ffmpeg", "-y", "-i", str(mp4), "-vf",
             "fps=6,scale=900:-1:flags=lanczos,palettegen=max_colors=128", str(pal)],
            args.serve)
        run(["ffmpeg", "-y", "-i", str(mp4), "-i", str(pal), "-lavfi",
             "fps=6,scale=900:-1:flags=lanczos [x]; [x][1:v] paletteuse=dither=bayer",
             str(gif)], args.serve)

    total = sum(s for _, s in seq)
    print(f"\n{len(seq)} frames, ~{total:.0f}s")
    for p in (OUT / "demo.mp4", OUT / "demo.gif"):
        if p.exists():
            print(f"  {p}  {p.stat().st_size/1e6:.1f} MB")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
