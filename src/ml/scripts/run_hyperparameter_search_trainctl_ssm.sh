#!/bin/bash
# Run hyperparameter search with runctl using SSM (no SSH key needed)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
RUNCTL_BIN="${RUNCTL_BIN:-$PROJECT_ROOT/../runctl/target/release/runctl}"

echo "🚀 Starting hyperparameter search with SSM..."

# Use existing instance or create new
INSTANCE_ID=$(aws ec2 describe-instances \
    --filters "Name=instance-state-name,Values=running" "Name=instance-type,Values=g4dn.xlarge" \
    --query 'Reservations[0].Instances[0].InstanceId' \
    --output text 2>/dev/null | head -1)

if [ -z "$INSTANCE_ID" ] || [ "$INSTANCE_ID" = "None" ]; then
    echo "⏳ Creating new instance..."
    INSTANCE_OUTPUT=$($RUNCTL_BIN aws create --spot g4dn.xlarge 2>&1)
    INSTANCE_ID=$(echo "$INSTANCE_OUTPUT" | grep -o 'i-[a-z0-9]*' | head -1)
    
    if [ -z "$INSTANCE_ID" ]; then
        echo "❌ Failed to create instance"
        exit 1
    fi
    
    echo "✅ Instance created: $INSTANCE_ID"
    sleep 30
else
    echo "✅ Using existing instance: $INSTANCE_ID"
fi

# Run training (runctl should use SSM automatically if no SSH key)
echo "Starting hyperparameter search..."
$RUNCTL_BIN aws train "$INSTANCE_ID" \
    src/ml/scripts/improve_embeddings_hyperparameter_search.py \
    --output-s3 s3://games-collections/experiments/ \
    -- \
    --input s3://games-collections/processed/pairs_large.csv \
    --output s3://games-collections/experiments/hyperparameter_results.json \
    --test-set s3://games-collections/processed/test_set_canonical_magic.json

echo "✅ Training started. Monitoring..."
$RUNCTL_BIN aws monitor "$INSTANCE_ID" --follow
