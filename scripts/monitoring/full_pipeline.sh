#!/bin/bash
# Full pipeline monitoring (training + evaluation)
# Combines: monitor_full_pipeline.sh, monitor_s3_outputs.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RUNCTL_BIN="${RUNCTL_BIN:-$PROJECT_ROOT/../runctl/target/release/runctl}"

INSTANCE_ID="${1:-i-0773955f0a1998ceb}"
CHECK_INTERVAL="${CHECK_INTERVAL:-30}"

echo "======================================================================"
echo "FULL PIPELINE MONITOR"
echo "======================================================================"
echo "Instance: $INSTANCE_ID"
echo "Check interval: ${CHECK_INTERVAL}s"
echo ""

GNN_OUTPUT="s3://games-collections/embeddings/gnn_graphsage.json"
EVAL_OUTPUT="s3://games-collections/experiments/hybrid_evaluation_results.json"
PROGRESS_DIR="s3://games-collections/training_progress"

iteration=0
gnn_found=false
eval_found=false

while true; do
    iteration=$((iteration + 1))
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$iteration] $timestamp"
    echo "----------------------------------------------------------------------"

    # Check instance status
    if "$RUNCTL_BIN" aws processes "$INSTANCE_ID" > /dev/null 2>&1; then
        echo "✓ Instance: Accessible"
    else
        echo "✗ Instance: Not accessible"
    fi

    # Check training completion
    if aws s3 ls "$GNN_OUTPUT" > /dev/null 2>&1; then
        if [ "$gnn_found" = false ]; then
            echo "✓ Training: Complete (GNN embeddings found)"
            gnn_found=true
        fi
    else
        echo "⏳ Training: In progress..."
    fi

    # Check evaluation completion
    if aws s3 ls "$EVAL_OUTPUT" > /dev/null 2>&1; then
        if [ "$eval_found" = false ]; then
            echo "✓ Evaluation: Complete (results found)"
            eval_found=true
        fi
    else
        if [ "$gnn_found" = true ]; then
            echo "⏳ Evaluation: In progress..."
        else
            echo "⏳ Evaluation: Waiting for training..."
        fi
    fi

    # Check progress files
    if aws s3 ls "${PROGRESS_DIR}/training_progress.json" > /dev/null 2>&1; then
        echo "✓ Progress: Available"
    fi

    echo ""

    # Exit if both complete
    if [ "$gnn_found" = true ] && [ "$eval_found" = true ]; then
        echo "======================================================================"
        echo "PIPELINE COMPLETE"
        echo "======================================================================"
        exit 0
    fi

    echo "Next check in ${CHECK_INTERVAL}s..."
    echo ""
    sleep "$CHECK_INTERVAL"
done
