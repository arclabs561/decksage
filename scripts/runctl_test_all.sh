#!/usr/bin/env bash
set -euo pipefail
# /// script
# requires-python = ">=3.11"
# ///
#
# Runctl wrapper for testing all improvements
# Usage: ./scripts/runctl_test_all.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Find or build runctl
RUNCTL_BIN="${RUNCTL_BIN:-$PROJECT_ROOT/../runctl/target/release/runctl}"
if [[ ! -f "$RUNCTL_BIN" ]]; then
    echo "    runctl not found, building from local project..."
    if [[ -d "$PROJECT_ROOT/../runctl" ]]; then
        (cd "$PROJECT_ROOT/../runctl" && cargo build --release) || {
            echo "  Failed to build runctl"
            echo "   Please build manually: cd ../runctl && cargo build --release"
            exit 1
        }
    else
        echo "  runctl directory not found"
        exit 1
    fi
fi

echo "  Testing all improvements with runctl"
echo ""

cd "$PROJECT_ROOT"

# Find or build runctl
RUNCTL_BIN="${RUNCTL_BIN:-$PROJECT_ROOT/../runctl/target/release/runctl}"
if [[ ! -f "$RUNCTL_BIN" ]]; then
    echo "    runctl not found, running tests directly with Python"
    RUNCTL_BIN=""
fi

# Test 1: Model selection
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 1: Model Selection (GPT-5.2)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ -n "$RUNCTL_BIN" ]]; then
    "$RUNCTL_BIN" local "src/ml/scripts/test_all_improvements.py" -- --test model_selection \
        || echo "    Test 1 failed (check output above)"
else
    uv run python src/ml/scripts/test_all_improvements.py --test model_selection \
        || echo "    Test 1 failed (check output above)"
fi

echo ""

# Test 2: Context loading
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 2: Context Loading (Case-Insensitive)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ -n "$RUNCTL_BIN" ]]; then
    "$RUNCTL_BIN" local "src/ml/scripts/test_labeling_with_context.py" -- \
        || echo "    Test 2 failed (check output above)"
else
    uv run python src/ml/scripts/test_labeling_with_context.py \
        || echo "    Test 2 failed (check output above)"
fi

echo ""

# Test 3: Training functions
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 3: Training Functions"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ -n "$RUNCTL_BIN" ]]; then
    "$RUNCTL_BIN" local "src/ml/scripts/test_training_progress.py" -- \
        || echo "    Test 3 failed (check output above)"
else
    uv run python src/ml/scripts/test_training_progress.py \
        || echo "    Test 3 failed (check output above)"
fi

echo ""

# Test 4: All improvements
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 4: All Improvements (Comprehensive)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ -n "$RUNCTL_BIN" ]]; then
    "$RUNCTL_BIN" local "src/ml/scripts/test_all_improvements.py" -- \
        || echo "    Test 4 failed (check output above)"
else
    uv run python src/ml/scripts/test_all_improvements.py \
        || echo "    Test 4 failed (check output above)"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  All tests completed!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
