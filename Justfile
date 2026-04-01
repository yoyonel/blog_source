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

# Default page to audit (heaviest page)
audit_slug := "suckless-ogl-anatomie-frame.html"
audit_port := "9222"

# Run a Lighthouse performance audit on the local build
audit page=audit_slug: build
    #!/usr/bin/env bash
    set -euo pipefail
    CHROMIUM_PATH=$(which chromium 2>/dev/null || which chromium-browser 2>/dev/null || echo "")
    if [[ -z "$CHROMIUM_PATH" ]]; then
        echo "❌ chromium not found. Install it first."
        exit 1
    fi
    python3 -m http.server {{ audit_port }} -d output &>/dev/null &
    SERVER_PID=$!
    trap "kill $SERVER_PID 2>/dev/null" EXIT
    sleep 2
    # Verify server is responding
    curl -sf "http://localhost:{{ audit_port }}/{{ page }}" -o /dev/null || { echo "❌ Server not responding"; exit 1; }
    echo "🔍 Running Lighthouse on {{ page }}..."
    mkdir -p lighthouse-reports
    npx lighthouse "http://localhost:{{ audit_port }}/{{ page }}" \
        --chrome-flags="--headless=new --no-sandbox --disable-gpu --disable-dev-shm-usage" \
        --chrome-path="$CHROMIUM_PATH" \
        --output=json --output=html \
        --output-path="lighthouse-reports/$(echo '{{ page }}' | sed 's/\.html//')" \
        --only-categories=performance \
        --throttling-method=simulate \
        --preset=desktop \
        2>&1 | grep -E "^(Runtime|LH:Printer)" || true
    python3 -c "
    import json, glob
    files = sorted(glob.glob('lighthouse-reports/*.report.json'))
    if not files:
        print('❌ No report found')
        exit(1)
    with open(files[-1]) as f:
        r = json.load(f)
    a = r['audits']
    score = r['categories']['performance']['score'] * 100
    def fmt(key, div=1): return a[key]['numericValue'] / div
    print()
    print(f'  Score:  {score:.0f}')
    print(f'  FCP:    {fmt(\"first-contentful-paint\", 1000):.2f}s')
    print(f'  LCP:    {fmt(\"largest-contentful-paint\", 1000):.2f}s')
    print(f'  TBT:    {fmt(\"total-blocking-time\"):.0f}ms')
    print(f'  CLS:    {fmt(\"cumulative-layout-shift\"):.3f}')
    print(f'  SI:     {fmt(\"speed-index\", 1000):.2f}s')
    print()
    html = files[-1].replace('.report.json', '.report.html')
    print(f'  📄 JSON: {files[-1]}')
    print(f'  📄 HTML: {html}')
    "

# Run 3 Lighthouse audits and show median (more stable)
audit-median page=audit_slug: build
    #!/usr/bin/env bash
    set -euo pipefail
    CHROMIUM_PATH=$(which chromium 2>/dev/null || which chromium-browser 2>/dev/null || echo "")
    if [[ -z "$CHROMIUM_PATH" ]]; then
        echo "❌ chromium not found. Install it first."
        exit 1
    fi
    python3 -m http.server {{ audit_port }} -d output &>/dev/null &
    SERVER_PID=$!
    trap "kill $SERVER_PID 2>/dev/null" EXIT
    sleep 2
    curl -sf "http://localhost:{{ audit_port }}/{{ page }}" -o /dev/null || { echo "❌ Server not responding"; exit 1; }
    mkdir -p lighthouse-reports
    echo "🔍 Running 3 Lighthouse audits on {{ page }}..."
    for i in 1 2 3; do
        echo "  Run $i/3..."
        npx lighthouse "http://localhost:{{ audit_port }}/{{ page }}" \
            --chrome-flags="--headless=new --no-sandbox --disable-gpu --disable-dev-shm-usage" \
            --chrome-path="$CHROMIUM_PATH" \
            --output=json \
            --output-path="lighthouse-reports/run-${i}" \
            --only-categories=performance \
            --throttling-method=simulate \
            --preset=desktop \
            2>&1 | grep -E "^(Runtime|LH:Printer)" || true
    done
    python3 -c "
    import json, statistics, os
    metrics = {'perf': [], 'fcp': [], 'lcp': [], 'tbt': [], 'cls': [], 'si': []}
    for i in range(1, 4):
        for path in [f'lighthouse-reports/run-{i}', f'lighthouse-reports/run-{i}.report.json']:
            if os.path.isfile(path):
                break
        with open(path) as f:
            r = json.load(f)
        a = r['audits']
        metrics['perf'].append(r['categories']['performance']['score'] * 100)
        metrics['fcp'].append(a['first-contentful-paint']['numericValue'] / 1000)
        metrics['lcp'].append(a['largest-contentful-paint']['numericValue'] / 1000)
        metrics['tbt'].append(a['total-blocking-time']['numericValue'])
        metrics['cls'].append(a['cumulative-layout-shift']['numericValue'])
        metrics['si'].append(a['speed-index']['numericValue'] / 1000)
    med = {k: statistics.median(v) for k, v in metrics.items()}
    def status(val, good, hb=False):
        if hb: return '🟢' if val >= good else ('🟠' if val >= good * 0.5 else '🔴')
        return '🟢' if val <= good else ('🟠' if val <= good * 1.5 else '🔴')
    print()
    print('  Lighthouse Performance Audit — median of 3 runs (desktop)')
    print('  ─────────────────────────────────────────────────────────')
    rows = [
        ('Score', med['perf'], '',   90,  True),
        ('FCP',   med['fcp'],  's',  1.8, False),
        ('LCP',   med['lcp'],  's',  2.5, False),
        ('TBT',   med['tbt'],  'ms', 200, False),
        ('CLS',   med['cls'],  '',   0.1, False),
        ('SI',    med['si'],   's',  3.4, False),
    ]
    for name, val, unit, target, hb in rows:
        s = status(val, target, hb)
        print(f'  {s} {name:6s} {val:>8.2f}{unit}  (target: {\"≥\" if hb else \"≤\"} {target}{unit})')
    print()
    "
