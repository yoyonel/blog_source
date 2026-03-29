---
title: Moderniser un blog Pelican en 2026 — Architecture, Stack & CI/CD
slug: modernisation-blog-pelican-2026
lang: fr
date: 2026-03-29
description: Retour d'expérience sur la modernisation complète d'un blog technique Pelican — de la gestion des dépendances au déploiement automatisé sur GitHub Pages.
tags: Pelican, Python, GitHub Actions, CI/CD, uv, Justfile, Blog
category: Développement
---

# Moderniser un blog Pelican en 2026

Ce blog existe depuis 2020. Il a été construit à l'époque avec une stack qui fonctionnait, mais qui n'a pas bien vieilli : `requirements.txt` sans versions pinées, 6 scripts shell, un `Makefile` généré par Pelican, des plugins tiers abandonnés, un thème datant de 2013, et un déploiement entièrement manuel.

Voici le retour d'expérience sur sa modernisation complète.

---

## L'état des lieux (avant)

Le projet souffrait de plusieurs problèmes :

| Problème | Détail |
|---|---|
| **Dépendances** | `requirements.txt` avec 3 lignes (`pelican`, `Markdown`, `punch.py`), aucune version pinée |
| **Scripts** | 6 scripts shell (`setup.sh`, `deploy.sh`, `publish.sh`, `release.sh`, `add_extras_*.sh`) |
| **Structure** | Contenu imbriqué dans `pelican/content/`, config dans `pelican/` |
| **Plugins** | `pelican-css` et `pelican-js` (repos tiers sur notabug.org, plus maintenus) |
| **Thème** | blueidea-custom — CSS de 2013, pas responsive, largeur fixe, police Trebuchet MS |
| **Déploiement** | Manuel : `make publish` → copie dans un dossier `deploy/` → `git push` |
| **Versioning** | `punch.py` pour gérer un numéro de version (inutile pour un blog) |
| **Workflow** | git-flow (overkill pour un blog personnel) |

---

## La nouvelle stack

### Python : `uv` au lieu de pip/poetry

