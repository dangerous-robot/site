#!/usr/bin/env python3
"""Write the committed preview of a candidate: <id>.thumb.webp, 480px on the long side.

Pillow is not a project dependency, so run it through uv:

    uv run --with pillow python3 .claude/skills/image-candidate/make_thumb.py <original> <id>

The output goes to media/candidates/<id>.thumb.webp. Metadata (EXIF, GPS) is not
copied, and the image is re-encoded, so the thumbnail is never a copy of the original.
"""
import sys
from pathlib import Path

from PIL import Image, ImageOps

LONG_SIDE = 480
QUALITY = 75
OUT_DIR = Path(__file__).resolve().parents[3] / "media" / "candidates"


def main(src: str, image_id: str) -> None:
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
        im.thumbnail((LONG_SIDE, LONG_SIDE), Image.LANCZOS)
        out = OUT_DIR / f"{image_id}.thumb.webp"
        im.save(out, "WEBP", quality=QUALITY, method=6)
    print(f"{out.relative_to(OUT_DIR.parents[1])} {im.width}x{im.height} {out.stat().st_size} bytes")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: make_thumb.py <original> <id>")
    main(sys.argv[1], sys.argv[2])
