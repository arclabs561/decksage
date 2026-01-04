#!/bin/bash
# Unified training monitoring
# Combines: monitor_training_unified.py, monitor_runctl_unified.sh, training/monitor_training*.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RUNCTL_BIN="${RUNCTL_BIN:-$PROJECT_ROOT/../runctl/target/release/runctl}"

INSTANCE_ID="${1:-}"
CHECK_INTERVAL="${CHECK_INTERVAL:-30}"
USE_STRUCTURED="${USE_STRUCTURED:-1}"

if [ -z "$INSTANCE_ID" ]; then
    echo "Usage: $0 <instance-id> [check-interval]"
    echo ""
    echo "Monitors training with:"
    echo "  - Structured log parsing (if available)"
    echo "  - S3 output monitoring"
    echo "  - Instance status checks"
    exit 1
fi

echo "======================================================================"
echo "TRAINING MONITOR"
echo "======================================================================"
echo "Instance: $INSTANCE_ID"
echo "Check interval: ${CHECK_INTERVAL}s"
echo ""

# Try structured log monitoring first (if Python script available)
MONITOR_SCRIPT="$PROJECT_ROOT/scripts/monitor_training_unified.py"
if [ -f "$MONITOR_SCRIPT" ] && [ "$USE_STRUCTURED" = "1" ]; then
    python3 "$MONITOR_SCRIPT" \
        --instance-id "$INSTANCE_ID" \
        --interval "$CHECK_INTERVAL" \
        "${@:2}"
    exit $?
fi

# Fallback to S3 + instance monitoring
GNN_OUTPUT="s3://games-collections/embeddings/gnn_graphsage.json"
PROGRESS_DIR="s3://games-collections/training_progress"

iteration=0
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

    # Check S3 outputs
    if aws s3 ls "$GNN_OUTPUT" > /dev/null 2>&1; then
        echo "✓ GNN embeddings: Found in S3"
        echo ""
        echo "Training complete!"
        exit 0
    else
        echo "⏳ GNN embeddings: Not found in S3"
    fi

    # Check progress files
    if aws s3 ls "${PROGRESS_DIR}/training_progress.json" > /dev/null 2>&1; then
        echo "✓ Progress file: Available"
    fi

    echo ""
    echo "Next check in ${CHECK_INTERVAL}s..."
    sleep "$CHECK_INTERVAL"
done
