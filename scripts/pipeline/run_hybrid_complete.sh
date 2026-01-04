#!/bin/bash
# Complete hybrid embeddings workflow
# Runs everything: setup → train → eval → test

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

MODE="${1:-local}"
INSTANCE_ID="${2:-}"

echo "="*70
echo "COMPLETE HYBRID EMBEDDINGS WORKFLOW"
echo "="*70
echo "Mode: $MODE"
if [[ -n "$INSTANCE_ID" ]]; then
 echo "Instance: $INSTANCE_ID"
fi
echo ""

# Step 1: Quick start (setup)
echo "Step 1: Quick start setup..."
./scripts/quick_start_hybrid.sh
echo ""

# Step 2: Test system
echo "Step 2: Testing hybrid system..."
uv run python -m ml.scripts.test_hybrid_system --test all || {
 echo " Warning: Some tests may have failed (check output above)"
}
echo ""

# Step 3: Train GNN (if graph exists)
echo "Step 3: Training GNN embeddings..."
if [[ -f "data/graphs/edgelist.edg" ]]; then
 if [[ "$MODE" == "local" ]]; then
 echo " Training locally (this may take 2-4 hours)..."
 just train-gnn-local || {
 echo " Warning: Local training failed or skipped"
 }
 elif [[ "$MODE" == "aws" && -n "$INSTANCE_ID" ]]; then
 echo " Training on AWS GPU (faster, ~30-60 min)..."
 just train-gnn-aws "$INSTANCE_ID" || {
 echo " Warning: AWS training failed"
 }
 else
 echo " Warning: Skipping training (use 'aws <instance-id>' for GPU training)"
 fi
else
 echo " Warning: No graph found, skipping GNN training"
 echo " Create graph first: uv run python -m ml.scripts.update_graph_incremental --rebuild"
fi
echo ""

# Step 4: Evaluate
echo "Step 4: Evaluating hybrid system..."
if [[ -f "experiments/test_set_unified_magic.json" ]]; then
 if [[ "$MODE" == "local" ]]; then
 just eval-hybrid-local || {
 echo " Warning: Evaluation failed"
 }
 elif [[ "$MODE" == "aws" && -n "$INSTANCE_ID" ]]; then
 just eval-hybrid-aws "$INSTANCE_ID" || {
 echo " Warning: Evaluation failed"
 }
 else
 echo " Warning: Skipping evaluation"
 fi
else
 echo " Warning: No test set found, skipping evaluation"
fi
echo ""

# Step 5: Summary
echo "="*70
echo "WORKFLOW COMPLETE"
echo "="*70
echo ""
echo "Results:"
if [[ -f "experiments/hybrid_evaluation_results.json" ]]; then
 echo " Evaluation: experiments/hybrid_evaluation_results.json"
 python3 -c "
import json
with open('experiments/hybrid_evaluation_results.json') as f:
 data = json.load(f)
 summary = data.get('summary', {})
 print(f\" Average P@10: {summary.get('avg_p_at_10', 0):.4f}\")
 print(f\" Evaluated: {summary.get('evaluated', 0)}/{summary.get('total_queries', 0)} queries\")
"
fi
echo ""
echo "Next steps:"
echo " 1. Review results: cat experiments/hybrid_evaluation_results.json"
echo " 2. Integrate into API: Set INSTRUCTION_EMBEDDER_MODEL env var"
echo " 3. Daily updates: uv run python -m ml.scripts.update_embeddings_hybrid --schedule daily"
echo ""
