# 💻🎸🎞️ Bloggy le Blog 🎦🎼🖥️

Blog technique personnel construit avec [Pelican](https://getpelican.com/) et publié sur [GitHub Pages](https://yoyonel.github.io/).

## Prérequis

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- [just](https://github.com/casey/just) — `cargo install just` ou `brew install just`

## Quick Start

```bash
just setup      # Installe les dépendances + thème
just dev        # Serveur local avec live-reload → http://localhost:8000
```

## Commandes disponibles

| Commande | Description |
|---|---|
| `just setup` | Installe les dépendances et configure le thème |
| `just dev [port]` | Serveur de développement avec live-reload |
| `just build` | Build du site en local |
| `just publish` | Build de production |
| `just deploy` | Publie sur GitHub Pages |
| `just clean` | Supprime le dossier `output/` |
| `just new-post "Mon Titre"` | Crée un nouvel article |

## Structure du projet

```
├── .github/workflows/   # CI/CD GitHub Actions
├── content/             # Articles (Markdown) et assets statiques
│   ├── css/             # CSS custom (ex: asciinema-player)
│   ├── js/              # JS custom (ex: asciinema-player)
│   └── *.md             # Articles
├── plugins/             # Plugins Pelican locaux
│   └── css_js_injector.py
├── themes/
│   └── blueidea-custom/ # Thème (git submodule)
├── Justfile             # Point d'entrée unique
├── pelicanconf.py       # Configuration développement
├── publishconf.py       # Configuration production
└── pyproject.toml       # Dépendances Python
```

## CI/CD

Le workflow GitHub Actions (`.github/workflows/deploy.yml`) déploie automatiquement sur push vers `master`/`main`.

### Configuration du deploy key (une seule fois)

```bash
# Générer une clé SSH dédiée
ssh-keygen -t ed25519 -C "blog-deploy" -f blog_deploy_key -N ""

# Sur le repo yoyonel.github.io :
#   Settings → Deploy keys → Add deploy key (coller la clé publique, cocher "Allow write access")

# Sur le repo blog_source :
#   Settings → Secrets → New repository secret → nom: DEPLOY_KEY (coller la clé privée)
```

## Écrire un article

```bash
just new-post "Mon Nouvel Article"
# Éditer content/mon-nouvel-article.md
just dev
# Visualiser sur http://localhost:8000
```

### Metadata disponibles

```markdown
---
title: Titre de l'article
date: 2024-01-15
description: Description courte
tags: Python, Tutorial
category: Développement
CSS: mon-style.css
JS: mon-script.js (top)
---
```
