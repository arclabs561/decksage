#!/bin/bash
# Check if code exists on EBS volume before syncing
# Returns 0 if code exists and is recent, 1 if sync needed

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RUNCTL_BIN="${RUNCTL_BIN:-$PROJECT_ROOT/../runctl/target/release/runctl}"

INSTANCE_ID="${1:-}"
MOUNT_POINT="${MOUNT_POINT:-/mnt/data500}" # Use separate mount for 500GB volume
CODE_DIR="${CODE_DIR:-$MOUNT_POINT/code}"
MAX_AGE_DAYS="${MAX_AGE_DAYS:-7}" # Consider code stale after 7 days

if [[ -z "$INSTANCE_ID" ]]; then
 echo "Usage: $0 <instance-id> [mount-point]"
 exit 1
fi

# Check if code exists on EBS using SSM (flexible path matching)
CHECK_CMD="if [ -d \"$CODE_DIR\" ]; then TRAIN_SCRIPT=\$(find \"$CODE_DIR\" -name 'train_hybrid_from_pairs.py' -type f 2>/dev/null | head -1); if [ -n \"\$TRAIN_SCRIPT\" ] && [ -f \"\$TRAIN_SCRIPT\" ]; then CODE_AGE=\$(stat -c %Y \"\$TRAIN_SCRIPT\" 2>/dev/null || stat -f %m \"\$TRAIN_SCRIPT\" 2>/dev/null || echo 0); CURRENT_TIME=\$(date +%s); AGE_DAYS=\$(( (\$CURRENT_TIME - \$CODE_AGE) / 86400 )); if [ \$AGE_DAYS -lt $MAX_AGE_DAYS ]; then echo EXISTS_RECENT; echo \"Code age: \$AGE_DAYS days\" >&2; else echo EXISTS_STALE; echo \"Code age: \$AGE_DAYS days (stale)\" >&2; fi; else echo NOT_FOUND; fi; else echo NOT_FOUND; fi"

# Use AWS SSM to execute command
COMMAND_ID=$(aws ssm send-command \
 --instance-ids "$INSTANCE_ID" \
 --document-name "AWS-RunShellScript" \
 --parameters "commands=[$CHECK_CMD]" \
 --output text \
 --query 'Command.CommandId' 2>/dev/null)

if [[ -z "$COMMAND_ID" ]]; then
 echo "✗ Could not execute SSM command"
 exit 1
fi

# Wait for command to complete
sleep 2

# Get command output
RESULT=$(aws ssm get-command-invocation \
 --command-id "$COMMAND_ID" \
 --instance-id "$INSTANCE_ID" \
 --query 'StandardOutputContent' \
 --output text 2>/dev/null | grep -E "(EXISTS_RECENT|EXISTS_STALE|NOT_FOUND)" | head -1)

case "$RESULT" in
 EXISTS_RECENT)
 echo "✓ Code found on EBS volume (recent)"
 echo " Skipping code sync - will reuse code from EBS"
 exit 0
 ;;
 EXISTS_STALE)
 echo "Warning: Code found on EBS volume (stale)"
 echo " Code is older than $MAX_AGE_DAYS days"
 echo " Will sync fresh code"
 exit 1
 ;;
 NOT_FOUND|*)
 echo "✗ Code not found on EBS volume"
 echo " Will sync code from local"
 exit 1
 ;;
esac
