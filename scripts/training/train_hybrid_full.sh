#!/bin/bash
# Full hybrid embedding training pipeline
# Usage: ./scripts/training/train_hybrid_full.sh [local|aws] [instance-id] [options...]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Source runctl finder if available
if [ -f "$PROJECT_ROOT/scripts/find_or_build_runctl.sh" ]; then
 . "$PROJECT_ROOT/scripts/find_or_build_runctl.sh" || true
fi

MODE="${1:-local}"
shift || true

# Default arguments
DECKS_PATH="${DECKS_PATH:-data/processed/decks_all_final.jsonl}"
GRAPH_PATH="${GRAPH_PATH:-data/graphs/incremental_graph.json}"
GNN_OUTPUT="${GNN_OUTPUT:-data/embeddings/gnn_graphsage.json}"
TEST_SET="${TEST_SET:-experiments/test_set_unified_magic.json}"
GNN_EPOCHS="${GNN_EPOCHS:-100}"
GNN_LR="${GNN_LR:-0.01}"
INSTRUCTION_MODEL="${INSTRUCTION_MODEL:-intfloat/e5-base-v2}"

echo "="*70
echo "HYBRID EMBEDDING FULL TRAINING"
echo "="*70
echo "Mode: $MODE"
echo "Decks: $DECKS_PATH"
echo "Graph: $GRAPH_PATH"
echo "GNN Output: $GNN_OUTPUT"
echo "Test Set: $TEST_SET"
echo "GNN Epochs: $GNN_EPOCHS"
echo ""

case "$MODE" in
 local)
 echo "Running local training..."
 uv run python -m ml.scripts.train_hybrid_full \
 --decks-path "$DECKS_PATH" \
 --graph-path "$GRAPH_PATH" \
 --gnn-output "$GNN_OUTPUT" \
 --test-set "$TEST_SET" \
 --gnn-epochs "$GNN_EPOCHS" \
 --gnn-lr "$GNN_LR" \
 --instruction-model "$INSTRUCTION_MODEL" \
 "$@"
 ;;
 aws|runpod)
 INSTANCE_ID="${1:-}"
 if [[ -z "$INSTANCE_ID" ]]; then
 echo "Instance ID required for cloud mode"
 echo " Usage: $0 $MODE <instance-id> [options...]"
 exit 1
 fi
 shift || true
 
 if [[ -n "${RUNCTL_BIN:-}" ]]; then
 echo "Running on AWS using runctl..."
 "$RUNCTL_BIN" aws train "$INSTANCE_ID" \
 "src/ml/scripts/train_hybrid_full.py" \
 --data-s3 "s3://games-collections/processed/" \
 --output-s3 "s3://games-collections/embeddings/" \
 -- \
 "--decks-path" "processed/decks_all_final.jsonl" \
 "--graph-path" "graphs/incremental_graph.json" \
 "--gnn-output" "embeddings/gnn_graphsage.json" \
 "--test-set" "experiments/test_set_unified_magic.json" \
 "--gnn-epochs" "$GNN_EPOCHS" \
 "--gnn-lr" "$GNN_LR" \
 "--instruction-model" "$INSTRUCTION_MODEL" \
 "$@"
 else
 echo "Warning: runctl not found, falling back to local mode"
 uv run python -m ml.scripts.train_hybrid_full \
 --decks-path "$DECKS_PATH" \
 --graph-path "$GRAPH_PATH" \
 --gnn-output "$GNN_OUTPUT" \
 --test-set "$TEST_SET" \
 --gnn-epochs "$GNN_EPOCHS" \
 --gnn-lr "$GNN_LR" \
 --instruction-model "$INSTRUCTION_MODEL" \
 "$@"
 fi
 ;;
 *)
 echo "Unknown mode: $MODE"
 exit 1
 ;;
esac

echo ""
echo "="*70
echo "TRAINING COMPLETE"
echo "="*70
