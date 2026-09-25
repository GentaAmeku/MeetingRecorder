#!/usr/bin/env python3
"""Generates MeetingRecorder's app icon.

Design (editorial / art direction): a high-contrast Didot serif "R" on a
cream background, with a small red period (dot) at its foot standing in for
recording. Renders every size macOS needs from a single master, places them
into AppIcon.appiconset, and updates Contents.json too.

Font dependency: relies on macOS's Didot
(/System/Library/Fonts/Supplemental/Didot.ttc), so generation must happen on
this Mac (the generated PNGs are committed to the repository).

Run it (from the repository root):
    uv run --with pillow python scripts/generate_appicon.py
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ICONSET = (
    Path(__file__).resolve().parent.parent
    / "MeetingRecorder/MeetingRecorder/Assets.xcassets/AppIcon.appiconset"
)

DIDOT = "/System/Library/Fonts/Supplemental/Didot.ttc"

CREAM = (244, 240, 233, 255)   # background
INK = (26, 26, 28, 255)        # color of the R
REC_RED = (233, 53, 45, 255)   # recording dot (red period)

SS = 4  # supersampling factor (for smooth edges)

# The (size, scale) pairs macOS requires for the icon.
CONTENTS = [
    (16, 1), (16, 2),
    (32, 1), (32, 2),
    (128, 1), (128, 2),
    (256, 1), (256, 2),
    (512, 1), (512, 2),
]


def render_master(px: int) -> Image.Image:
    """Draws a px-by-px icon (rendered via supersampling)."""
    S = px * SS
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Rounded-rectangle background (macOS convention: ~22.4% corner radius).
    radius = int(S * 0.224)
    d.rounded_rectangle([0, 0, S, S], radius=radius, fill=CREAM)

    # The initial R (Didot, high-contrast serif).
    font = ImageFont.truetype(DIDOT, int(S * 0.70), index=0)
    d.text((S * 0.46, S * 0.50), "R", font=font, fill=INK, anchor="mm")

    # The red period standing in for recording.
    dot_r = S * 0.05
    dcx, dcy = S * 0.72, S * 0.70
    d.ellipse([dcx - dot_r, dcy - dot_r, dcx + dot_r, dcy + dot_r], fill=REC_RED)

    return img.resize((px, px), Image.LANCZOS)


def main() -> None:
    sizes = sorted({size * scale for size, scale in CONTENTS})
    for px in sizes:
        render_master(px).save(ICONSET / f"icon_{px}.png")

    images = [
        {
            "idiom": "mac",
            "scale": f"{scale}x",
            "size": f"{size}x{size}",
            "filename": f"icon_{size * scale}.png",
        }
        for size, scale in CONTENTS
    ]
    contents = {"images": images, "info": {"author": "xcode", "version": 1}}
    (ICONSET / "Contents.json").write_text(
        json.dumps(contents, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(sizes)} PNGs + Contents.json to {ICONSET}")


if __name__ == "__main__":
    main()
