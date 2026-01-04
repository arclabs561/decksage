#!/bin/bash
# Full pipeline: Train + Evaluate hybrid system with runctl
# Usage: ./scripts/run_full_pipeline_with_runctl.sh [instance-id]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNCTL_BIN="${RUNCTL_BIN:-$PROJECT_ROOT/../runctl/target/release/runctl}"

INSTANCE_ID="${1:-}"

if [[ -z "$INSTANCE_ID" ]]; then
 echo "Creating new AWS instance..."
 INSTANCE_ID=$("$RUNCTL_BIN" aws create --spot g4dn.xlarge 2>&1 | grep -o 'i-[a-z0-9]*' | head -1)
 if [[ -z "$INSTANCE_ID" ]]; then
 echo "Error: Failed to create instance"
 exit 1
 fi
 echo "✓ Created instance: $INSTANCE_ID"
 echo " Waiting for instance to be ready..."
 sleep 30
fi

echo "="*70
echo "FULL HYBRID PIPELINE"
echo "="*70
echo "Instance: $INSTANCE_ID"
echo ""

# Step 1: Sync data to S3
echo "Step 1: Syncing data to S3..."
s5cmd cp data/graphs/incremental_graph.json s3://games-collections/graphs/ 2>&1 | grep -v "^$" || true
s5cmd cp data/graphs/train_val_edgelist.edg s3://games-collections/graphs/ 2>&1 | grep -v "^$" || true
s5cmd cp experiments/test_set_canonical_magic.json s3://games-collections/experiments/ 2>&1 | grep -v "^$" || true
echo "✓ Data synced"
echo ""

# Step 2: Train
echo "Step 2: Training hybrid system..."
echo " (This may take 30-60 minutes)"
echo ""
"$PROJECT_ROOT/scripts/training/train_hybrid_full_with_runctl.sh" aws "$INSTANCE_ID"
TRAIN_EXIT=$?

if [[ $TRAIN_EXIT -ne 0 ]]; then
 echo "Error: Training failed"
 exit 1
fi

echo ""
echo "✓ Training complete"
echo ""

# Step 3: Evaluate
echo "Step 3: Evaluating hybrid system..."
echo ""
"$PROJECT_ROOT/scripts/evaluation/eval_hybrid_with_runctl.sh" aws "$INSTANCE_ID"
EVAL_EXIT=$?

if [[ $EVAL_EXIT -ne 0 ]]; then
 echo "Error: Evaluation failed"
 exit 1
fi

echo ""
echo "="*70
echo "PIPELINE COMPLETE"
echo "="*70
echo "Instance: $INSTANCE_ID"
echo "Results: s3://games-collections/experiments/hybrid_evaluation_results.json"
echo ""
echo "Download results:"
echo " s5cmd cp s3://games-collections/experiments/hybrid_evaluation_results.json experiments/"
echo "="*70
