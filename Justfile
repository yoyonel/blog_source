# Blog - Justfile
# Single entry point for all blog operations

set dotenv-load
set positional-arguments

DEPLOY_REMOTE := "git@github.com:yoyonel/yoyonel.github.io.git"

# Show available recipes
default:
    @just --list

# Install dependencies and setup theme
setup:
    uv sync
    npm install
    git submodule update --init --recursive
    uv run pre-commit install
    @git remote get-url deploy 2>/dev/null || git remote add deploy {{ DEPLOY_REMOTE }}
    @echo "✅ Setup complete. Run 'just dev' to start the dev server."

# Run ruff linter
lint:
    uv run ruff check .
    npx @biomejs/biome check .

# Run ruff formatter check
format-check:
    uv run ruff format --check .
    npx @biomejs/biome format .

# Auto-fix lint + format
fix:
    uv run ruff check --fix .
    uv run ruff format .
    npx @biomejs/biome check --fix .

# Start dev server with live-reload (default port 8000)
dev port="8000":
    uv run pelican content -o output -s pelicanconf.py -lr -p {{ port }}

# Build site for local preview
build:
    uv run pelican content -o output -s pelicanconf.py

# Build site for production
publish:
    uv run pelican content -o output -s publishconf.py

# Run Lighthouse performance audit (builds if needed)
audit page="suckless-ogl-anatomie-frame.html":
    ./scripts/lighthouse-audit.sh {{ page }}

# Clean generated output
clean:
    rm -rf output

# Deploy to GitHub Pages (builds then pushes to yoyonel.github.io)
deploy: publish
    uv run ghp-import output -b main -r deploy -p -f
    @echo "🚀 Deployed to GitHub Pages"

# Create a new article
new-post title:
    #!/usr/bin/env bash
    set -euo pipefail
    slug=$(echo "{{ title }}" | iconv -t ascii//TRANSLIT | tr '[:upper:]' '[:lower:]' | tr ' ' '-' | sed 's/[^a-z0-9-]//g')
    date=$(date +%Y-%m-%d)
    target="content/${slug}.md"
    if [[ -f "$target" ]]; then
        echo "❌ File already exists: $target"
        exit 1
    fi
    cat > "$target" << EOF
    ---
    title: {{ title }}
    date: ${date}
    description:
    tags:
    category: Développement
    ---

    # {{ title }}
    EOF
    echo "📝 Created ${target}"
