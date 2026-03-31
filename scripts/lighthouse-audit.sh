#!/usr/bin/env bash
# Run Lighthouse performance audit on locally-served blog pages.
# Usage: ./scripts/lighthouse-audit.sh [page-slug]
# Default: audits the heaviest page (suckless-ogl-anatomie-frame.html)
set -euo pipefail

SLUG="${1:-suckless-ogl-anatomie-frame.html}"
PORT=9222
OUTPUT_DIR="lighthouse-reports"
CHROMIUM=$(which chromium 2>/dev/null || which chromium-browser 2>/dev/null || echo "")

if [[ -z "$CHROMIUM" ]]; then
  echo "❌ chromium not found in PATH"
  exit 1
fi

# Build if output doesn't exist
if [[ ! -d "output" ]]; then
  echo "📦 Building site..."
  uv run pelican content -o output -s pelicanconf.py
fi

mkdir -p "$OUTPUT_DIR"

# Start a local HTTP server in background
python3 -m http.server "$PORT" -d output &>/dev/null &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null; exit' INT TERM EXIT
sleep 1

URL="http://localhost:${PORT}/${SLUG}"
REPORT_JSON="${OUTPUT_DIR}/${SLUG%.html}.report.json"
REPORT_HTML="${OUTPUT_DIR}/${SLUG%.html}.report.html"

echo "🔍 Auditing ${URL} ..."

npx lighthouse "$URL" \
  --chrome-flags="--headless --no-sandbox --disable-gpu" \
  --chrome-path="$CHROMIUM" \
  --output=json,html \
  --output-path="${OUTPUT_DIR}/${SLUG%.html}" \
  --only-categories=performance \
  --throttling-method=simulate \
  --preset=desktop \
  --quiet 2>&1

# Extract key metrics from JSON
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Core Web Vitals — ${SLUG}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

python3 -c "
import json, sys
with open('${REPORT_JSON}') as f:
    r = json.load(f)
a = r['audits']

metrics = [
    ('Performance Score', r['categories']['performance']['score'] * 100, '', 90, True),
    ('First Contentful Paint', a['first-contentful-paint']['numericValue']/1000, 's', 1.8, False),
    ('Largest Contentful Paint', a['largest-contentful-paint']['numericValue']/1000, 's', 2.5, False),
    ('Total Blocking Time', a['total-blocking-time']['numericValue'], 'ms', 200, False),
    ('Cumulative Layout Shift', a['cumulative-layout-shift']['numericValue'], '', 0.1, False),
    ('Speed Index', a['speed-index']['numericValue']/1000, 's', 3.4, False),
]

for name, val, unit, threshold, higher_better in metrics:
    if higher_better:
        icon = '🟢' if val >= threshold else ('🟠' if val >= threshold * 0.5 else '🔴')
    else:
        icon = '🟢' if val <= threshold else ('🟠' if val <= threshold * 1.5 else '🔴')
    print(f'  {icon} {name:30s} {val:>8.2f}{unit}  (good: {\"≥\" if higher_better else \"≤\"}{threshold}{unit})')
"

echo ""
echo "📄 Full report: ${REPORT_HTML}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Compare with baseline if it exists
BASELINE="${OUTPUT_DIR}/baseline-before-profiler-fixes.json"
if [[ -f "$BASELINE" && "$REPORT_JSON" != "$BASELINE" ]]; then
  echo ""
  echo "📈 Comparison with baseline:"
  python3 << PYEOF
import json
with open('${BASELINE}') as f:
    old = json.load(f)
with open('${REPORT_JSON}') as f:
    new = json.load(f)
oa, na = old['audits'], new['audits']

metrics = [
    ('Performance Score', 'score', 100, '', True),
    ('FCP', 'first-contentful-paint', 0.001, 's', False),
    ('LCP', 'largest-contentful-paint', 0.001, 's', False),
    ('TBT', 'total-blocking-time', 1, 'ms', False),
    ('CLS', 'cumulative-layout-shift', 1, '', False),
    ('Speed Index', 'speed-index', 0.001, 's', False),
]

for name, key, mult, unit, higher_better in metrics:
    if key == 'score':
        ov = old['categories']['performance']['score'] * 100
        nv = new['categories']['performance']['score'] * 100
    else:
        ov = oa[key]['numericValue'] * mult
        nv = na[key]['numericValue'] * mult
    diff = nv - ov
    if higher_better:
        icon = '📈' if diff > 0 else ('📉' if diff < 0 else '➡️')
    else:
        icon = '📈' if diff < 0 else ('📉' if diff > 0 else '➡️')
    print(f'  {icon} {name:20s}  {ov:>8.2f}{unit} → {nv:>8.2f}{unit}  ({diff:+.2f}{unit})')
PYEOF
fi
