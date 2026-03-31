"""
Lazy Images Plugin for Pelican.

- Adds loading="lazy" to all <img> tags missing a loading attribute.
- Adds width/height from actual image files to prevent CLS (layout shifts).
"""

import logging
import os
import re
import struct

from pelican import signals

logger = logging.getLogger(__name__)

_IMG_RE = re.compile(r"<img\b(?![^>]*\bloading\s*=)", re.IGNORECASE)
_IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_SRC_RE = re.compile(r'\bsrc="([^"]*)"', re.IGNORECASE)
_HAS_DIMS_RE = re.compile(r"\b(?:width|height)\s*=", re.IGNORECASE)


def _get_image_dimensions(filepath):
    """Read image dimensions without external libs. Supports WebP, PNG, GIF, JPEG."""
    try:
        with open(filepath, "rb") as f:
            header = f.read(30)

        # WebP
        if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
            if header[12:16] == b"VP8 ":
                w = struct.unpack_from("<H", header, 26)[0] & 0x3FFF
                h = struct.unpack_from("<H", header, 28)[0] & 0x3FFF
                return w, h
            if header[12:16] == b"VP8L":
                bits = struct.unpack_from("<I", header, 21)[0]
                w = (bits & 0x3FFF) + 1
                h = ((bits >> 14) & 0x3FFF) + 1
                return w, h
            if header[12:16] == b"VP8X":
                with open(filepath, "rb") as f:
                    f.read(24)
                    data = f.read(6)
                w = struct.unpack_from("<I", data[:3] + b"\x00", 0)[0] + 1
                h = struct.unpack_from("<I", data[3:] + b"\x00", 0)[0] + 1
                return w, h

        # PNG
        if header[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack_from(">II", header, 16)
            return w, h

        # GIF
        if header[:6] in (b"GIF87a", b"GIF89a"):
            w, h = struct.unpack_from("<HH", header, 6)
            return w, h

        # JPEG
        if header[:2] == b"\xff\xd8":
            with open(filepath, "rb") as f:
                f.read(2)
                while True:
                    marker = f.read(2)
                    if len(marker) < 2:
                        break
                    if marker[0] != 0xFF:
                        break
                    if marker[1] in (0xC0, 0xC1, 0xC2):
                        f.read(3)  # length + precision
                        h, w = struct.unpack(">HH", f.read(4))
                        return w, h
                    length = struct.unpack(">H", f.read(2))[0]
                    f.read(length - 2)

    except (OSError, struct.error):
        pass
    return None, None


def add_lazy_loading(path, context):
    if not path.endswith(".html"):
        return

    output_root = path
    # Walk up to find the output root (where /images/ would be)
    settings = context.get("settings", {}) or context.get("SETTINGS", {})
    output_root = settings.get("OUTPUT_PATH", os.path.dirname(path))

    with open(path, encoding="utf-8") as f:
        content = f.read()

    # 1. Add loading="lazy"
    new_content = _IMG_RE.sub('<img loading="lazy"', content)

    # 2. Add width/height to images missing explicit dimensions
    def _add_dimensions(match):
        tag = match.group(0)
        if _HAS_DIMS_RE.search(tag):
            return tag  # Already has dimensions

        src_match = _SRC_RE.search(tag)
        if not src_match:
            return tag

        src = src_match.group(1)
        # Resolve to local file path
        if src.startswith("/"):
            img_path = os.path.join(output_root, src.lstrip("/"))
        elif src.startswith("http"):
            return tag  # Skip external images
        else:
            img_path = os.path.join(os.path.dirname(path), src)

        if not os.path.isfile(img_path):
            return tag

        w, h = _get_image_dimensions(img_path)
        if w and h:
            return tag.replace("<img ", f'<img width="{w}" height="{h}" ', 1)
        return tag

    new_content = _IMG_TAG_RE.sub(_add_dimensions, new_content)

    if new_content != content:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)


def register():
    signals.content_written.connect(add_lazy_loading)
