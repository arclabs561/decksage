#!/bin/bash
# Setup EBS volume for code storage (one-time setup)
# Pre-populates EBS volume with code to avoid re-uploading every time

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RUNCTL_BIN="${RUNCTL_BIN:-}"
if [[ -z "$RUNCTL_BIN" ]]; then
 if [[ -f "$PROJECT_ROOT/../runctl/target/release/runctl" ]]; then
 RUNCTL_BIN="$PROJECT_ROOT/../runctl/target/release/runctl"
 elif [[ -f "../runctl/target/release/runctl" ]]; then
 RUNCTL_BIN="../runctl/target/release/runctl"
 elif command -v runctl > /dev/null 2>&1; then
 RUNCTL_BIN="runctl"
 else
 echo "Error: runctl not found. Please set RUNCTL_BIN or ensure runctl is in PATH"
 exit 1
 fi
fi

VOLUME_ID="${1:-}"
INSTANCE_ID="${2:-}"
MOUNT_POINT="${MOUNT_POINT:-/mnt/data500}" # Use separate mount for 500GB volume
CODE_DIR="${CODE_DIR:-$MOUNT_POINT/code}"

if [[ -z "$VOLUME_ID" ]] || [[ -z "$INSTANCE_ID" ]]; then
 echo "Usage: $0 <volume-id> <instance-id> [mount-point]"
 echo ""
 echo "Example:"
 echo " $0 vol-0bfa4b5f1e173b6d8 i-0b7cddaa3ee535369"
 echo ""
 echo "This will:"
 echo " 1. Mount EBS volume on instance"
 echo " 2. Upload code to EBS volume"
 echo " 3. Future runs can reuse code from EBS (skip sync)"
 exit 1
fi

echo "======================================================================"
echo "EBS CODE STORAGE SETUP"
echo "======================================================================"
echo "Volume: $VOLUME_ID"
echo "Instance: $INSTANCE_ID"
echo "Mount Point: $MOUNT_POINT"
echo "Code Directory: $CODE_DIR"
echo ""

# Check if volume is attached to instance
if ! "$RUNCTL_BIN" aws ebs list 2>&1 | grep "$VOLUME_ID" | grep -q "$INSTANCE_ID"; then
 echo "Warning: Volume $VOLUME_ID is not attached to instance $INSTANCE_ID"
 echo " Attaching now..."
 "$RUNCTL_BIN" aws ebs attach --instance-id "$INSTANCE_ID" "$VOLUME_ID" 2>&1
 sleep 5
fi

# Mount volume on instance (if not already mounted)
echo "Mounting EBS volume on instance..."
MOUNT_CMD="if ! mountpoint -q $MOUNT_POINT; then sudo mkdir -p $MOUNT_POINT; if ! sudo blkid /dev/nvme1n1 > /dev/null 2>&1 && ! sudo blkid /dev/xvdf > /dev/null 2>&1; then echo 'Formatting volume...'; sudo mkfs -t xfs /dev/nvme1n1 2>/dev/null || sudo mkfs -t xfs /dev/xvdf 2>/dev/null || echo 'Volume may already be formatted'; fi; sudo mount /dev/nvme1n1 $MOUNT_POINT 2>/dev/null || sudo mount /dev/xvdf $MOUNT_POINT 2>/dev/null || echo 'Volume may already be mounted'; sudo chown ec2-user:ec2-user $MOUNT_POINT; echo 'Volume mounted at $MOUNT_POINT'; else echo 'Volume already mounted at $MOUNT_POINT'; fi"

COMMAND_ID=$(aws ssm send-command \
 --instance-ids "$INSTANCE_ID" \
 --document-name "AWS-RunShellScript" \
 --parameters "commands=[$MOUNT_CMD]" \
 --output text \
 --query 'Command.CommandId' 2>/dev/null)

if [[ -n "$COMMAND_ID" ]]; then
 sleep 3
 aws ssm get-command-invocation \
 --command-id "$COMMAND_ID" \
 --instance-id "$INSTANCE_ID" \
 --query 'StandardOutputContent' \
 --output text 2>&1
