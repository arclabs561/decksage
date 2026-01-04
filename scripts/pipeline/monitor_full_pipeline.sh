#!/bin/bash
# Continuous monitoring and execution of full pipeline
# Monitors training, then automatically runs evaluation

set -euo pipefail

INSTANCE_ID="${1:-i-0773955f0a1998ceb}"
SSH_KEY_PATH="${SSH_KEY_PATH:-$HOME/.ssh/unknown.pem}"
RUNCTL_BIN="${RUNCTL_BIN:-$(cd "$(dirname "$0")/.." && pwd)/../runctl/target/release/runctl}"

export SSH_KEY_PATH

echo "="*70
echo "FULL PIPELINE - CONTINUOUS MONITORING"
echo "="*70
echo "Instance: $INSTANCE_ID"
echo "SSH Key: $SSH_KEY_PATH"
echo ""

# Function to check if process is running
check_training() {
 ps aux | grep -E "runctl.*train.*$INSTANCE_ID|train_hybrid.*$INSTANCE_ID" | grep -v grep > /dev/null
}

# Function to check S3 for training completion
check_training_complete() {
 # Check if GNN embeddings exist in S3
 aws s3 ls "s3://games-collections/embeddings/gnn_graphsage.json" > /dev/null 2>&1
}

# Function to check if evaluation is running
check_evaluation() {
 ps aux | grep -E "runctl.*eval.*$INSTANCE_ID|eval_hybrid.*$INSTANCE_ID" | grep -v grep > /dev/null
}

# Step 1: Check training status
echo "Step 1: Checking training status..."
if check_training; then
 echo "✓ Training is running"
 echo " Monitoring training progress..."
 
 # Monitor until training completes
 while check_training; do
 echo -n "."
 sleep 30
 done
 echo ""
 echo "Training process completed"
else
 echo "Warning: Training process not found"
 
 # Check if training already completed
 if check_training_complete; then
 echo "✓ Training appears to have completed (GNN embeddings found in S3)"
 else
 echo "Warning: Training not found and outputs not in S3"
 echo " Starting training..."
 
 SSH_KEY_PATH="$SSH_KEY_PATH" "$RUNCTL_BIN" aws train "$INSTANCE_ID" \
 "src/ml/scripts/train_hybrid_full.py" \
 --data-s3 "s3://games-collections/" \
 --output-s3 "s3://games-collections/" \
 -- \
 --decks-path "processed/decks_all_final.jsonl" \
 --graph-path "graphs/incremental_graph.json" \
 --gnn-output "embeddings/gnn_graphsage.json" \
 --gnn-epochs 50 \
 --instruction-model "intfloat/e5-base-v2" &
 
 TRAIN_PID=$!
 echo " Training started (PID: $TRAIN_PID)"
 
 # Monitor training
 while check_training || kill -0 $TRAIN_PID 2>/dev/null; do
 echo -n "."
 sleep 30
 done
 echo ""
 echo "✓ Training completed"
 fi
fi

# Wait a bit for outputs to sync
echo ""
echo "Waiting for outputs to sync to S3..."
sleep 60

# Step 2: Run evaluation
echo ""
echo "Step 2: Starting evaluation..."
if check_evaluation; then
 echo "Warning: Evaluation already running"
else
 echo " Running evaluation with leakage prevention..."
 
 "$RUNCTL_BIN" aws train "$INSTANCE_ID" \
 "src/ml/scripts/evaluate_hybrid_with_runctl.py" \
 --data-s3 "s3://games-collections/" \
 --output-s3 "s3://games-collections/experiments/" \
 -- \
    --test-set "experiments/test_set_unified_magic.json" \
 --graph "graphs/incremental_graph.json" \
 --gnn-model "embeddings/gnn_graphsage.json" \
 --cooccurrence-embeddings "embeddings/production.wv" \
 --instruction-model "intfloat/e5-base-v2" \
 --output "experiments/hybrid_evaluation_results.json" \
 --use-temporal-split &
 
 EVAL_PID=$!
 echo " Evaluation started (PID: $EVAL_PID)"
 
 # Monitor evaluation
 while check_evaluation || kill -0 $EVAL_PID 2>/dev/null; do
 echo -n "."
 sleep 30
 done
 echo ""
 echo "✓ Evaluation completed"
fi

# Step 3: Download results
echo ""
echo "Step 3: Downloading results..."
s5cmd cp "s3://games-collections/embeddings/gnn_graphsage.json" "data/embeddings/" 2>&1 | grep -v "^$" || true
s5cmd cp "s3://games-collections/experiments/hybrid_evaluation_results.json" "experiments/" 2>&1 | grep -v "^$" || true

echo ""
echo "="*70
echo "PIPELINE COMPLETE"
echo "="*70
echo "Results downloaded to:"
echo " - data/embeddings/gnn_graphsage.json"
echo " - experiments/hybrid_evaluation_results.json"
echo ""
echo "View results:"
echo " cat experiments/hybrid_evaluation_results.json | python3 -m json.tool"
echo "="*70

