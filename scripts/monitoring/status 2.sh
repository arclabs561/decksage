#!/bin/bash
# Quick status check for all system components
# Combines: monitor_quick.py, check_runctl_status.sh, check_eval_status.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RUNCTL_BIN="${RUNCTL_BIN:-$PROJECT_ROOT/../runctl/target/release/runctl}"

INSTANCE_ID="${1:-}"

echo "======================================================================"
echo "QUICK STATUS CHECK"
echo "======================================================================"
echo ""

# Check runctl binary
if [ -f "$RUNCTL_BIN" ]; then
    echo "✓ runctl: $($RUNCTL_BIN --version 2>&1 | head -1 || echo 'found')"
else
    echo "✗ runctl: Not found"
fi

echo ""

# Check AWS instances (if AWS CLI available)
if command -v aws &> /dev/null; then
    echo "AWS Instances:"
    aws ec2 describe-instances \
        --query 'Reservations[*].Instances[*].[InstanceId,State.Name,InstanceType]' \
        --output table 2>/dev/null | head -10 || echo "  (AWS CLI not configured)"
    echo ""
fi

# Check local training processes
echo "Local Processes:"
ps aux | grep -E "(train|embedding|eval)" | grep -v grep | head -5 || echo "  None running"
echo ""

# Check key files
echo "Key Files:"
for path in \
    "data/embeddings/gnn_graphsage.json" \
    "data/graphs/incremental_graph.json" \
    "experiments/test_set_unified_magic.json"; do
    if [ -f "$PROJECT_ROOT/$path" ]; then
        size=$(du -h "$PROJECT_ROOT/$path" | cut -f1)
        echo "  ✓ $path ($size)"
    else
        echo "  ✗ $path (not found)"
    fi
done

echo ""
echo "======================================================================"
