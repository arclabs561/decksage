#!/usr/bin/env bash
set -euo pipefail
# Runctl wrapper for downstream task evaluation
# Usage: ./scripts/evaluation/runctl_downstream_eval.sh aws <instance-id> [options...]
# Note: Use AWS for efficiency per project rules

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# For runctl, check both relative to project root and absolute
RUNCTL_DIR="${RUNCTL_DIR:-$PROJECT_ROOT/../runctl}"
if [[ ! -d "$RUNCTL_DIR" ]] && [[ -d "../runctl" ]]; then
 RUNCTL_DIR="../runctl"
fi

MODE="${1:-aws}"
if [[ "$MODE" == "local" ]]; then
 echo "Warning: Local mode not recommended for evaluation. Use AWS for efficiency."
fi
shift || true

# Default parameters
GAME="${GAME:-magic}"

# EBS volume settings (for persistent data storage - avoids re-syncing from S3)
# Set USE_EBS=false to disable EBS and use S3 sync instead
USE_EBS="${USE_EBS:-true}"
DATA_VOLUME_SIZE="${DATA_VOLUME_SIZE:-500}" # GB - adjust based on dataset size

# S3 paths (for cloud - per cursor rules)
# If using EBS, data is pre-warmed on volume, S3 used for initial setup and output
S3_DATA="${S3_DATA:-s3://games-collections/}"
S3_OUTPUT="${S3_OUTPUT:-s3://games-collections/experiments/}"

# Local paths (will be synced to S3 by runctl, or accessed from EBS if mounted)
# EBS volume is typically mounted at /data or /mnt/data
EMBEDDINGS="${EMBEDDINGS:-embeddings/trained/production.wv}"
PAIRS="${PAIRS:-processed/pairs_large.csv}"
TEST_DECKS="${TEST_DECKS:-experiments/downstream_test_data/magic_refinement_test_decks.jsonl}"
TEST_SUBS="${TEST_SUBS:-experiments/downstream_test_data/magic_substitution_test_pairs.json}"
TEST_CTX="${TEST_CTX:-experiments/downstream_test_data/magic_contextual_test_queries.json}"
OUTPUT="${OUTPUT:-experiments/downstream_evaluation_magic.json}"

echo "Starting downstream task evaluation with runctl (mode: $MODE)"
echo " Game: $GAME"
if [[ "$USE_EBS" == "true" ]]; then
 echo " Using EBS volume: ${DATA_VOLUME_SIZE}GB (persistent data storage)"
 echo " Benefits: Faster access, no repeated S3 downloads, persistent across restarts"
else
 echo " Using S3 sync (EBS disabled)"
fi
echo " S3 data: $S3_DATA"
echo " S3 output: $S3_OUTPUT"
echo ""

# Find or build runctl
# Default location: parent directory (relative to project root)
RUNCTL_BIN="${RUNCTL_BIN:-}"
if [[ -z "$RUNCTL_BIN" ]]; then
 # Try absolute path first
 if [[ -f "$RUNCTL_DIR/target/release/runctl" ]]; then
 RUNCTL_BIN="$(cd "$RUNCTL_DIR" && pwd)/target/release/runctl"
 elif [[ -f "$PROJECT_ROOT/../runctl/target/release/runctl" ]]; then
 RUNCTL_BIN="$(cd "$PROJECT_ROOT/../runctl" && pwd)/target/release/runctl"
 elif command -v runctl &> /dev/null; then
 RUNCTL_BIN="runctl"
 else
 # Default to absolute path
 RUNCTL_BIN="$(cd "$PROJECT_ROOT/../runctl" && pwd)/target/release/runctl"
 fi
fi

if [[ ! -f "$RUNCTL_BIN" ]] && [[ "$RUNCTL_BIN" != "runctl" ]]; then
 if [[ -d "$RUNCTL_DIR" ]]; then
 echo "Warning: runctl not found, building from $RUNCTL_DIR..."
 (cd "$RUNCTL_DIR" && cargo build --release) || {
 echo "Error: Failed to build runctl"
 echo " Build manually: cd $RUNCTL_DIR && cargo build --release"
 exit 1
 }
 # Re-check after build with absolute path
 if [[ -f "$RUNCTL_DIR/target/release/runctl" ]]; then
 RUNCTL_BIN="$(cd "$RUNCTL_DIR" && pwd)/target/release/runctl"
 else
 echo "Error: runctl still not found after build"
 exit 1
 fi
 else
 echo "Error: runctl directory not found at $RUNCTL_DIR"
 echo " Please ensure runctl is in the parent directory"
 exit 1
 fi
