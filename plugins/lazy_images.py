"""
Lazy Images Plugin for Pelican.

Adds loading="lazy" to all <img> tags in generated HTML
that don't already have a loading attribute.
"""

import re

from pelican import signals

_IMG_RE = re.compile(r"<img\b(?![^>]*\bloading\s*=)", re.IGNORECASE)


def add_lazy_loading(path, context):
    if not path.endswith(".html"):
        return

    with open(path, encoding="utf-8") as f:
        content = f.read()

    new_content = _IMG_RE.sub('<img loading="lazy"', content)

    if new_content != content:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)


def register():
    signals.content_written.connect(add_lazy_loading)
