---
title: Modernizing a Pelican Blog in 2026 — Architecture, Stack & CI/CD
slug: modernisation-blog-pelican-2026
lang: en
date: 2026-03-29
description: Lessons learned from a complete modernization of a technical Pelican blog — from dependency management to automated deployment on GitHub Pages.
tags: Pelican, Python, GitHub Actions, CI/CD, uv, Justfile, Blog
category: Development
---

# Modernizing a Pelican Blog in 2026

This blog has been around since 2020. It was built with a stack that worked back then, but didn't age well: an unpinned `requirements.txt`, 6 shell scripts, a Pelican-generated `Makefile`, abandoned third-party plugins, a theme from 2013, and fully manual deployment.

Here's the full story of its modernization.

---

## The Starting Point (Before)

The project suffered from several issues:

| Problem | Details |
|---|---|
| **Dependencies** | `requirements.txt` with 3 lines (`pelican`, `Markdown`, `punch.py`), no pinned versions |
| **Scripts** | 6 shell scripts (`setup.sh`, `deploy.sh`, `publish.sh`, `release.sh`, `add_extras_*.sh`) |
| **Structure** | Content nested in `pelican/content/`, config in `pelican/` |
| **Plugins** | `pelican-css` and `pelican-js` (third-party repos on notabug.org, unmaintained) |
| **Theme** | blueidea-custom — 2013 CSS, not responsive, fixed width, Trebuchet MS font |
| **Deployment** | Manual: `make publish` → copy to a `deploy/` folder → `git push` |
| **Versioning** | `punch.py` for managing a version number (useless for a blog) |
| **Workflow** | git-flow (overkill for a personal blog) |

---

## The New Stack

### Python: `uv` Instead of pip/poetry

