#!/bin/bash
# Comprehensive S3 sync for DeckSage data
# Syncs all critical data to S3 with proper organization

set -euo pipefail

BUCKET="s3://games-collections"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "=" | tr '=' '='
echo "S3 DATA SYNC - COMPREHENSIVE"
echo "=" | tr '=' '='
echo

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI not found. Install it first."
    exit 1
fi

# Check bucket access
if ! aws s3 ls "$BUCKET" &> /dev/null; then
    echo "❌ Cannot access bucket: $BUCKET"
    echo "   Check AWS credentials: aws sts get-caller-identity"
    exit 1
fi

echo "✅ Bucket accessible: $BUCKET"
echo

# Sync processed data
echo "📊 Syncing processed data..."
if [ -d "data/processed" ]; then
    aws s3 sync data/processed/ "$BUCKET/processed/" \
        --exclude "*.tmp" \
        --exclude "*.log" \
        --exclude "__pycache__/*" \
        --exclude "*.pyc" \
        --delete
    echo "  ✅ Processed data synced (includes decks_all_final.jsonl)"
else
    echo "  ⚠️  data/processed/ not found"
fi

# Sync embeddings
echo "📊 Syncing embeddings..."
if [ -d "data/embeddings" ]; then
    aws s3 sync data/embeddings/ "$BUCKET/embeddings/"         --exclude "*.tmp"         --exclude "*.log"         --delete
    echo "  ✅ Embeddings synced"
else
    echo "  ⚠️  data/embeddings/ not found"
fi

# Sync experiments
echo "📊 Syncing experiments..."
if [ -d "experiments" ]; then
    aws s3 sync experiments/ "$BUCKET/experiments/"         --exclude "*.tmp"         --exclude "*.log"         --exclude "__pycache__/*"         --exclude "checkpoint_*.json"         --delete
    echo "  ✅ Experiments synced"
else
    echo "  ⚠️  experiments/ not found"
fi

# Sync graphs
echo "📊 Syncing graphs..."
if [ -d "data/graphs" ]; then
    aws s3 sync data/graphs/ "$BUCKET/graphs/"         --exclude "*.tmp"         --exclude "*.log"         --delete
    echo "  ✅ Graphs synced"
else
    echo "  ⚠️  data/graphs/ not found"
fi

echo
echo "=" | tr '=' '='
echo "SYNC COMPLETE"
echo "=" | tr '=' '='
echo

# Show bucket summary
echo "📊 Bucket Summary:"
aws s3 ls "$BUCKET/" --recursive --human-readable --summarize 2>&1 | tail -5
