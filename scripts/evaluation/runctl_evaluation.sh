#!/usr/bin/env bash
set -euo pipefail
# /// script
# requires-python = ">=3.11"
# ///
#
# Runctl wrapper for LLM-based evaluation with GPT-5.2
# Usage: ./scripts/runctl_evaluation.sh [local|aws] [options...]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

MODE="${1:-local}"
shift || true

# Default parameters
TEST_SET="${TEST_SET:-experiments/test_set_unified_magic.json}"
EMBEDDINGS="${EMBEDDINGS:-data/embeddings/multitask_embeddings.wv}"
OUTPUT_DIR="${OUTPUT_DIR:-experiments/evaluations}"
BATCH_SIZE="${BATCH_SIZE:-20}"

# S3 paths (for cloud)
S3_DATA="${S3_DATA:-s3://games-collections/}"
S3_OUTPUT="${S3_OUTPUT:-s3://games-collections/evaluations/}"

echo "Starting LLM evaluation with runctl (mode: $MODE)"
echo "   Test set: $TEST_SET"
echo "   Embeddings: $EMBEDDINGS"
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
        echo "Local evaluation mode"
        cd "$PROJECT_ROOT"

        # Ensure output directory exists
        mkdir -p "$OUTPUT_DIR"

        # Run evaluation (generates predictions and evaluates them)
        EMBEDDINGS_DIR="$(dirname "$EMBEDDINGS")"
        "$RUNCTL_BIN" local "src/ml/scripts/evaluate_all_embeddings.py" -- \
                "--test-set" "$TEST_SET" \
                "--embeddings-dir" "$EMBEDDINGS_DIR" \
                "--output" "$OUTPUT_DIR/evaluation_results.json" \
                "--fast" \
                "$@"
        ;;

    aws)
        echo "Cloud evaluation mode"
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

        # Run evaluation (generates predictions and evaluates them)
        "$RUNCTL_BIN" aws train "$INSTANCE_ID" \
            "src/ml/scripts/evaluate_all_embeddings.py" \
            --output-s3 "$S3_OUTPUT" \
            -- \
                "--test-set" "test_set_canonical_magic.json" \
                "--embeddings-dir" "embeddings" \
                "--output" "evaluations/evaluation_results.json" \
                "$@"
        ;;

    *)
        echo "Unknown mode: $MODE"
        echo "   Use: local or aws"
        exit 1
        ;;
esac

echo ""
echo "Evaluation completed!"