fi

case "$MODE" in
 aws)
 INSTANCE_ID="${1:-${INSTANCE_ID:-}}"
 DATA_VOLUME_SIZE="${DATA_VOLUME_SIZE:-500}"
 USE_EBS="${USE_EBS:-true}"
 
 if [[ -z "$INSTANCE_ID" ]]; then
 echo "No instance ID provided, creating spot instance..."
 INSTANCE_TYPE="${INSTANCE_TYPE:-g4dn.xlarge}"
 echo " Instance type: $INSTANCE_TYPE"
 
 # Check for existing EBS volume for this project
 if [[ "$USE_EBS" == "true" ]]; then
 echo " Checking for existing EBS volume..."
 EXISTING_VOLUME=$("$RUNCTL_BIN" aws ebs list 2>&1 | grep -i "decksage\|evaluation\|data" | head -1 | awk '{print $1}' || echo "")
 if [[ -n "$EXISTING_VOLUME" && "$EXISTING_VOLUME" =~ ^vol- ]]; then
 echo " Found existing volume: $EXISTING_VOLUME"
 echo " Note: Will create new instance, existing volume can be attached manually if needed"
 echo " To attach: $RUNCTL_BIN aws ebs attach $EXISTING_VOLUME --instance-id <instance-id>"
 else
 echo " Will create new EBS volume (${DATA_VOLUME_SIZE}GB) for persistent data"
 echo " Volume will be auto-mounted at /mnt/data by user-data script"
 fi
 
 CREATE_OUTPUT=$("$RUNCTL_BIN" aws create --spot --data-volume-size "$DATA_VOLUME_SIZE" --iam-instance-profile EC2-SSM-InstanceProfile --key-name tarek "$INSTANCE_TYPE" 2>&1)
 else
 CREATE_OUTPUT=$("$RUNCTL_BIN" aws create --spot --iam-instance-profile EC2-SSM-InstanceProfile --key-name tarek "$INSTANCE_TYPE" 2>&1)
 fi
 
 echo "$CREATE_OUTPUT"
 # Extract instance ID from output (handles both spot and on-demand fallback)
 # Look for "Created spot instance: i-xxx" or "Created on-demand instance: i-xxx" pattern
 INSTANCE_ID=$(echo "$CREATE_OUTPUT" | grep -oE '(Created (spot|on-demand) instance|Instance ID): i-[a-z0-9]+' | grep -oE 'i-[a-z0-9]+' | head -1 || echo "")
 
 # If still not found, try to find any instance ID pattern
 if [[ -z "$INSTANCE_ID" ]]; then
 INSTANCE_ID=$(echo "$CREATE_OUTPUT" | grep -oE 'i-[a-z0-9]{17}' | head -1 || echo "")
 fi
 
 if [[ -z "$INSTANCE_ID" ]]; then
 echo "Could not determine instance ID from output."
 echo "Output was:"
 echo "$CREATE_OUTPUT"
 echo ""
 echo "Please create manually and provide instance ID:"
 if [[ "$USE_EBS" == "true" ]]; then
 echo " $RUNCTL_BIN aws create --spot --data-volume-size $DATA_VOLUME_SIZE --iam-instance-profile EC2-SSM-InstanceProfile --key-name tarek $INSTANCE_TYPE"
 else
 echo " $RUNCTL_BIN aws create --spot --iam-instance-profile EC2-SSM-InstanceProfile --key-name tarek $INSTANCE_TYPE"
 fi
 echo " Then run: $0 aws <instance-id>"
 exit 1
 fi
 echo "Using instance: $INSTANCE_ID"
 echo "Waiting for instance to be ready and EBS volume to mount..."
 
 # Wait for instance to be running
 echo " Waiting for instance to be running..."
 for i in {1..30}; do
 STATE=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --query 'Reservations[0].Instances[0].State.Name' --output text 2>/dev/null || echo "unknown")
 if [[ "$STATE" == "running" ]]; then
 break
 fi
 sleep 2
 done
 
 # If using EBS, wait for volume to be attached and give time for user-data to mount it
 if [[ "$USE_EBS" == "true" ]]; then
 echo " Waiting for EBS volume to attach and mount (user-data script)..."
 sleep 30 # Give user-data script time to format and mount volume
 
 # Check if volume is attached
 VOLUME_ID=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --query 'Reservations[0].Instances[0].BlockDeviceMappings[?DeviceName==`/dev/sdf`].Ebs.VolumeId' --output text 2>/dev/null || echo "")
 if [[ -n "$VOLUME_ID" && "$VOLUME_ID" != "None" ]]; then
 echo " EBS volume attached: $VOLUME_ID"
 echo " Volume should be mounted at /mnt/data by user-data script"
 fi
 else
 sleep 15 # Standard wait without EBS
 fi
 fi
 shift || true
 
 echo "AWS evaluation mode (instance: $INSTANCE_ID)"
 echo " S3 data: $S3_DATA"
 echo " S3 output: $S3_OUTPUT"
 echo ""
 
 # Get instance key name to set SSH_KEY_PATH
 INSTANCE_KEY=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --query 'Reservations[0].Instances[0].KeyName' --output text 2>&1)
 if [[ -n "$INSTANCE_KEY" && "$INSTANCE_KEY" != "None" ]]; then
 # Try to find the key file
 if [[ -f "$HOME/.ssh/${INSTANCE_KEY}.pem" ]]; then
 export SSH_KEY_PATH="$HOME/.ssh/${INSTANCE_KEY}.pem"
 echo " Using SSH key: $SSH_KEY_PATH"
 elif [[ -f "$HOME/.ssh/${INSTANCE_KEY}" ]]; then
 export SSH_KEY_PATH="$HOME/.ssh/${INSTANCE_KEY}"
 echo " Using SSH key: $SSH_KEY_PATH"
 fi
 fi
 
 # Fallback to tarek key if available
 if [[ -z "${SSH_KEY_PATH:-}" ]] && [[ -f "$HOME/.ssh/tarek.pem" ]]; then
 export SSH_KEY_PATH="$HOME/.ssh/tarek.pem"
 echo " Using fallback SSH key: $SSH_KEY_PATH"
 fi
 
 # Use shell-based sync for better reliability (works with SSH or SSM)
 export TRAINCTL_USE_SHELL_SYNC=1
 
 # runctl syncs code to /home/{user}/{project_name}/ and runs from that directory
 # Script path is relative to project root (runctl syncs entire project)
 # Use --data-s3 and --output-s3 per cursor rules
 cd "$PROJECT_ROOT" || exit 1
 
 # Ensure we're in the right directory for runctl
 # runctl syncs to /home/ec2-user/<project-name>/ by default
 PROJECT_NAME=$(basename "$PROJECT_ROOT")
 
 # Export environment variables for runctl
 export TRAINCTL_USE_SHELL_SYNC=1 # Use shell-based sync for reliability
 export SSH_KEY_PATH="${SSH_KEY_PATH:-$HOME/.ssh/tarek.pem}"
 
 echo "Syncing code to instance..."
 echo " Syncing from: src/ml/scripts"
 
 "$RUNCTL_BIN" aws train "$INSTANCE_ID" \
 "src/ml/scripts/evaluate_downstream_complete.py" \
 --data-s3 "$S3_DATA" \
 --output-s3 "$S3_OUTPUT" \
 --project-name "$PROJECT_NAME" \
 -- \
 --game "$GAME" \
 --embeddings "$EMBEDDINGS" \
 --pairs "$PAIRS" \
 --test-decks "$TEST_DECKS" \
 --test-substitutions "$TEST_SUBS" \
 --test-contextual "$TEST_CTX" \
 --output "$OUTPUT" \
 "$@"
 ;;
 *)
 echo "Unknown mode: $MODE"
 echo " Usage: $0 aws [instance-id] [options...]"
 echo " If no instance-id provided, will create spot instance automatically"
 exit 1
 ;;
esac

echo ""
echo "Evaluation completed!"
echo ""
echo "To check status without hanging:"
echo " ssh -i ~/.ssh/tarek.pem ec2-user@<instance-ip> 'tail -f /home/ec2-user/dev/training.log'"
echo " aws s3 ls s3://games-collections/experiments/downstream_evaluation_*.json"
echo " aws ssm list-commands --instance-id $INSTANCE_ID --max-items 1"

