"""
HTML Optimizer Plugin for Pelican.

Post-processes generated HTML to:
1. Inject <link rel="preconnect"> hints for external font domains
   (eliminates DNS+TCP+TLS round-trips before font CSS is fetched)
2. Lazy-load SVG-heavy <pre class="mermaid"> blocks below the fold
   via IntersectionObserver (reduces initial Paint cost)
"""

import re

from pelican import signals

# Preconnect hints to inject early in <head>
_PRECONNECT_DOMAINS = [
    "https://fonts.googleapis.com",
    "https://fonts.gstatic.com",
]

_PRECONNECT_HTML = "\n".join(
    f'  <link rel="preconnect" href="{d}" crossorigin>' for d in _PRECONNECT_DOMAINS
)

# Match <pre class="mermaid"> blocks with their SVG content
_MERMAID_PRE_RE = re.compile(
    r'(<pre\s+class="mermaid">)(.*?)(</pre>)',
    re.DOTALL,
)

# Inline script for lazy-loading mermaid SVGs via IntersectionObserver
_LAZY_SVG_SCRIPT = """<script>
(function(){
  var pres=document.querySelectorAll('pre.mermaid[data-lazy-svg]');
  if(!pres.length) return;
  function reveal(pre){
    var t=pre.querySelector('template');
    if(t){pre.replaceChild(t.content,t);pre.removeAttribute('data-lazy-svg');}
  }
  if(!('IntersectionObserver' in window)){
    pres.forEach(reveal);return;
  }
  var io=new IntersectionObserver(function(entries){
    entries.forEach(function(e){
      if(e.isIntersecting){reveal(e.target);io.unobserve(e.target);}
    });
  },{rootMargin:'400px'});
  pres.forEach(function(p){io.observe(p);});
})();
</script>"""

# How many mermaid diagrams to keep eager (above the fold)
_EAGER_COUNT = 2


def optimize_html(path, context):
    """Post-process generated HTML with preconnect and lazy SVGs."""
    if not path.endswith(".html"):
        return

    with open(path, encoding="utf-8") as f:
        content = f.read()

    modified = False

    # 1. Inject preconnect hints right after <head> (before font CSS)
    if "fonts.googleapis.com" in content and "preconnect" not in content:
        content = content.replace("<head>\n", f"<head>\n{_PRECONNECT_HTML}\n", 1)
        modified = True

    # 2. Lazy-load mermaid SVGs below the fold
    matches = list(_MERMAID_PRE_RE.finditer(content))
    if len(matches) > _EAGER_COUNT:
        # Process in reverse to preserve offsets
        for i, m in enumerate(reversed(matches)):
            idx = len(matches) - 1 - i
            if idx < _EAGER_COUNT:
                continue  # Keep first N diagrams eager
            open_tag, svg_content, close_tag = m.group(1), m.group(2), m.group(3)
            # Wrap SVG in <template> (not parsed/rendered until revealed)
            placeholder = (
                f"{open_tag[:-1]} data-lazy-svg>"
                f"<template>{svg_content}</template>"
                f"{close_tag}"
            )
            content = content[: m.start()] + placeholder + content[m.end() :]
        # Inject the reveal script before </body>
        content = content.replace("</body>", _LAZY_SVG_SCRIPT + "\n</body>", 1)
        modified = True

    if modified:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


def register():
    signals.content_written.connect(optimize_html)
