#!/bin/bash
# Monitor S3 outputs and intermediate progress files
# Uses runctl for instance management instead of raw AWS commands
# Checks for training/evaluation completion by monitoring S3
# Also checks for intermediate progress files for better visibility

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RUNCTL_BIN="${RUNCTL_BIN:-$PROJECT_ROOT/../runctl/target/release/runctl}"

INSTANCE_ID="${1:-i-0773955f0a1998ceb}"
CHECK_INTERVAL="${CHECK_INTERVAL:-30}"

GNN_OUTPUT="s3://games-collections/embeddings/gnn_graphsage.json"
EVAL_OUTPUT="s3://games-collections/experiments/hybrid_evaluation_results.json"
PROGRESS_DIR="s3://games-collections/training_progress"

echo "======================================================================"
echo "CONTINUOUS MONITORING - S3 OUTPUTS + INTERMEDIATE PROGRESS"
echo "======================================================================"
echo "Instance: $INSTANCE_ID"
echo "Check interval: ${CHECK_INTERVAL}s"
echo ""

iteration=0
gnn_found=false
eval_found=false

while true; do
    iteration=$((iteration + 1))
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    echo "[$iteration] $timestamp"
    echo "----------------------------------------------------------------------"

    # Check intermediate progress files
    echo "Intermediate Progress:"

    # Check for training metrics
    if aws s3 ls "${PROGRESS_DIR}/training_metrics.jsonl" > /dev/null 2>&1; then
        echo "  ✓ Training metrics found"
        # Download and show latest
        aws s3 cp "${PROGRESS_DIR}/training_metrics.jsonl" /tmp/training_metrics.jsonl > /dev/null 2>&1
        if [ -f /tmp/training_metrics.jsonl ]; then
            latest_epoch=$(tail -1 /tmp/training_metrics.jsonl 2>/dev/null | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('epoch', '?'))" 2>/dev/null || echo "?")
            latest_loss=$(tail -1 /tmp/training_metrics.jsonl 2>/dev/null | python3 -c "import sys, json; d=json.load(sys.stdin); print(f\"{d.get('metrics', {}).get('loss', '?'):.4f}\")" 2>/dev/null || echo "?")
            echo "    Latest: Epoch $latest_epoch, Loss: $latest_loss"
        fi
    else
        echo "  ✗ Training metrics: Not found"
    fi

    # Check for progress summary
    if aws s3 ls "${PROGRESS_DIR}/training_progress.json" > /dev/null 2>&1; then
        echo "  ✓ Progress summary found"
        aws s3 cp "${PROGRESS_DIR}/training_progress.json" /tmp/training_progress.json > /dev/null 2>&1
        if [ -f /tmp/training_progress.json ]; then
            last_epoch=$(python3 -c "import json; d=json.load(open('/tmp/training_progress.json')); print(d.get('last_epoch', '?'))" 2>/dev/null || echo "?")
            elapsed=$(python3 -c "import json; d=json.load(open('/tmp/training_progress.json')); print(f\"{d.get('elapsed_seconds', 0)/3600:.1f}h\")" 2>/dev/null || echo "?")
            echo "    Last epoch: $last_epoch, Elapsed: $elapsed"
        fi
    else
        echo "  ✗ Progress summary: Not found"
    fi

    # Check for checkpoints
    checkpoint_count=$(aws s3 ls "${PROGRESS_DIR}/checkpoints/" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$checkpoint_count" -gt 0 ]; then
        echo "  ✓ Checkpoints: $checkpoint_count found"
    else
        echo "  ✗ Checkpoints: Not found"
    fi

    echo ""

    # Check GNN embeddings
    if aws s3 ls "$GNN_OUTPUT" > /dev/null 2>&1; then
        if [ "$gnn_found" = false ]; then
            echo "✓ GNN embeddings found in S3!"
            gnn_found=true

            # Download
            echo "  Downloading..."
            aws s3 cp "$GNN_OUTPUT" "data/embeddings/gnn_graphsage.json" 2>&1 | grep -v "^$" || true
            echo "  ✓ Downloaded to data/embeddings/gnn_graphsage.json"
        else
            echo "✓ GNN embeddings: Available"
        fi
    else
        echo "✗ GNN embeddings: Not found in S3"
    fi

    # Check evaluation results
    if aws s3 ls "$EVAL_OUTPUT" > /dev/null 2>&1; then
        if [ "$eval_found" = false ]; then
            echo "✓ Evaluation results found in S3!"
            eval_found=true

            # Download
            echo "  Downloading..."
            aws s3 cp "$EVAL_OUTPUT" "experiments/hybrid_evaluation_results.json" 2>&1 | grep -v "^$" || true
            echo "  ✓ Downloaded to experiments/hybrid_evaluation_results.json"

            # Show summary
            echo ""
            echo "======================================================================"
            echo "PIPELINE COMPLETE!"
            echo "======================================================================"
            echo "Results:"
            echo "  - GNN embeddings: data/embeddings/gnn_graphsage.json"
            echo "  - Evaluation: experiments/hybrid_evaluation_results.json"
            echo ""
            echo "View results:"
            echo "  cat experiments/hybrid_evaluation_results.json | python3 -m json.tool"
            echo "======================================================================"

                   # If both found, prompt to stop instance
                   if [ "$gnn_found" = true ] && [ "$eval_found" = true ]; then
                       echo ""
                       echo "======================================================================"
                       echo "TRAINING COMPLETE - CONSIDER STOPPING INSTANCE"
                       echo "======================================================================"
                       echo "To stop instance and save costs:"
                       echo "  runctl aws stop $INSTANCE_ID"
                       echo ""
                       echo "To terminate instance (deletes EBS volumes):"
                       echo "  runctl aws terminate $INSTANCE_ID"
                       echo "======================================================================"
                       exit 0
                   fi
        else
            echo "✓ Evaluation results: Available"
        fi
    else
        echo "✗ Evaluation results: Not found in S3"
    fi

    # Check instance status using runctl (more reliable than process checking)
    if "$RUNCTL_BIN" aws processes "$INSTANCE_ID" > /dev/null 2>&1; then
        echo "✓ Instance: Accessible via runctl"
        # Show quick status (CPU, memory)
        "$RUNCTL_BIN" aws processes "$INSTANCE_ID" 2>&1 | grep -E "(cpu|mem|SYSTEM)" | head -3 || true
    else
        echo "✗ Instance: Not accessible (may be stopped or terminated)"
    fi

    echo ""

    # If both found, exit
    if [ "$gnn_found" = true ] && [ "$eval_found" = true ]; then
        echo "All outputs found. Monitoring complete."
        exit 0
    fi

    echo "Next check in ${CHECK_INTERVAL}s..."
    echo ""
    sleep "$CHECK_INTERVAL"
done
