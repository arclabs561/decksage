#!/bin/bash
# Check runctl training status and AWS instances

set -euo pipefail

echo "=" | tr -d '\n' && printf '%.0s=' {1..69} && echo
echo "RUNCTL TRAINING STATUS CHECK"
echo "=" | tr -d '\n' && printf '%.0s=' {1..69} && echo
echo

# Check runctl binary
RUNCTL_BIN="../runctl/target/release/runctl"
if [ -f "$RUNCTL_BIN" ]; then
    echo "✓ runctl found: $RUNCTL_BIN"
    echo "  Version: $($RUNCTL_BIN --version 2>&1 || echo 'unknown')"
else
    echo "✗ runctl not found at $RUNCTL_BIN"
    echo "  Build with: cd ../runctl && cargo build --release"
fi

echo

# Check AWS instances
echo "AWS EC2 Instances:"
echo "-" | tr -d '\n' && printf '%.0s-' {1..69} && echo

if command -v aws &> /dev/null; then
    aws ec2 describe-instances \
        --query 'Reservations[*].Instances[*].[InstanceId,State.Name,InstanceType,Tags[?Key==`Name`].Value|[0],LaunchTime]' \
        --output table 2>/dev/null || echo "  (AWS CLI not configured)"
else
    echo "  AWS CLI not installed"
fi

echo

# Check for training processes
echo "Local Training Processes:"
echo "-" | tr -d '\n' && printf '%.0s-' {1..69} && echo
ps aux | grep -E "(train|embedding|pecan|hyperparam)" | grep -v grep | head -5 || echo "  No training processes found"

echo

# Check log files
echo "Training Logs:"
echo "-" | tr -d '\n' && printf '%.0s-' {1..69} && echo
for log in /tmp/hyperparam_search.log /tmp/enrichment.log /tmp/labeling.log; do
    if [ -f "$log" ]; then
        size=$(du -h "$log" | cut -f1)
        echo "  ✓ $log ($size)"
    fi
done

echo
echo "=" | tr -d '\n' && printf '%.0s=' {1..69} && echo

