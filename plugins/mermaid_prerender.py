"""
Mermaid Pre-Render Plugin for Pelican.

Replaces <pre class="mermaid">...</pre> blocks in generated HTML
with inline SVGs pre-rendered by mmdc (mermaid-cli) at build time.

This eliminates the need to load the 800KB+ mermaid.min.js library
and perform client-side rendering of diagrams.

Optimizations:
- SHA256 disk cache (.mermaid-cache/) avoids re-rendering unchanged diagrams
- Parallel mmdc calls via ThreadPoolExecutor

Requires: @mermaid-js/mermaid-cli (mmdc) and a Chromium browser.
Config:   mermaid.config.json (theme/style) + puppeteer.json (browser path).
"""

import hashlib
import logging
import os
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

from pelican import signals

logger = logging.getLogger(__name__)

_MERMAID_RE = re.compile(
    r'<pre\s+class="mermaid">\s*(.*?)\s*</pre>',
    re.DOTALL,
)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MMDC = shutil.which("mmdc")
_MERMAID_CONFIG = os.path.join(_PROJECT_ROOT, "mermaid.config.json")
_PUPPETEER_CONFIG = os.path.join(_PROJECT_ROOT, "puppeteer.json")
_CACHE_DIR = os.path.join(_PROJECT_ROOT, ".mermaid-cache")
_MAX_WORKERS = 4

# In-memory cache for same-process dedup (FR + EN share diagrams)
_svg_cache: dict[str, str] = {}


def _cache_key(mermaid_code):
    """SHA256 of mermaid source + config for cache invalidation."""
    h = hashlib.sha256(mermaid_code.encode())
    # Include config in hash so theme changes bust the cache
    for cfg in (_MERMAID_CONFIG, _PUPPETEER_CONFIG):
        if os.path.isfile(cfg):
            with open(cfg, "rb") as f:
                h.update(f.read())
    return h.hexdigest()


def _load_from_disk_cache(key):
    """Load a cached SVG from disk, return None if not found."""
    path = os.path.join(_CACHE_DIR, f"{key}.svg")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return None


def _save_to_disk_cache(key, svg):
    """Persist rendered SVG to disk cache."""
    os.makedirs(_CACHE_DIR, exist_ok=True)
    path = os.path.join(_CACHE_DIR, f"{key}.svg")
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)


def _render_svg(mermaid_code):
    """Run mmdc to convert mermaid code to an inline SVG string."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".mmd", delete=False) as src:
        src.write(mermaid_code)
        src_path = src.name

    out_path = src_path.replace(".mmd", ".svg")

    try:
        cmd = [
            _MMDC,
            "-i",
            src_path,
            "-o",
            out_path,
            "-b",
            "transparent",
        ]
        if os.path.isfile(_MERMAID_CONFIG):
            cmd += ["-c", _MERMAID_CONFIG]
        if os.path.isfile(_PUPPETEER_CONFIG):
            cmd += ["-p", _PUPPETEER_CONFIG]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            logger.warning("mmdc failed: %s", result.stderr[:500])
            return None

        with open(out_path, encoding="utf-8") as f:
            svg = f.read()

        # Strip XML declaration if present
        svg = re.sub(r"<\?xml[^?]*\?>\s*", "", svg)

        return svg

    except subprocess.TimeoutExpired:
        logger.warning("mmdc timed out for diagram")
        return None
    finally:
        for p in (src_path, out_path):
            if os.path.exists(p):
                os.unlink(p)


def _unescape_html(text):
    """Unescape HTML entities that Pelican/markdown may have introduced."""
    return (
        text.replace("&gt;", ">")
        .replace("&lt;", "<")
        .replace("&amp;", "&")
        .replace("&quot;", '"')
    )


def _get_or_render(mermaid_code):
    """Get SVG from cache or render it. Returns (key, svg_or_None)."""
    code = _unescape_html(mermaid_code)
    key = _cache_key(code)

    # 1. In-memory cache (instant)
    if key in _svg_cache:
        return key, _svg_cache[key]

    # 2. Disk cache (fast)
    svg = _load_from_disk_cache(key)
    if svg is not None:
        _svg_cache[key] = svg
        return key, svg

    # 3. Render with mmdc (slow)
    svg = _render_svg(code)
    if svg is not None:
        _svg_cache[key] = svg
        _save_to_disk_cache(key, svg)

    return key, svg


def _assign_unique_ids(svg, idx):
    """Replace generic 'my-svg' id with a per-diagram unique id."""
    uid = f"mermaid-svg-{idx}"
    return svg.replace("my-svg", uid)


def prerender_mermaid(path, context):
    """Post-process generated HTML to replace mermaid blocks with SVGs."""
    if not path.endswith(".html"):
        return

    if _MMDC is None:
        return

    with open(path, encoding="utf-8") as f:
        content = f.read()

    matches = list(_MERMAID_RE.finditer(content))
    if not matches:
        return

    # Deduplicate: collect unique diagram codes to render
    diagrams = []
    for m in matches:
        code = _unescape_html(m.group(1))
        key = _cache_key(code)
        diagrams.append((m, code, key))

    # Find which keys actually need rendering (not in any cache)
    to_render = {}
    for _, code, key in diagrams:
        if key not in _svg_cache and _load_from_disk_cache(key) is None:
            to_render[key] = code

    cached = len(diagrams) - len(to_render)
    if cached:
        logger.info(
            "%s: %d diagram(s) from cache, %d to render",
            os.path.basename(path),
            cached,
            len(to_render),
        )
    if to_render:
        logger.info(
            "Rendering %d mermaid diagram(s) in %s (parallel, %d workers)",
            len(to_render),
            os.path.basename(path),
            _MAX_WORKERS,
        )

    # Render uncached diagrams in parallel
    if to_render:
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            futures = {
                pool.submit(_render_svg, code): key for key, code in to_render.items()
            }
            for future in as_completed(futures):
                key = futures[future]
                svg = future.result()
                if svg is not None:
                    _svg_cache[key] = svg
                    _save_to_disk_cache(key, svg)

    # Load any disk-cached items into memory
    for _, _, key in diagrams:
        if key not in _svg_cache:
            svg = _load_from_disk_cache(key)
            if svg is not None:
                _svg_cache[key] = svg

    # Substitute all matches (reverse order to preserve offsets)
    new_content = content
    for idx, (m, _code, key) in enumerate(reversed(diagrams)):
        svg = _svg_cache.get(key)
        if svg is None:
            continue  # Keep original block as fallback
        unique_svg = _assign_unique_ids(svg, len(diagrams) - 1 - idx)
        replacement = f'<pre class="mermaid">{unique_svg}</pre>'
        new_content = new_content[: m.start()] + replacement + new_content[m.end() :]

    if new_content != content:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)


def register():
    signals.content_written.connect(prerender_mermaid)
