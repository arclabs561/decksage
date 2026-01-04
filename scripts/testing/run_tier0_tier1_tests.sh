#!/usr/bin/env bash
# Run tests for Tier 0 & Tier 1 validation scripts

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"

echo "=================================================="
echo "Tier 0 & Tier 1 Validation Tests"
echo "=================================================="
echo ""

# Run tests
echo "[1/2] Running unit tests..."
if uv run pytest src/ml/tests/test_tier0_tier1_validation.py \
    src/ml/tests/test_validate_deck_quality.py \
    -v \
    --tb=short \
    -m "not slow"; then
    echo "✓ Unit tests passed"
else
    echo "✗ Unit tests failed"
    exit 1
fi

echo ""
echo "[2/2] Running integration tests (slow)..."
if uv run pytest src/ml/tests/test_tier0_tier1_validation.py \
    src/ml/tests/test_validate_deck_quality.py \
    -v \
    --tb=short \
    -m "slow"; then
    echo "✓ Integration tests passed"
else
    echo "⚠ Integration tests failed (non-blocking)"
fi

echo ""
echo "=================================================="
echo "All Tests Complete"
echo "=================================================="

