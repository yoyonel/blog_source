"""
CSS/JS Injector Plugin for Pelican.

Replaces the third-party pelican-css and pelican-js plugins.
Reads 'CSS' and 'JS' metadata from articles/pages and injects
the corresponding <link> and <script> tags into generated HTML.

Usage in article metadata:
    CSS: asciinema-player.css
    JS: asciinema-player.js (top)

Multiple files can be comma-separated:
    CSS: style1.css, style2.css
    JS: lib.js (top), app.js
"""

import re

from pelican import signals


def inject_css_js(path, context):
    if not path.endswith(".html"):
        return

    article = context.get("article") or context.get("page")
    if article is None:
        return

    # Always use root-relative paths for shared static assets (CSS/JS/images)
    # to avoid i18n_subsites prepending /en/, /fr/, etc. to static file paths
    static_root = ""

    css_meta = getattr(article, "css", None)
    js_meta = getattr(article, "js", None)

    if not css_meta and not js_meta:
        return

    with open(path, encoding="utf-8") as f:
        content = f.read()

    if css_meta:
        css_files = [name.strip() for name in css_meta.split(",")]
        css_tags = "\n".join(
            f'<link rel="stylesheet" href="{static_root}/css/{name}" type="text/css">'
            for name in css_files
        )
        content = content.replace("</head>", f"{css_tags}\n</head>", 1)

    if js_meta:
        for entry in js_meta.split(","):
            entry = entry.strip()
            if "(top)" in entry:
                fname = entry.replace("(top)", "").strip()
                tag = f'<script src="{static_root}/js/{fname}"></script>'
                # Match <body ...> with any attributes
                content = re.sub(r"(<body[^>]*>)", rf"\1\n{tag}", content, count=1)
            else:
                fname = entry.replace("(bottom)", "").strip()
                tag = f'<script src="{static_root}/js/{fname}"></script>'
                content = content.replace("</body>", f"{tag}\n</body>", 1)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def register():
    signals.content_written.connect(inject_css_js)
