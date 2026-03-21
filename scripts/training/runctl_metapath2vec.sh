#!/usr/bin/env bash
set -euo pipefail
#
# runctl wrapper for MetaPath2Vec training
# Supports local, AWS, and sweep modes
#
# Usage:
#   ./scripts/training/runctl_metapath2vec.sh local               # Train locally (1 game)
#   ./scripts/training/runctl_metapath2vec.sh local-all            # Train all 3 games locally
#   ./scripts/training/runctl_metapath2vec.sh aws                  # Create instance + train all games
#   ./scripts/training/runctl_metapath2vec.sh aws <instance-id>    # Train on existing instance
#
# Environment variables:
#   GAME=magic|pokemon|yugioh  (default: magic, ignored for *-all modes)
#   EPOCHS=160                 (training epochs)
#   WALKS=30                   (walks per node)
#   LR=0.003                   (learning rate)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

MODE="${1:-local}"
shift || true

GAME="${GAME:-magic}"
DIM="${DIM:-128}"
EPOCHS="${EPOCHS:-160}"
WALKS="${WALKS:-30}"
LR="${LR:-0.003}"
BATCH="${BATCH:-256}"
ALL_GAMES=(magic pokemon yugioh)

RUNCTL_BIN="${RUNCTL_BIN:-runctl}"
S3_DATA="s3://games-collections/graphs/"
S3_OUTPUT="s3://games-collections/embeddings/"

train_one() {
    local game="$1"
    echo ""
    echo "=== MetaPath2Vec [$game] epochs=$EPOCHS walks=$WALKS lr=$LR ==="
    uv run scripts/training/train_metapath2vec.py \
        --game "$game" \
        --dim "$DIM" \
        --epochs "$EPOCHS" \
        --walks-per-node "$WALKS" \
        --lr "$LR" \
        --batch-size "$BATCH"

    echo ""
    echo "Evaluating $game..."
    uv run scripts/evaluation/eval_per_mode.py \
        --game "$game" \
        --embedding "${game}_metapath2vec"
}

case "$MODE" in
    local)
        cd "$PROJECT_ROOT"
        train_one "$GAME"
        ;;

    local-all)
        cd "$PROJECT_ROOT"
        for game in "${ALL_GAMES[@]}"; do
            train_one "$game"
        done
        ;;

    aws)
        INSTANCE_ID="${1:-}"
        shift || true

        if [ -z "$INSTANCE_ID" ]; then
            echo "Creating AWS instance..."
            INSTANCE_ID=$("$RUNCTL_BIN" aws create c5.xlarge \
                --spot --max-hourly-usd 0.20 --ttl-minutes 180 \
                --iam-instance-profile runctl-ssm-profile \
                --wait --project-name decksage \
                -c "$PROJECT_ROOT/runctl.toml" \
                --output json 2>/dev/null | grep -o '"i-[^"]*"' | tr -d '"')
            echo "  Instance: $INSTANCE_ID"
        fi

        echo "Training all games on AWS instance $INSTANCE_ID"
        echo "  S3 data: $S3_DATA -> data/graphs/"
        echo "  S3 output: $S3_OUTPUT"

        # Train all games sequentially (each run uses --output-suffix for isolation)
        for game in "${ALL_GAMES[@]}"; do
            echo ""
            echo "=== Starting $game ==="
            "$RUNCTL_BIN" aws train "$INSTANCE_ID" \
                "scripts/training/train_metapath2vec.py" \
                --data-s3 "$S3_DATA" \
                --output-s3 "$S3_OUTPUT" \
                --sync-code \
                --project-name decksage \
                -c "$PROJECT_ROOT/runctl.toml" \
                --wait --timeout 60 \
                -- \
                    "--game" "$game" \
                    "--dim" "$DIM" \
                    "--epochs" "$EPOCHS" \
                    "--walks-per-node" "$WALKS" \
                    "--lr" "$LR" \
                    "--batch-size" "$BATCH" \
                    "$@"
        done

        echo ""
        echo "All games complete. Monitor: $RUNCTL_BIN aws monitor $INSTANCE_ID"
        ;;

    sweep)
        echo "Running local sweep..."
        cd "$PROJECT_ROOT"
        for epochs in 40 80 160; do
            for walks in 10 20 30; do
                for lr in 0.01 0.005 0.003 0.001; do
                    echo ""
                    echo "=== epochs=$epochs walks=$walks lr=$lr ==="
                    EPOCHS=$epochs WALKS=$walks LR=$lr \
                        "$0" local 2>&1 | tail -10
                done
            done
        done
        ;;

    *)
        echo "Unknown mode: $MODE"
        echo "Usage: $0 {local|local-all|aws [instance-id]|sweep}"
        exit 1
        ;;
esac
