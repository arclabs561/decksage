#!/bin/bash
# Complete hybrid embeddings pipeline using runctl
# Usage: ./scripts/hybrid_embeddings_pipeline.sh [local|aws] [instance-id]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

MODE="${1:-local}"
INSTANCE_ID="${2:-}"

echo "="*70
echo "HYBRID EMBEDDINGS PIPELINE"
echo "="*70
echo "Mode: $MODE"
if [[ -n "$INSTANCE_ID" ]]; then
 echo "Instance: $INSTANCE_ID"
fi
echo ""

# Step 1: Update graph (if new decks available)
echo "Step 1: Update graph..."
if [[ -f "data/processed/new_decks.jsonl" ]]; then
 uv run python -m ml.scripts.update_graph_incremental \
 --graph-path data/graphs/incremental_graph.json \
 --new-decks data/processed/new_decks.jsonl \
 --export-edgelist data/graphs/edgelist.edg \
 --min-weight 2
 echo "✓ Graph updated"
else
 echo "Warning: No new decks found, skipping graph update"
fi

# Step 2: Train GNN embeddings
echo ""
echo "Step 2: Train GNN embeddings..."
if [[ "$MODE" == "local" ]]; then
 ./scripts/training/train_hybrid_gnn_with_runctl.sh local \
 --edgelist data/graphs/edgelist.edg \
 --output data/embeddings/gnn_graphsage.json \
 --epochs 100
elif [[ "$MODE" == "aws" && -n "$INSTANCE_ID" ]]; then
 ./scripts/training/train_hybrid_gnn_with_runctl.sh aws "$INSTANCE_ID" \
 --edgelist s3://games-collections/graphs/edgelist.edg \
 --output s3://games-collections/embeddings/gnn_graphsage.json \
 --epochs 100
else
 echo "Warning: Skipping GNN training (requires instance ID for AWS)"
fi

# Step 3: Evaluate hybrid system
echo ""
echo "Step 3: Evaluate hybrid embeddings..."
if [[ "$MODE" == "local" ]]; then
 ./scripts/evaluation/eval_hybrid_with_runctl.sh local \
 --test-set experiments/test_set_canonical_magic.json \
 --output experiments/hybrid_evaluation_results.json
elif [[ "$MODE" == "aws" && -n "$INSTANCE_ID" ]]; then
 ./scripts/evaluation/eval_hybrid_with_runctl.sh aws "$INSTANCE_ID" \
 --test-set s3://games-collections/experiments/test_set_canonical_magic.json \
 --output s3://games-collections/experiments/hybrid_evaluation_results.json
else
 echo "Warning: Skipping evaluation (requires instance ID for AWS)"
fi

echo ""
echo "="*70
echo "PIPELINE COMPLETE"
echo "="*70
