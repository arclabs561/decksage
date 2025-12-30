#!/bin/bash
# Generic wrapper to run any training script with runctl
# Usage: train_with_runctl_wrapper.sh <script_path> <instance_id> [script_args...]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
RUNCTL_BIN="${RUNCTL_BIN:-$PROJECT_ROOT/../runctl/target/release/runctl}"

if [ $# -lt 2 ]; then
    echo "Usage: $0 <script_path> <instance_id> [script_args...]"
    echo ""
    echo "Examples:"
    echo "  $0 src/ml/scripts/compare_embedding_methods.py i-1234567890abcdef0 --input s3://bucket/data.csv"
    echo "  $0 src/ml/scripts/train_all_embeddings.py i-1234567890abcdef0 --dims 64,128,256"
    exit 1
fi

SCRIPT_PATH="$1"
INSTANCE_ID="$2"
shift 2  # Remove script_path and instance_id, keep remaining args

# Check if runctl exists
if [ ! -f "$RUNCTL_BIN" ]; then
    echo "❌ runctl not found at $RUNCTL_BIN"
    echo "   Build it with: cd ../runctl && cargo build --release"
    exit 1
fi

# Check if script exists
if [ ! -f "$SCRIPT_PATH" ]; then
    echo "❌ Script not found: $SCRIPT_PATH"
    exit 1
fi

echo "🚀 Running $SCRIPT_PATH with runctl on instance $INSTANCE_ID"
echo "   Args: $@"
echo ""

# Run with runctl
exec "$RUNCTL_BIN" aws train "$INSTANCE_ID" \
    "$SCRIPT_PATH" \
    --output-s3 s3://games-collections/experiments/ \
    -- \
    "$@"

