#!/usr/bin/env python3
"""Print facts about an image file as JSON: format, size, hash, orientation.

Standard library only, so it runs anywhere the repo does. Reads headers for
PNG, JPEG, GIF, WebP and SVG; AVIF and HEIC report their format with no size.

    python3 .claude/skills/image-candidate/inspect_image.py <file>
"""
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

# Long-side minimum for raster art (image guidelines, "What to hand over").
MIN_LONG_SIDE = 1600


def png(b):
    return struct.unpack(">II", b[16:24]) if b[:8] == b"\x89PNG\r\n\x1a\n" else None


def gif(b):
    return struct.unpack("<HH", b[6:10]) if b[:4] == b"GIF8" else None


def jpeg(b):
    if b[:2] != b"\xff\xd8":
        return None
    i = 2
    while i + 9 < len(b):
        if b[i] != 0xFF:
            i += 1
            continue
        marker = b[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        length = struct.unpack(">H", b[i + 2:i + 4])[0]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            h, w = struct.unpack(">HH", b[i + 5:i + 9])
            return w, h
        i += 2 + length
    return None


def webp(b):
    if b[:4] != b"RIFF" or b[8:12] != b"WEBP":
        return None
    chunk = b[12:16]
    if chunk == b"VP8 ":
        w, h = struct.unpack("<HH", b[26:30])
        return w & 0x3FFF, h & 0x3FFF
    if chunk == b"VP8L":
        b0, b1, b2, b3 = b[21:25]
        return 1 + (b0 | (b1 & 0x3F) << 8), 1 + (b1 >> 6 | b2 << 2 | (b3 & 0x0F) << 10)
    if chunk == b"VP8X":
        return 1 + int.from_bytes(b[24:27], "little"), 1 + int.from_bytes(b[27:30], "little")
    return None


def svg(b):
    head = b[:4096].decode("utf-8", "ignore")
    tag = re.search(r"<svg\b[^>]*>", head, re.S)
    if not tag:
        return None
    t = tag.group(0)
    w = re.search(r'\bwidth="([\d.]+)(px)?"', t)
    h = re.search(r'\bheight="([\d.]+)(px)?"', t)
    if w and h:
        return round(float(w.group(1))), round(float(h.group(1)))
    vb = re.search(r'viewBox="[\d.\-]+[ ,]+[\d.\-]+[ ,]+([\d.]+)[ ,]+([\d.]+)"', t)
    return (round(float(vb.group(1))), round(float(vb.group(2)))) if vb else (0, 0)


def iso_bmff(b):
    if b[4:8] != b"ftyp":
        return None
    brand = b[8:12].decode("ascii", "ignore")
    return {"avif": "avif", "avis": "avif"}.get(brand, "heic" if brand.startswith(("hei", "mif", "hev")) else None)


def main(path_str):
    path = Path(path_str)
    b = path.read_bytes()
    out = {"path": str(path), "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}
    for name, fn in (("png", png), ("jpeg", jpeg), ("gif", gif), ("webp", webp), ("svg", svg)):
        size = fn(b)
        if size:
            out["format"], (out["width"], out["height"]) = name, size
            break
    else:
        out["format"] = iso_bmff(b) or "unknown"

    flags = []
    w, h = out.get("width"), out.get("height")
    if w and h:
        ratio = w / h
        out["aspect"] = round(ratio, 3)
        out["orientation"] = "landscape" if ratio > 1.05 else "portrait" if ratio < 0.95 else "square"
        if out["format"] != "svg" and max(w, h) < MIN_LONG_SIDE:
            flags.append(f"long side {max(w, h)}px is under {MIN_LONG_SIDE}px")
        if out["orientation"] == "portrait":
            flags.append("portrait: shows small in the landscape spotlight, post and social boxes")
    if out["format"] == "heic":
        flags.append("HEIC: the site build cannot read it; export to JPEG")
    if out["format"] == "unknown":
        flags.append("unrecognized format")
    if len(b) > 5 * 1024 * 1024:
        flags.append(f"{len(b) / 1048576:.1f} MB: consider a smaller export before committing")
    out["flags"] = flags
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: inspect_image.py <file>")
    main(sys.argv[1])
