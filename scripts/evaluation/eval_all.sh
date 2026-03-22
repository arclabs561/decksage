#!/usr/bin/env bash
set -euo pipefail
#
# Run all evaluations for an embedding.
#
# Usage:
#   ./scripts/evaluation/eval_all.sh magic metapath2vec         # Offline only
#   ./scripts/evaluation/eval_all.sh magic metapath2vec --api    # Offline + API evals
#
# Outputs JSON results to data/logs/{game}_{embedding}_eval.json

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

GAME="${1:?Usage: eval_all.sh <game> <embedding> [--api]}"
EMBEDDING="${2:?Usage: eval_all.sh <game> <embedding> [--api]}"
API_MODE="${3:-}"
API_URL="${API_URL:-http://localhost:8001}"

LOGS_DIR="$PROJECT_ROOT/data/logs"
mkdir -p "$LOGS_DIR"
OUT="$LOGS_DIR/${GAME}_${EMBEDDING}_eval.json"

echo "=== Eval: $GAME / $EMBEDDING ==="
echo ""

# 1. Per-mode nDCG (offline, always runs)
echo "[1/4] Per-mode nDCG..."
PERMODE=$(uv run "$SCRIPT_DIR/eval_per_mode.py" --game "$GAME" --embedding "$EMBEDDING" --json 2>/dev/null)
if [ -n "$PERMODE" ]; then
    echo "  OK"
else
    echo "  FAILED"
    PERMODE="{}"
fi

# API-dependent evals
CONTEXTUAL="{}"
SEARCH="{}"
COMPLETION="{}"

if [ "$API_MODE" = "--api" ]; then
    # Check API is reachable
    if ! curl -sf "$API_URL/live" >/dev/null 2>&1; then
        echo ""
        echo "  API not reachable at $API_URL -- skipping API evals"
        echo "  Start with: uv run src/ml/api/api.py"
        API_MODE=""
    fi
fi

if [ "$API_MODE" = "--api" ]; then
    # 2. Contextual recall
    echo "[2/4] Contextual recall..."
    CONTEXTUAL=$(uv run "$SCRIPT_DIR/eval_contextual.py" --game "$GAME" --api-url "$API_URL" --json 2>/dev/null) || CONTEXTUAL="{}"
    echo "  OK"

    # 3. Search relevance
    echo "[3/4] Search relevance..."
    SEARCH=$(uv run "$SCRIPT_DIR/eval_search_relevance.py" --game "$GAME" --api-url "$API_URL" --json 2>/dev/null) || SEARCH="{}"
    echo "  OK"

    # 4. Deck completion
    echo "[4/4] Deck completion..."
    COMPLETION=$(uv run "$SCRIPT_DIR/eval_deck_completion.py" --game "$GAME" --api-url "$API_URL" --json 2>/dev/null) || COMPLETION="{}"
    echo "  OK"
else
    echo "[2-4] Skipped (no --api flag)"
fi

# Combine results via temp files (avoids fragile shell JSON interpolation)
TMPDIR=$(mktemp -d)
echo "$PERMODE" > "$TMPDIR/permode.json"
echo "$CONTEXTUAL" > "$TMPDIR/contextual.json"
echo "$SEARCH" > "$TMPDIR/search.json"
echo "$COMPLETION" > "$TMPDIR/completion.json"

python3 -c "
import json, sys, pathlib
tmpdir = pathlib.Path('$TMPDIR')
def safe_load(p):
    try:
        text = p.read_text().strip()
        return json.loads(text) if text else {}
    except (json.JSONDecodeError, FileNotFoundError):
        return {}
result = {
    'game': '$GAME',
    'embedding': '$EMBEDDING',
    'per_mode': safe_load(tmpdir / 'permode.json'),
    'contextual': safe_load(tmpdir / 'contextual.json'),
    'search': safe_load(tmpdir / 'search.json'),
    'deck_completion': safe_load(tmpdir / 'completion.json'),
}
with open('$OUT', 'w') as f:
    json.dump(result, f, indent=2)
print(f'Wrote $OUT')
"
rm -rf "$TMPDIR"

echo ""
echo "=== Summary ==="

# Print key metrics
python3 -c "
import json
with open('$OUT') as f:
    r = json.load(f)
pm = r.get('per_mode', {})
if isinstance(pm, list): pm = pm[0] if pm else {}
sub = pm.get('mode_substitute', {}).get('ndcg_at_k', 'N/A')
syn = pm.get('mode_synergy', {}).get('ndcg_at_k', 'N/A')
meta = pm.get('mode_meta', {}).get('ndcg_at_k', 'N/A')
print(f'  sub nDCG:  {sub}')
print(f'  syn nDCG:  {syn}')
print(f'  meta nDCG: {meta}')

ctx = r.get('contextual', {})
if ctx:
    recall = ctx.get('overall_recall', ctx.get('recall', 'N/A'))
    print(f'  contextual recall: {recall}')

srch = r.get('search', {})
if srch:
    mrr = srch.get('mrr', 'N/A')
    print(f'  search MRR: {mrr}')
"
