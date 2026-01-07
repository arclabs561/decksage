#!/bin/bash
# Run visual embeddings evaluation

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"

echo "=========================================="
echo "Visual Embeddings Evaluation"
echo "=========================================="
echo ""

# Check for required files
EMBEDDINGS_PATH="${EMBEDDINGS_PATH:-data/embeddings/magic_128d_test_pecanpy.wv}"
PAIRS_PATH="${PAIRS_PATH:-data/pairs/magic_large.csv}"
TEST_SET_PATH="${TEST_SET_PATH:-data/test_set_minimal.json}"
OUTPUT_PATH="${OUTPUT_PATH:-experiments/visual_embeddings_evaluation.json}"

if [ ! -f "$EMBEDDINGS_PATH" ]; then
    echo "Warning: Embeddings file not found: $EMBEDDINGS_PATH"
    echo "Set EMBEDDINGS_PATH environment variable or update default in script"
fi

if [ ! -f "$PAIRS_PATH" ]; then
    echo "Warning: Pairs file not found: $PAIRS_PATH"
    echo "Set PAIRS_PATH environment variable or update default in script"
fi

if [ ! -f "$TEST_SET_PATH" ]; then
    echo "Warning: Test set file not found: $TEST_SET_PATH"
    echo "Set TEST_SET_PATH environment variable or update default in script"
fi

echo "Configuration:"
echo "  Embeddings: $EMBEDDINGS_PATH"
echo "  Pairs: $PAIRS_PATH"
echo "  Test Set: $TEST_SET_PATH"
echo "  Output: $OUTPUT_PATH"
echo ""

# Run evaluation
python3 scripts/evaluation/evaluate_visual_embeddings.py \
    --test-set "$TEST_SET_PATH" \
    --embeddings "$EMBEDDINGS_PATH" \
    --pairs "$PAIRS_PATH" \
    --top-k 10 \
    --output "$OUTPUT_PATH"

echo ""
echo "=========================================="
echo "Evaluation Complete"
echo "=========================================="
echo ""
echo "Results saved to: $OUTPUT_PATH"
echo ""
echo "To view results:"
echo "  cat $OUTPUT_PATH | python3 -m json.tool"