[uv](https://docs.astral.sh/uv/) is a Python package manager written in Rust — fast and all-in-one. It replaces `pip`, `pip-tools`, `virtualenv`, and `poetry` with a single tool.

The minimal `pyproject.toml`:

```toml
[project]
name = "blog-source"
version = "1.0.0"
description = "Bloggy le Blog - Technical blog with Pelican"
requires-python = ">=3.10"
dependencies = [
    "pelican[markdown]>=4.9",
    "ghp-import>=2.1",
]
```

One-command install:

```bash
uv sync  # Creates the venv, resolves dependencies, installs everything
```

On a GitHub Actions runner, `uv sync` takes **~2 seconds** vs 15-30s with pip.

### Task Runner: `Justfile` Instead of Make + Shell Scripts

[just](https://github.com/casey/just) is a modern command runner (written in Rust) that replaces `make` for project tasks. Unlike Make, it has no file dependency system — it's just a command launcher with clean syntax.

The complete project `Justfile`:

```just
set dotenv-load
set positional-arguments

# Show available recipes
default:
    @just --list

# Install dependencies and setup theme
setup:
    uv sync
    git submodule update --init --recursive

# Start dev server with live-reload
dev port="8000":
    uv run pelican content -o output -s pelicanconf.py -lr -p {{ port }}

# Build for production
publish:
    uv run pelican content -o output -s publishconf.py

# Deploy to GitHub Pages
deploy: publish
    uv run ghp-import output -b main -r deploy -p -f
```

The advantage over 6 independent shell scripts: **a single entry point**, self-documenting (`just --list`), with named parameters and default values.

### Theme: Flex

[Flex](https://github.com/alexandrevicenzi/Flex) is the most popular and actively maintained Pelican theme. It provides:

- **Responsive** mobile-first design
- **Dark mode** auto-detect (follows the OS `prefers-color-scheme`)
- **Syntax highlighting** with Pygments (separate light/dark themes)
- **SEO**: OpenGraph tags, meta description
- Configuration via Python variables in `pelicanconf.py`:

```python
THEME = "themes/Flex"

# Dark mode auto-detect
THEME_COLOR_AUTO_DETECT_BROWSER_PREFERENCE = True
THEME_COLOR_ENABLE_USER_OVERRIDE = True

# Syntax highlighting
PYGMENTS_STYLE = "github"         # light theme
PYGMENTS_STYLE_DARK = "monokai"   # dark theme
```

The theme is integrated as a **git submodule**, allowing independent updates and a clean history.

### Local Plugin: `css_js_injector`

The old `pelican-css` and `pelican-js` plugins (third-party repos) used fragile hacks with magic constants to inject CSS/JS into templates. They are no longer maintained.

The replacement fits in **~40 lines of Python**:

```python
import re
from pelican import signals

def inject_css_js(path, context):
    if not path.endswith(".html"):
        return

    article = context.get("article") or context.get("page")
    if article is None:
        return

    siteurl = context.get("SITEURL", "")
    css_meta = getattr(article, "css", None)
    js_meta = getattr(article, "js", None)

    if not css_meta and not js_meta:
        return

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    if css_meta:
        for name in css_meta.split(","):
            tag = f'<link rel="stylesheet" href="{siteurl}/css/{name.strip()}" type="text/css">'
            content = content.replace("</head>", f"{tag}\n</head>", 1)

    if js_meta:
        for entry in js_meta.split(","):
            entry = entry.strip()
            if "(top)" in entry:
                fname = entry.replace("(top)", "").strip()
                tag = f'<script src="{siteurl}/js/{fname}"></script>'
                content = re.sub(r"(<body[^>]*>)", rf"\1\n{tag}", content, count=1)
            else:
                fname = entry.replace("(bottom)", "").strip()
                tag = f'<script src="{siteurl}/js/{fname}"></script>'
                content = content.replace("</body>", f"{tag}\n</body>", 1)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def register():
    signals.content_written.connect(inject_css_js)
```

How it works: Pelican emits a `content_written` signal after generating each HTML file. The plugin intercepts this signal, reads the `CSS` and `JS` metadata from the article, and injects `<link>` / `<script>` tags at the right locations in the HTML.

Usage in an article:

```markdown
---
title: My article
CSS: asciinema-player.css
JS: asciinema-player.js (top)
---
```

A technical note: the `<body>` replacement requires a regex (`<body[^>]*>`) because themes add attributes (`class`, `id`) to the body tag.

---

## CI/CD: GitHub Actions

### Automatic Deployment

Every push to `master` triggers a build + deploy:

```yaml
name: Deploy Blog
on:
  push:
    branches: [master, main]

jobs:
  build-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: recursive

      - uses: astral-sh/setup-uv@v4
      - run: uv sync
      - run: uv run pelican content -o output -s publishconf.py

      - uses: JamesIves/github-pages-deploy-action@v4
        with:
          repository-name: yoyonel/yoyonel.github.io
          branch: master
          folder: output
          ssh-key: ${{ secrets.DEPLOY_KEY }}
```

Total pipeline time: **~25 seconds** (including ~15s for submodule checkout).

### PR Preview on surge.sh

Every Pull Request automatically generates a preview on [surge.sh](https://surge.sh/) with a bot comment containing the URL:

```
🚀 Preview deployed!
https://blog-source-pr-1.surge.sh
```

The workflow uses a `PELICAN_SITEURL` environment variable to override the production `SITEURL`:

```python
# publishconf.py
SITEURL = os.environ.get("PELICAN_SITEURL", "https://yoyonel.github.io")
```

This allows the same `publishconf.py` to serve both production and previews, without duplicating configuration.

---

## Final Project Structure

```
├── .github/workflows/
│   ├── deploy.yml          # Deploy on push to master
│   └── preview.yml         # PR preview via surge.sh
├── content/
│   ├── css/                # Custom CSS (static assets)
│   ├── js/                 # Custom JS
│   └── *.md                # Markdown articles
├── plugins/
│   └── css_js_injector.py  # Local CSS/JS plugin
├── themes/
│   └── Flex/               # Theme (git submodule)
├── Justfile                # Single entry point
├── pelicanconf.py          # Dev config
├── publishconf.py          # Production config
└── pyproject.toml          # Python dependencies
```

Compared to before: **11 config/script files** reduced to **4** (`pyproject.toml`, `pelicanconf.py`, `publishconf.py`, `Justfile`).

---

## Day-to-Day Workflow

Writing an article:

```bash
just new-post "My Awesome Article"
just dev
# → http://localhost:8000 with live-reload
```

Publishing:

```bash
git add content/my-awesome-article.md
git commit -m "article: my awesome article"
git push
# → GitHub Actions builds + deploys automatically
```

That's it. No `make publish && cd deploy && git add . && git commit && git push`. No manually activating a virtualenv. No installing the theme into the venv. The blog deploys in **25 seconds** on every push.

---

## Reproducing This Stack

To build a similar blog from scratch:

1. **Pelican** + **Markdown**: the static blog engine
2. **uv**: Python dependency management
3. **just**: task runner
4. **Flex**: responsive theme with dark mode
5. **GitHub Actions** + **JamesIves/github-pages-deploy-action**: CI/CD
6. **surge.sh**: PR preview

Everything is open source: [yoyonel/blog_source](https://github.com/yoyonel/blog_source).
