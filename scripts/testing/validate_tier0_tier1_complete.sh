#!/usr/bin/env bash
# Complete validation and testing for Tier 0 & Tier 1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"

echo "=================================================="
echo "Complete Tier 0 & Tier 1 Validation & Testing"
echo "=================================================="
echo ""

# Step 1: Check prerequisites
echo "[1/4] Checking prerequisites..."
if uv run --script src/ml/scripts/validate_prerequisites.py --json > /tmp/prereq_check.json 2>&1; then
    echo "✓ Prerequisites check passed"
    cat /tmp/prereq_check.json | python3 -m json.tool | head -20
else
    echo "⚠ Prerequisites check had warnings (continuing)"
    cat /tmp/prereq_check.json | python3 -m json.tool | head -20
fi

echo ""

# Step 2: Run unit tests
echo "[2/4] Running unit tests..."
if uv run pytest src/ml/tests/test_tier0_tier1_validation.py \
    src/ml/tests/test_validate_deck_quality.py \
    src/ml/tests/test_validate_integration.py \
    -v \
    -m "not slow" \
    --tb=short; then
    echo "✓ Unit tests passed"
else
    echo "✗ Unit tests failed"
    exit 1
fi

echo ""

# Step 3: Run integration validation
echo "[3/4] Running integration validation..."
if uv run --script src/ml/scripts/validate_integration.py \
    --game magic \
    --workflow \
    --components \
    --output experiments/integration_validation.json; then
    echo "✓ Integration validation passed"
else
    echo "⚠ Integration validation had warnings (non-blocking)"
fi

echo ""

# Step 4: Run full validation (optional, can be slow)
echo "[4/4] Running full Tier 0 & Tier 1 validation..."
echo "  (Skipping slow deck validation by default)"
if uv run --script src/ml/scripts/run_all_tier0_tier1.py \
    --game magic \
    --num-decks 10 \
    --skip-deck-validation \
    --check-prerequisites; then
    echo "✓ Full validation passed"
else
    echo "⚠ Full validation had warnings (non-blocking)"
fi

echo ""
echo "=================================================="
echo "Validation & Testing Complete"
echo "=================================================="
echo ""
echo "Results:"
echo "  - Prerequisites: /tmp/prereq_check.json"
echo "  - Integration: experiments/integration_validation.json"
echo "  - Full validation: experiments/tier0_tier1_validation.json"
echo "  - Dashboard: experiments/quality_dashboard.html"
echo ""

