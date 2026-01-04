#!/usr/bin/env bash
# Quick status check for downstream evaluation (non-blocking)
# Usage: ./scripts/evaluation/check_eval_status.sh <instance-id>

set -euo pipefail

INSTANCE_ID="${1:-}"
if [[ -z "$INSTANCE_ID" ]]; then
    echo "Usage: $0 <instance-id>"
    exit 1
fi

SSH_KEY="${SSH_KEY_PATH:-$HOME/.ssh/tarek.pem}"
INSTANCE_IP=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text 2>/dev/null || echo "")

echo "Evaluation Status Check"
echo "======================"
echo "Instance: $INSTANCE_ID"
if [[ -n "$INSTANCE_IP" ]]; then
    echo "IP: $INSTANCE_IP"
fi
echo ""

# Check S3 output
echo "S3 Output:"
aws s3 ls s3://games-collections/experiments/downstream_evaluation_*.json 2>&1 | tail -5 || echo "  No output files found"
echo ""

# Check running processes (if SSH available)
if [[ -f "$SSH_KEY" ]] && [[ -n "$INSTANCE_IP" ]]; then
    echo "Running Processes:"
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=5 ec2-user@"$INSTANCE_IP" \
        "ps aux | grep -E '(python|evaluate|downstream)' | grep -v grep | head -5" 2>&1 || echo "  Could not check processes"
    echo ""

    echo "Recent Log (last 20 lines):"
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=5 ec2-user@"$INSTANCE_IP" \
        "find /home/ec2-user -name 'training.log' -o -name '*.log' 2>/dev/null | head -1 | xargs tail -20 2>/dev/null" 2>&1 || echo "  Could not read logs"
fi

echo ""
echo "To follow logs: ssh -i $SSH_KEY ec2-user@$INSTANCE_IP 'tail -f /path/to/training.log'"
