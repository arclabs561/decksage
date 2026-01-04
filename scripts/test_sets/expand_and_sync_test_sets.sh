#!/usr/bin/env bash
# Expand test sets and sync to S3

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# Configuration
GAME="${GAME:-magic}"
TARGET_SIZE="${TARGET_SIZE:-200}"
BATCH_SIZE="${BATCH_SIZE:-10}"
CHECKPOINT_INTERVAL="${CHECKPOINT_INTERVAL:-5}"

# Test set paths
CANONICAL="experiments/test_set_canonical_${GAME}.json"
EXPANDED="experiments/test_set_expanded_${GAME}.json"
OUTPUT="experiments/test_set_expanded_${GAME}_v$(date +%Y%m%d).json"

echo "=" | tr -d '\n' | head -c 70 && echo
echo "TEST SET EXPANSION AND SYNC"
echo "=" | tr -d '\n' | head -c 70 && echo
echo "Game: $GAME"
echo "Target size: $TARGET_SIZE"
echo "Input: $CANONICAL"
echo "Output: $OUTPUT"
echo ""

# Check if canonical exists
if [ ! -f "$CANONICAL" ]; then
    echo "ERROR: Canonical test set not found: $CANONICAL"
    echo "Syncing from S3..."
    aws s3 cp "s3://games-collections/experiments/test_set_canonical_${GAME}.json" "$CANONICAL" || {
        echo "ERROR: Failed to sync canonical test set"
        exit 1
    }
fi

# Use expanded as base if it exists and is larger
BASE="$CANONICAL"
if [ -f "$EXPANDED" ]; then
    CANONICAL_SIZE=$(python3 -c "import json; print(len(json.load(open('$CANONICAL')).get('queries', {})))" 2>/dev/null || echo "0")
    EXPANDED_SIZE=$(python3 -c "import json; print(len(json.load(open('$EXPANDED')).get('queries', {})))" 2>/dev/null || echo "0")
    if [ "$EXPANDED_SIZE" -gt "$CANONICAL_SIZE" ]; then
        BASE="$EXPANDED"
        echo "Using expanded test set as base ($EXPANDED_SIZE queries)"
    fi
fi

# Check current size
CURRENT_SIZE=$(python3 -c "import json; print(len(json.load(open('$BASE')).get('queries', {})))" 2>/dev/null || echo "0")
echo "Current size: $CURRENT_SIZE queries"
echo "Target size: $TARGET_SIZE queries"
echo "Need to add: $((TARGET_SIZE - CURRENT_SIZE)) queries"
echo ""

if [ "$CURRENT_SIZE" -ge "$TARGET_SIZE" ]; then
    echo "Test set already at or above target size"
    exit 0
fi

# Expand using generate_labels_for_new_queries_optimized.py
echo "Expanding test set..."
uv run python src/ml/scripts/generate_labels_for_new_queries_optimized.py \
    --input "$BASE" \
    --output "$OUTPUT" \
    --batch-size "$BATCH_SIZE" \
    --checkpoint-interval "$CHECKPOINT_INTERVAL" \
    || {
    echo "ERROR: Label generation failed"
    exit 1
}

# Check if expansion worked
FINAL_SIZE=$(python3 -c "import json; print(len(json.load(open('$OUTPUT')).get('queries', {})))" 2>/dev/null || echo "0")
echo ""
echo "Expansion complete:"
echo "  Before: $CURRENT_SIZE queries"
echo "  After: $FINAL_SIZE queries"
echo "  Added: $((FINAL_SIZE - CURRENT_SIZE)) queries"
echo ""

# Sync to S3
echo "Syncing to S3..."
aws s3 cp "$OUTPUT" "s3://games-collections/experiments/$(basename $OUTPUT)" || {
    echo "WARNING: Failed to sync to S3"
}

# Also update the expanded symlink/reference
if [ -f "$EXPANDED" ] && [ "$FINAL_SIZE" -gt "$(python3 -c "import json; print(len(json.load(open('$EXPANDED')).get('queries', {})))" 2>/dev/null || echo "0")" ]; then
    echo "Updating expanded test set reference..."
    cp "$OUTPUT" "$EXPANDED"
    aws s3 cp "$EXPANDED" "s3://games-collections/experiments/test_set_expanded_${GAME}.json" || true
fi

echo ""
echo "=" | tr -d '\n' | head -c 70 && echo
echo "COMPLETE"
echo "=" | tr -d '\n' | head -c 70 && echo
echo "Output: $OUTPUT"
echo "Size: $FINAL_SIZE queries"
echo "Synced to S3: s3://games-collections/experiments/$(basename $OUTPUT)"
