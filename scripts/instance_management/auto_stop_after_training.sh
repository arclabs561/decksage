#!/bin/bash
# Auto-stop instance after training completes
# Usage: ./scripts/auto_stop_after_training.sh <instance-id> [wait-minutes]

set -euo pipefail

INSTANCE_ID="${1:-}"
WAIT_MINUTES="${2:-10}"  # Wait 10 min after completion before stopping

if [[ -z "$INSTANCE_ID" ]]; then
    echo "Usage: $0 <instance-id> [wait-minutes]"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RUNCTL_BIN="${RUNCTL_BIN:-$PROJECT_ROOT/../runctl/target/release/runctl}"

GNN_OUTPUT="s3://games-collections/embeddings/gnn_graphsage.json"
EVAL_OUTPUT="s3://games-collections/experiments/hybrid_evaluation_results.json"

echo "======================================================================"
echo "AUTO-STOP AFTER TRAINING"
echo "======================================================================"
echo "Instance: $INSTANCE_ID"
echo "Will stop $WAIT_MINUTES minutes after training completes"
echo ""

while true; do
    # Check for completion
    GNN_EXISTS=$(s5cmd ls "$GNN_OUTPUT" 2>&1 | grep -q "gnn_graphsage.json" && echo "yes" || echo "no")
    EVAL_EXISTS=$(s5cmd ls "$EVAL_OUTPUT" 2>&1 | grep -q "hybrid_evaluation_results.json" && echo "yes" || echo "no")
    
    if [[ "$GNN_EXISTS" == "yes" ]] && [[ "$EVAL_EXISTS" == "yes" ]]; then
        echo "✓ Training complete! Waiting $WAIT_MINUTES minutes before stopping..."
        sleep $((WAIT_MINUTES * 60))
        
        echo "Stopping instance $INSTANCE_ID..."
        "$RUNCTL_BIN" aws stop "$INSTANCE_ID"
        echo "✓ Instance stopped"
        exit 0
    fi
    
    sleep 60  # Check every minute
done
