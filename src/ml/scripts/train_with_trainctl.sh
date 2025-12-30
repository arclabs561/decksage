#!/bin/bash
# Train embeddings using runctl
# This script wraps our training script to work with runctl

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
RUNCTL_BIN="${RUNCTL_BIN:-$PROJECT_ROOT/../runctl/target/release/runctl}"

# Default arguments
INPUT="${INPUT:-data/processed/pairs_large.csv}"
OUTPUT="${OUTPUT:-data/embeddings/trained.wv}"
DIM="${DIM:-128}"
WALK_LENGTH="${WALK_LENGTH:-80}"
NUM_WALKS="${NUM_WALKS:-10}"
WINDOW="${WINDOW:-10}"
P="${P:-1.0}"
Q="${Q:-1.0}"
EPOCHS="${EPOCHS:-10}"
VAL_RATIO="${VAL_RATIO:-0.1}"
PATIENCE="${PATIENCE:-3}"
LR="${LR:-0.025}"
MIN_LR="${MIN_LR:-0.0001}"

# Training script
TRAIN_SCRIPT="$SCRIPT_DIR/improve_training_with_validation_enhanced.py"

# Check if runctl exists
if [ ! -f "$RUNCTL_BIN" ]; then
    echo "❌ runctl not found at $RUNCTL_BIN"
    echo "   Build it with: cd ../runctl && cargo build --release"
    exit 1
fi

# Check if training script exists
if [ ! -f "$TRAIN_SCRIPT" ]; then
    echo "❌ Training script not found: $TRAIN_SCRIPT"
    exit 1
fi

echo "🚀 Training with runctl"
echo "   Input: $INPUT"
echo "   Output: $OUTPUT"
echo "   Script: $TRAIN_SCRIPT"
echo ""

# Run with runctl
exec "$RUNCTL_BIN" local "$TRAIN_SCRIPT" \
    --input "$INPUT" \
    --output "$OUTPUT" \
    --dim "$DIM" \
    --walk-length "$WALK_LENGTH" \
    --num-walks "$NUM_WALKS" \
    --window "$WINDOW" \
    --p "$P" \
    --q "$Q" \
    --epochs "$EPOCHS" \
    --train-ratio 0.8 \
    --val-ratio "$VAL_RATIO" \
    --patience "$PATIENCE" \
    --lr "$LR" \
    --lr-decay 0.95 \
    "$@"

