#!/usr/bin/env bash
set -euo pipefail
#
# runctl wrapper for MetaPath2Vec training
# Supports local, AWS, and RunPod modes
#
# Usage:
#   ./scripts/training/runctl_metapath2vec.sh local           # Train locally
#   ./scripts/training/runctl_metapath2vec.sh aws <instance>  # Train on AWS
#
# Environment variables:
#   GAME=magic|pokemon|yugioh  (default: magic)
#   DIM=128                    (embedding dimension)
#   EPOCHS=40                  (training epochs)
#   WALKS=30                   (walks per node)
#   LR=0.005                   (learning rate)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

MODE="${1:-local}"
shift || true

GAME="${GAME:-magic}"
DIM="${DIM:-128}"
EPOCHS="${EPOCHS:-40}"
WALKS="${WALKS:-30}"
LR="${LR:-0.005}"
BATCH="${BATCH:-256}"

echo "MetaPath2Vec training (mode: $MODE, game: $GAME)"
echo "  dim=$DIM epochs=$EPOCHS walks=$WALKS lr=$LR"

case "$MODE" in
    local)
        echo "Running locally..."
        cd "$PROJECT_ROOT"
        uv run scripts/training/train_metapath2vec.py \
            --game "$GAME" \
            --dim "$DIM" \
            --epochs "$EPOCHS" \
            --walks-per-node "$WALKS" \
            --lr "$LR" \
            --batch-size "$BATCH"

        echo ""
        echo "Evaluating..."
        uv run scripts/evaluation/eval_per_mode.py \
            --game "$GAME" \
            --embedding "${GAME}_metapath2vec"
        ;;

    aws)
        INSTANCE_ID="${1:?Instance ID required}"
        shift || true

        RUNCTL_BIN="${RUNCTL_BIN:-runctl}"
        S3_DATA="s3://games-collections/graphs/"
        S3_OUTPUT="s3://games-collections/embeddings/"

        echo "Training on AWS instance $INSTANCE_ID"
        echo "  S3 data: $S3_DATA"
        echo "  S3 output: $S3_OUTPUT"

        "$RUNCTL_BIN" aws train "$INSTANCE_ID" \
            "scripts/training/train_metapath2vec.py" \
            --data-s3 "$S3_DATA" \
            --output-s3 "$S3_OUTPUT" \
            --sync-code \
            -- \
                "--game" "$GAME" \
                "--dim" "$DIM" \
                "--epochs" "$EPOCHS" \
                "--walks-per-node" "$WALKS" \
                "--lr" "$LR" \
                "--batch-size" "$BATCH" \
                "$@"
        ;;

    sweep)
        echo "Running local sweep..."
        cd "$PROJECT_ROOT"
        for epochs in 20 40 80; do
            for walks in 10 20 30; do
                for lr in 0.01 0.005 0.001; do
                    echo ""
                    echo "=== epochs=$epochs walks=$walks lr=$lr ==="
                    EPOCHS=$epochs WALKS=$walks LR=$lr \
                        "$0" local 2>&1 | tail -10
                done
            done
        done
        ;;

    *)
        echo "Unknown mode: $MODE (use: local, aws, sweep)"
        exit 1
        ;;
esac
