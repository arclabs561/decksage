#!/usr/bin/env bash
# Run Tier 0 & Tier 1 validation with proper error handling

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"

# Configuration
GAME="${GAME:-magic}"
NUM_DECKS="${NUM_DECKS:-20}"
SKIP_DECK_VALIDATION="${SKIP_DECK_VALIDATION:-false}"
CHECK_PREREQUISITES="${CHECK_PREREQUISITES:-true}"

echo "=================================================="
echo "Tier 0 & Tier 1 Validation"
echo "=================================================="
echo "Game: $GAME"
echo "Num decks: $NUM_DECKS"
echo "Skip deck validation: $SKIP_DECK_VALIDATION"
echo "Check prerequisites: $CHECK_PREREQUISITES"
echo ""

# Check prerequisites
if [ "$CHECK_PREREQUISITES" = "true" ]; then
    echo "[1/2] Checking prerequisites..."
    if ! uv run --script src/ml/scripts/validate_prerequisites.py; then
        echo "ERROR: Prerequisites check failed"
        echo "Run with CHECK_PREREQUISITES=false to skip"
        exit 1
    fi
    echo ""
fi

# Run validations
echo "[2/2] Running validations..."
SKIP_FLAG=""
if [ "$SKIP_DECK_VALIDATION" = "true" ]; then
    SKIP_FLAG="--skip-deck-validation"
fi

if uv run --script src/ml/scripts/run_all_tier0_tier1.py \
    --game "$GAME" \
    --num-decks "$NUM_DECKS" \
    $SKIP_FLAG \
    --check-prerequisites; then
    echo ""
    echo "=================================================="
    echo "Validation Complete"
    echo "=================================================="
    echo "Results: experiments/tier0_tier1_validation.json"
    echo "Dashboard: experiments/quality_dashboard.html"
    exit 0
else
    echo ""
    echo "ERROR: Validation failed"
    exit 1
fi

