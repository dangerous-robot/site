#!/usr/bin/env python3
"""Write the web copy of a chosen image: src/assets/posts/<id>.jpg (or .png with transparency).

Pillow is not a project dependency, so run it through uv:

    uv run --with pillow python3 .claude/skills/image-candidate/export_web.py <original> <id>

The same rules apply to every image, so no post needs its own tuning:
- Crop to the subject. When the corners share one flat background colour (art on
  white or black), trim it to the subject's edges plus a 1% margin. A photo with
  no flat background is left uncropped.
- 2400px on the long side at most; metadata (EXIF, GPS) is not copied.
"""
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageOps

LONG_SIDE = 2400
QUALITY = 85
MARGIN = 0.01
# How far a pixel may differ from the background before it counts as subject.
# High enough to skip JPEG noise, low enough to keep faint lines.
INK = 12
OUT_DIR = Path(__file__).resolve().parents[3] / "src" / "assets" / "posts"


def subject_box(im: Image.Image) -> tuple[int, int, int, int] | None:
    """The subject's bounding box, or None when the corners don't share one background."""
    rgb = im.convert("RGB")
    w, h = rgb.size
    corners = [rgb.getpixel(p) for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
    bg = corners[0]
    if any(max(abs(a - b) for a, b in zip(c, bg)) > INK for c in corners):
        return None
    diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, bg)).convert("L")
    box = diff.point(lambda v: 255 if v > INK else 0).getbbox()
    if box is None:
        return None
    pad = round(max(w, h) * MARGIN)
    l, t, r, b = box
    return max(0, l - pad), max(0, t - pad), min(w, r + pad), min(h, b + pad)


def main(src: str, image_id: str) -> None:
    with Image.open(src) as im:
        alpha = "A" in im.getbands() or "transparency" in im.info
        im = ImageOps.exif_transpose(im)
        im = im.convert("RGBA" if alpha else "RGB")
        box = None if alpha else subject_box(im)
        if box:
            im = im.crop(box)
        im.thumbnail((LONG_SIDE, LONG_SIDE), Image.LANCZOS)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        out = OUT_DIR / f"{image_id}.{'png' if alpha else 'jpg'}"
        if alpha:
            im.save(out, "PNG", optimize=True)
        else:
            im.save(out, "JPEG", quality=QUALITY, optimize=True)
    note = f"cropped to {box}" if box else "not cropped (no flat background)"
    print(f"{out.relative_to(OUT_DIR.parents[2])} {im.width}x{im.height} {out.stat().st_size} bytes, {note}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: export_web.py <original> <id>")
    main(sys.argv[1], sys.argv[2])
