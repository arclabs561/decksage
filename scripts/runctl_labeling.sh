#!/usr/bin/env bash
# /// script
# requires-python = ">=3.11"
# ///
#
# Runctl wrapper for enhanced labeling with GPT-5.2 and full context
# Usage: ./scripts/runctl_labeling.sh [local|aws] [options...]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

MODE="${1:-local}"
shift || true

# Default parameters
QUERIES_JSON="${QUERIES_JSON:-experiments/test_set_unified_magic.json}"
CARD_ATTRS="${CARD_ATTRS:-data/processed/card_attributes_enriched.csv}"
OUTPUT_DIR="${OUTPUT_DIR:-annotations/enhanced_labels}"
BATCH_SIZE="${BATCH_SIZE:-10}"
MAX_QUERIES="${MAX_QUERIES:-50}"

# S3 paths (for cloud)
S3_DATA="${S3_DATA:-s3://games-collections/processed/}"
S3_OUTPUT="${S3_OUTPUT:-s3://games-collections/annotations/}"

echo "Starting enhanced labeling with runctl (mode: $MODE)"
echo "   Queries: $QUERIES_JSON"
echo "   Card attrs: $CARD_ATTRS"
echo "   Output: $OUTPUT_DIR"
echo "   Model: GPT-5.2 (via pydantic_ai_helpers)"
echo ""

# Find or build runctl (Rust binary)
RUNCTL_BIN="${RUNCTL_BIN:-$PROJECT_ROOT/../runctl/target/release/runctl}"
if [[ ! -f "$RUNCTL_BIN" ]]; then
    echo "runctl not found, building from local project..."
    if [[ -d "$PROJECT_ROOT/../runctl" ]]; then
        (cd "$PROJECT_ROOT/../runctl" && cargo build --release) || {
            echo "Failed to build runctl"
            echo "   Please build manually: cd ../runctl && cargo build --release"
            exit 1
        }
    else
        echo "runctl directory not found"
        exit 1
    fi
fi

case "$MODE" in
    local)
        echo "Local labeling mode"
        cd "$PROJECT_ROOT"

        # Ensure output directory exists
        mkdir -p "$OUTPUT_DIR"

        # Run labeling (using batch script)
        "$RUNCTL_BIN" local "src/ml/scripts/generate_labels_for_new_queries_optimized.py" -- \
                "--input" "$QUERIES_JSON" \
                "--output" "$OUTPUT_DIR/labeled_queries.json" \
                "--batch-size" "$BATCH_SIZE" \
                "$@"
        ;;

    aws)
        echo "Cloud labeling mode"
        echo "   S3 data: $S3_DATA"
        echo "   S3 output: $S3_OUTPUT"

        # Get instance ID from args or env
        INSTANCE_ID="${INSTANCE_ID:-${1:-}}"
        if [[ -z "$INSTANCE_ID" ]]; then
            echo "Instance ID required for cloud mode"
            echo "   Usage: $0 aws <instance-id> [options...]"
            exit 1
        fi
        shift || true

        # Run labeling (using batch script)
        "$RUNCTL_BIN" aws train "$INSTANCE_ID" \
            "src/ml/scripts/generate_labels_for_new_queries_optimized.py" \
            --output-s3 "$S3_OUTPUT" \
            -- \
                "--input" "test_set_unified_magic.json" \
                "--output" "enhanced_labels/labeled_queries.json" \
                "--batch-size" "$BATCH_SIZE" \
                "$@"
        ;;

    *)
        echo "Unknown mode: $MODE"
        echo "   Use: local or aws"
        exit 1
        ;;
esac

echo ""
echo "Labeling completed!"
