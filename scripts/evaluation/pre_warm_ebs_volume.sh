#!/usr/bin/env bash
# Pre-warm EBS volume with data from S3
# Usage: ./scripts/evaluation/pre_warm_ebs_volume.sh <volume-id> [instance-id]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
RUNCTL_DIR="${RUNCTL_DIR:-$PROJECT_ROOT/../runctl}"
RUNCTL_BIN="${RUNCTL_BIN:-$RUNCTL_DIR/target/release/runctl}"

VOLUME_ID="${1:-}"
INSTANCE_ID="${2:-}"

if [[ -z "$VOLUME_ID" ]]; then
    echo "Usage: $0 <volume-id> [instance-id]"
    echo ""
    echo "Pre-warms an EBS volume with data from S3 for faster evaluation runs."
    echo ""
    echo "If instance-id is provided, uses that instance for pre-warming."
    echo "Otherwise, creates a temporary instance, pre-warms, then terminates it."
    echo ""
    echo "Example:"
    echo "  $0 vol-1234567890abcdef0 i-0987654321fedcba0"
    exit 1
fi

S3_DATA="${S3_DATA:-s3://games-collections/}"

echo "Pre-warming EBS volume: $VOLUME_ID"
echo "   S3 source: $S3_DATA"
echo ""

# Check if volume exists
if ! aws ec2 describe-volumes --volume-ids "$VOLUME_ID" &>/dev/null; then
    echo "Error: Volume $VOLUME_ID not found"
    exit 1
fi

# Get volume AZ
VOLUME_AZ=$(aws ec2 describe-volumes --volume-ids "$VOLUME_ID" --query 'Volumes[0].AvailabilityZone' --output text)
echo "   Volume AZ: $VOLUME_AZ"

if [[ -z "$INSTANCE_ID" ]]; then
    echo "   Creating temporary instance for pre-warming..."
    CREATE_OUTPUT=$("$RUNCTL_BIN" aws create --spot --instance-type t3.medium --iam-instance-profile EC2-SSM-InstanceProfile --key-name tarek 2>&1)
    INSTANCE_ID=$(echo "$CREATE_OUTPUT" | grep -oE 'i-[a-z0-9]+' | head -1 || echo "")

    if [[ -z "$INSTANCE_ID" ]]; then
        echo "Error: Could not create instance for pre-warming"
        exit 1
    fi

    echo "   Created instance: $INSTANCE_ID"
    echo "   Waiting for instance to be running..."
    sleep 30

    # Attach volume
    echo "   Attaching volume to instance..."
    "$RUNCTL_BIN" aws ebs attach "$VOLUME_ID" --instance-id "$INSTANCE_ID" --device /dev/sdf || {
        echo "Error: Failed to attach volume"
        "$RUNCTL_BIN" aws terminate "$INSTANCE_ID" --force || true
        exit 1
    }

    sleep 10  # Wait for attachment

    TEMP_INSTANCE=true
else
    echo "   Using existing instance: $INSTANCE_ID"
    TEMP_INSTANCE=false
fi

# Pre-warm using runctl
echo "   Pre-warming volume with data from S3..."
"$RUNCTL_BIN" aws ebs pre-warm "$VOLUME_ID" \
    --s3-source "$S3_DATA" \
    --mount-point /mnt/data \
    --instance-id "$INSTANCE_ID" || {
    echo "Error: Pre-warming failed"
    if [[ "$TEMP_INSTANCE" == "true" ]]; then
        "$RUNCTL_BIN" aws terminate "$INSTANCE_ID" --force || true
    fi
    exit 1
}

echo ""
echo "Pre-warming complete!"
echo "   Volume: $VOLUME_ID"
echo "   Data available at /mnt/data on attached instances"

# Clean up temporary instance
if [[ "$TEMP_INSTANCE" == "true" ]]; then
    echo "   Detaching volume and terminating temporary instance..."
    "$RUNCTL_BIN" aws ebs detach "$VOLUME_ID" || true
    "$RUNCTL_BIN" aws terminate "$INSTANCE_ID" --force || true
fi

echo ""
echo "To use this volume:"
echo "  $RUNCTL_BIN aws ebs attach $VOLUME_ID --instance-id <instance-id> --device /dev/sdf"
echo "  (Volume will be auto-mounted at /mnt/data by user-data script)"
