#!/usr/bin/env bash
set -euo pipefail
# /// script
# requires-python = ">=3.11"
# ///
#
# Runctl wrapper for training multitask embeddings with all improvements
# Usage: ./scripts/runctl_training.sh [local|aws|runpod] [options...]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

MODE="${1:-local}"
shift || true

# Default training parameters
DIM="${DIM:-128}"
WALK_LENGTH="${WALK_LENGTH:-80}"
NUM_WALKS="${NUM_WALKS:-10}"
WINDOW_SIZE="${WINDOW_SIZE:-10}"
EPOCHS="${EPOCHS:-5}"
MIN_COOCCURRENCE="${MIN_COOCCURRENCE:-2}"

# Data paths
PAIRS_CSV="${PAIRS_CSV:-data/processed/pairs_large.csv}"
CARD_ATTRS="${CARD_ATTRS:-data/processed/card_attributes_enriched.csv}"
SUBSTITUTION_PAIRS="${SUBSTITUTION_PAIRS:-experiments/substitution_pairs.json}"
OUTPUT_DIR="${OUTPUT_DIR:-data/embeddings}"

# S3 paths (for cloud training)
S3_DATA="${S3_DATA:-s3://games-collections/processed/}"
S3_OUTPUT="${S3_OUTPUT:-s3://games-collections/embeddings/}"

echo "Starting training with runctl (mode: $MODE)"
echo "   Pairs CSV: $PAIRS_CSV"
echo "   Card attrs: $CARD_ATTRS"
echo "   Output: $OUTPUT_DIR"
echo ""

# Find or build runctl (Rust binary)
RUNCTL_BIN="${RUNCTL_BIN:-$PROJECT_ROOT/../runctl/target/release/runctl}"
if [[ ! -f "$RUNCTL_BIN" ]]; then
    echo "runctl not found, building from local project..."
    if [[ -d "$PROJECT_ROOT/../runctl" ]]; then
        (cd "$PROJECT_ROOT/../runctl" && cargo build --release) || {
            echo "Failed to build runctl"
            echo "   Please build manually: cd ../runctl && cargo build --release"
            exit 1
        }
    else
        echo "runctl directory not found"
        exit 1
    fi
fi

case "$MODE" in
    local)
        echo "Local training mode"
        cd "$PROJECT_ROOT"

        # Check if data exists
        if [[ ! -f "$PAIRS_CSV" ]]; then
            echo "Pairs CSV not found: $PAIRS_CSV"
            echo "   Creating minimal test data..."
            uv run python -c "
import pandas as pd
from pathlib import Path
df = pd.DataFrame({
    'NAME_1': ['Lightning Bolt', 'Brainstorm', 'Ponder'],
    'NAME_2': ['Chain Lightning', 'Ponder', 'Preordain'],
    'COUNT_MULTISET': [10, 15, 12],
    'COUNT_SET': [10, 15, 12],
})
Path('$PAIRS_CSV').parent.mkdir(parents=True, exist_ok=True)
df.to_csv('$PAIRS_CSV', index=False)
print('Created test data')
"
        fi

        # Run training
        "$RUNCTL_BIN" local "src/ml/scripts/train_multitask_refined.py" -- \
                "--pairs" "$PAIRS_CSV" \
                "--output" "$OUTPUT_DIR/multitask_embeddings.wv" \
                "--dim" "$DIM" \
                "--walk-length" "$WALK_LENGTH" \
                "--num-walks" "$NUM_WALKS" \
                "--window-size" "$WINDOW_SIZE" \
                "--epochs" "$EPOCHS" \
                "--min-cooccurrence" "$MIN_COOCCURRENCE" \
                ${SUBSTITUTION_PAIRS:+--substitution-pairs "$SUBSTITUTION_PAIRS"} \
                "$@"
        ;;

    aws|runpod)
        echo "Cloud training mode: $MODE"
        echo "   S3 data: $S3_DATA"
        echo "   S3 output: $S3_OUTPUT"

        # Get instance ID from args or env
        INSTANCE_ID="${INSTANCE_ID:-${1:-}}"
        if [[ -z "$INSTANCE_ID" ]]; then
            echo "Instance ID required for cloud mode"
            echo "   Usage: $0 $MODE <instance-id> [options...]"
            exit 1
        fi
        shift || true

        # Run training
        "$RUNCTL_BIN" aws train "$INSTANCE_ID" \
            "src/ml/scripts/train_multitask_refined.py" \
            --output-s3 "$S3_OUTPUT" \
            -- \
                "--pairs-csv" "pairs_large.csv" \
                "--output-dir" "embeddings" \
                "--dim" "$DIM" \
                "--walk-length" "$WALK_LENGTH" \
                "--num-walks" "$NUM_WALKS" \
                "--window-size" "$WINDOW_SIZE" \
                "--epochs" "$EPOCHS" \
                "--min-cooccurrence" "$MIN_COOCCURRENCE" \
                "--card-attrs" "card_attributes_enriched.csv" \
                ${SUBSTITUTION_PAIRS:+--substitution-pairs "substitution_pairs.json"} \
                ${USE_ATTRIBUTE_BOOST:+--use-attribute-boost} \
                ${CHECKPOINT_INTERVAL:+--checkpoint-interval "$CHECKPOINT_INTERVAL"} \
                "$@"
        ;;

    *)
        echo "Unknown mode: $MODE"
        echo "   Use: local, aws, or runpod"
        exit 1
        ;;
esac

echo ""
echo "Training completed!"