[uv](https://docs.astral.sh/uv/) est un gestionnaire de paquets Python écrit en Rust, rapide et tout-en-un. Il remplace `pip`, `pip-tools`, `virtualenv` et `poetry` avec un seul outil.

Le fichier `pyproject.toml` minimal :

```toml
[project]
name = "blog-source"
version = "1.0.0"
description = "Bloggy le Blog - Blog technique avec Pelican"
requires-python = ">=3.10"
dependencies = [
    "pelican[markdown]>=4.9",
    "ghp-import>=2.1",
]
```

Installation en une commande :

```bash
uv sync  # Crée le venv, résout les dépendances, installe tout
```

Sur un runner GitHub Actions, `uv sync` prend **~2 secondes** contre 15-30s avec pip.

### Task runner : `Justfile` au lieu de Make + scripts shell

[just](https://github.com/casey/just) est un command runner moderne (écrit en Rust) qui remplace `make` pour les tâches de projet. Contrairement à Make, il n'a pas de système de dépendances de fichiers — c'est juste un lanceur de commandes avec une syntaxe propre.

Le `Justfile` complet du projet :

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

L'avantage par rapport à 6 scripts shell indépendants : **un seul point d'entrée**, auto-documenté (`just --list`), avec des paramètres nommés et des valeurs par défaut.

### Thème : Flex

[Flex](https://github.com/alexandrevicenzi/Flex) est le thème Pelican le plus populaire et maintenu. Il apporte :

- **Responsive** mobile-first
- **Dark mode** automatique (suit `prefers-color-scheme` de l'OS)
- **Syntax highlighting** avec Pygments (thème light/dark séparé)
- **SEO** : balises OpenGraph, meta description
- Config via des variables Python dans `pelicanconf.py` :

```python
THEME = "themes/Flex"

# Dark mode auto-detect
THEME_COLOR_AUTO_DETECT_BROWSER_PREFERENCE = True
THEME_COLOR_ENABLE_USER_OVERRIDE = True

# Syntax highlighting
PYGMENTS_STYLE = "github"         # thème clair
PYGMENTS_STYLE_DARK = "monokai"   # thème sombre
```

Le thème est intégré comme **git submodule**, ce qui permet de le mettre à jour indépendamment et de garder un historique propre.

### Plugin local : `css_js_injector`

Les anciens plugins `pelican-css` et `pelican-js` (repos tiers) utilisaient des hacks fragiles avec des constantes magiques pour injecter du CSS/JS dans les templates. Ils ne sont plus maintenus.

Le remplacement tient en **~40 lignes de Python** :

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

Le principe : Pelican émet un signal `content_written` après avoir généré chaque fichier HTML. Le plugin intercepte ce signal, lit les metadata `CSS` et `JS` de l'article, et injecte les balises `<link>` / `<script>` aux bons endroits dans le HTML.

Utilisation dans un article :

```markdown
---
title: Mon article
CSS: asciinema-player.css
JS: asciinema-player.js (top)
---
```

Un point technique à noter : le remplacement de `<body>` nécessite une regex (`<body[^>]*>`) car les thèmes ajoutent des attributs (`class`, `id`) sur la balise.

---

## CI/CD : GitHub Actions

### Déploiement automatique

Chaque push sur `master` déclenche un build + deploy :

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

Le temps total du pipeline : **~25 secondes** (dont ~15s pour le checkout des submodules).

### Preview de PR sur surge.sh

Chaque Pull Request génère automatiquement une preview sur [surge.sh](https://surge.sh/) avec un commentaire bot contenant l'URL :

```
🚀 Preview deployed!
https://blog-source-pr-1.surge.sh
```

Le workflow utilise une variable d'environnement `PELICAN_SITEURL` pour overrider le `SITEURL` de production :

```python
# publishconf.py
SITEURL = os.environ.get("PELICAN_SITEURL", "https://yoyonel.github.io")
```

Cela permet au même `publishconf.py` de servir à la fois pour la production et pour les previews, sans duplication de configuration.

---

## Structure finale du projet

```
├── .github/workflows/
│   ├── deploy.yml          # Deploy sur push master
│   └── preview.yml         # Preview PR via surge.sh
├── content/
│   ├── css/                # CSS custom (assets statiques)
│   ├── js/                 # JS custom
│   └── *.md                # Articles en Markdown
├── plugins/
│   └── css_js_injector.py  # Plugin CSS/JS local
├── themes/
│   └── Flex/               # Thème (git submodule)
├── Justfile                # Point d'entrée unique
├── pelicanconf.py          # Config dev
├── publishconf.py          # Config production
└── pyproject.toml          # Dépendances Python
```

Comparé à avant : **11 fichiers de config/scripts** réduits à **4** (`pyproject.toml`, `pelicanconf.py`, `publishconf.py`, `Justfile`).

---

## Ce que ça donne au quotidien

Écrire un article :

```bash
just new-post "Mon Super Article"
just dev
# → http://localhost:8000 avec live-reload
```

Publier :

```bash
git add content/mon-super-article.md
git commit -m "article: mon super article"
git push
# → GitHub Actions build + deploy automatiquement
```

C'est tout. Pas de `make publish && cd deploy && git add . && git commit && git push`. Pas de virtualenv à activer manuellement. Pas de thème à installer dans le venv. Le blog se déploie en **25 secondes** sur chaque push.

---

## Reproduire cette stack

Pour construire un blog similaire from scratch :

1. **Pelican** + **Markdown** : le moteur de blog statique
2. **uv** : gestion des dépendances Python
3. **just** : task runner
4. **Flex** : thème responsive avec dark mode
5. **GitHub Actions** + **JamesIves/github-pages-deploy-action** : CI/CD
6. **surge.sh** : preview de PR

Le tout est open source : [yoyonel/blog_source](https://github.com/yoyonel/blog_source).