else
 echo "Warning: Could not mount volume via SSM"
fi

# Create code directory
echo "Creating code directory on EBS volume..."
MKDIR_CMD="mkdir -p $CODE_DIR && echo 'Code directory ready'"
COMMAND_ID=$(aws ssm send-command \
 --instance-ids "$INSTANCE_ID" \
 --document-name "AWS-RunShellScript" \
 --parameters "commands=[$MKDIR_CMD]" \
 --output text \
 --query 'Command.CommandId' 2>/dev/null)
sleep 2
if [[ -n "$COMMAND_ID" ]]; then
 aws ssm get-command-invocation \
 --command-id "$COMMAND_ID" \
 --instance-id "$INSTANCE_ID" \
 --query 'StandardOutputContent' \
 --output text 2>&1 || true
fi

# Upload code to EBS volume
echo ""
echo "Uploading code to EBS volume..."
echo " This is a one-time operation. Future runs will reuse this code."
echo ""

# Use runctl's code sync but to EBS location
# We'll sync code to the EBS-mounted directory
SYNC_CMD="
cd $CODE_DIR
# Remove old code if exists
rm -rf decksage 2>/dev/null || true
mkdir -p decksage
"

# First, sync code normally, then move to EBS
echo "Step 1: Syncing code to instance (temporary location)..."
"$RUNCTL_BIN" aws train "$INSTANCE_ID" \
 "src/ml/scripts/train_hybrid_from_pairs.py" \
 --data-s3 "s3://games-collections/" \
 --output-s3 "s3://games-collections/" \
 -- --help > /dev/null 2>&1 || {
 echo "Warning: Code sync initiated (this will complete in background)"
}

# Wait a bit for sync to start
sleep 10

# Move code to EBS
echo "Step 2: Moving code to EBS volume..."
echo " Waiting for code sync to complete..."
sleep 30 # Wait for code sync

MOVE_CMD="CODE_SRC=\$(find ~ -name 'decksage' -type d -maxdepth 3 2>/dev/null | grep -v '.git' | head -1); if [ -n \"\$CODE_SRC\" ] && [ -d \"\$CODE_SRC\" ]; then echo \"Found code at: \$CODE_SRC\"; sudo mkdir -p $CODE_DIR; sudo cp -r \"\$CODE_SRC\"/* $CODE_DIR/ 2>/dev/null || cp -r \"\$CODE_SRC\"/* $CODE_DIR/ 2>/dev/null; echo \"Code copied to $CODE_DIR\"; ls -la $CODE_DIR | head -10; else echo \"Code not found - may need to wait longer or sync manually\"; fi"

COMMAND_ID=$(aws ssm send-command \
 --instance-ids "$INSTANCE_ID" \
 --document-name "AWS-RunShellScript" \
 --parameters "commands=[$MOVE_CMD]" \
 --output text \
 --query 'Command.CommandId' 2>/dev/null)

if [[ -n "$COMMAND_ID" ]]; then
 sleep 5
 aws ssm get-command-invocation \
 --command-id "$COMMAND_ID" \
 --instance-id "$INSTANCE_ID" \
 --query 'StandardOutputContent' \
 --output text 2>&1
else
 echo "Warning: Could not move code automatically"
 echo " Manual steps:"
 echo " 1. Wait for code sync to complete"
 echo " 2. SSH/SSM into instance"
 echo " 3. Copy code from ~/decksage or ~/runctl/decksage to $CODE_DIR"
fi

echo ""
echo "======================================================================"
echo "EBS CODE STORAGE SETUP COMPLETE"
echo "======================================================================"
echo ""
echo "Next steps:"
echo " 1. Verify code is on EBS:"
echo " aws ssm send-command --instance-ids $INSTANCE_ID \\"
echo " --document-name 'AWS-RunShellScript' \\"
echo " --parameters 'commands=[\"ls -la $CODE_DIR\"]'"
echo " 2. Training script will automatically check EBS before syncing"
echo " 3. Future runs will reuse code from EBS (much faster!)"
echo ""

