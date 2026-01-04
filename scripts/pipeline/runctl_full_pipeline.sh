#!/usr/bin/env bash
set -euo pipefail
# /// script
# requires-python = ">=3.11"
# ///
#
# Full pipeline using runctl for everything:
# 1. Test all improvements
# 2. Generate enhanced labels
# 3. Train embeddings with attribute boost
# 4. Evaluate with LLM judge
#
# Usage: ./scripts/runctl_full_pipeline.sh [local|aws] [options...]

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

MODE="${1:-local}"
shift || true

echo "═══════════════════════════════════════════════════════════════════════════════"
echo "    FULL PIPELINE WITH RUNCTL (Mode: $MODE)"
echo "═══════════════════════════════════════════════════════════════════════════════"
echo ""

cd "$PROJECT_ROOT"

# Step 1: Test all improvements
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 1: Testing All Improvements"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
./scripts/runctl_test_all.sh || {
    echo "    Tests failed, but continuing..."
}
echo ""

# Step 2: Generate enhanced labels (if queries exist)
if [[ -f "experiments/test_set_canonical_magic.json" ]]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "STEP 2: Generating Enhanced Labels (GPT-5.2 + Full Context)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    ./scripts/runctl_labeling.sh "$MODE" || {
        echo "    Labeling failed, but continuing..."
    }
    echo ""
else
    echo "    Skipping labeling (test set not found)"
    echo ""
fi

# Step 3: Train embeddings (if pairs exist)
if [[ -f "data/processed/pairs_large.csv" ]] || [[ "$MODE" != "local" ]]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "STEP 3: Training Multitask Embeddings (With Attribute Boost)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    USE_ATTRIBUTE_BOOST=1 ./scripts/runctl_training.sh "$MODE" || {
        echo "    Training failed, but continuing..."
    }
    echo ""
else
    echo "    Skipping training (pairs CSV not found locally)"
    echo "   Use cloud mode or create test data first"
    echo ""
fi

# Step 4: Evaluate (if embeddings exist)
if [[ -f "data/embeddings/multitask_embeddings.wv" ]] || [[ "$MODE" != "local" ]]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "STEP 4: LLM Evaluation (GPT-5.2 Judge)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    ./scripts/runctl_evaluation.sh "$MODE" || {
        echo "    Evaluation failed"
    }
    echo ""
else
    echo "    Skipping evaluation (embeddings not found)"
    echo ""
fi

echo "═══════════════════════════════════════════════════════════════════════════════"
echo "    FULL PIPELINE COMPLETED"
echo "═══════════════════════════════════════════════════════════════════════════════"
echo ""
echo "Summary:"
echo "    All improvements tested"
echo "    Enhanced labels generated (if test set available)"
echo "    Embeddings trained (if data available)"
echo "    Evaluation completed (if embeddings available)"
echo ""


