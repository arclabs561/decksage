#!/bin/bash
# Daily automated update: Graph + Embeddings + Quick Evaluation
# Runs daily at 2 AM UTC (or manually)
# 
# This script:
# 1. Updates incremental graph with new deck data
# 2. Detects new cards and updates embeddings incrementally
# 3. Runs quick evaluation (smoke test)
# 4. Reports status

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$PROJECT_ROOT"

# Parse arguments
DRY_RUN=false
while [[ $# -gt 0 ]]; do
 case $1 in
 --dry-run)
 DRY_RUN=true
 shift
 ;;
 *)
 echo "Unknown option: $1"
 echo "Usage: $0 [--dry-run]"
 exit 1
 ;;
 esac
done

LOG_DIR="${LOG_DIR:-logs/daily}"
mkdir -p "$LOG_DIR"
DAY=$(date +%Y%m%d)
LOG_FILE="$LOG_DIR/daily_update_${DAY}.log"
JSON_LOG_FILE="$LOG_DIR/daily_update_${DAY}.jsonl"

exec > >(tee -a "$LOG_FILE")
exec 2>&1

echo "======================================================================"
if [[ "$DRY_RUN" == "true" ]]; then
 echo "DAILY UPDATE (DRY-RUN): $(date '+%Y-%m-%d %H:%M:%S')"
else
 echo "DAILY UPDATE: $(date '+%Y-%m-%d %H:%M:%S')"
fi
echo "======================================================================"
echo ""

# Configuration (must be before validation)
GRAPH_PATH="${GRAPH_PATH:-data/graphs/incremental_graph.json}"
NEW_DECKS_PATH="${NEW_DECKS_PATH:-data/processed/decks_new.jsonl}"
GNN_MODEL_PATH="${GNN_MODEL_PATH:-data/embeddings/gnn_graphsage.json}"
QUICK_TEST_SET="${QUICK_TEST_SET:-experiments/test_set_unified_magic.json}"

# Pre-flight validation
echo "Pre-flight validation..."
if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY-RUN] Skipping validation (would check files and dependencies)"
    echo "[DRY-RUN] Would validate data lineage"
else
    # Validate data lineage
    if [[ -f "scripts/data_processing/validate_lineage.py" ]]; then
        echo " Validating data lineage..."
        python3 scripts/data_processing/validate_lineage.py || {
            echo "⚠️  Data lineage validation failed, but continuing..."
        }
    fi
 # Basic file checks
 if [[ ! -f "$GRAPH_PATH" ]] && [[ "$GRAPH_PATH" != s3://* ]]; then
 echo "Warning: Graph file not found (will be created): $GRAPH_PATH"
 else
 echo " ✓ Graph file: $GRAPH_PATH"
 fi
 
 if [[ ! -f "$GNN_MODEL_PATH" ]] && [[ "$GNN_MODEL_PATH" != s3://* ]]; then
 echo "Warning: GNN model not found (will use default): $GNN_MODEL_PATH"
 else
 echo " ✓ GNN model: $GNN_MODEL_PATH"
 fi
fi
echo ""

# Step 1: Update incremental graph
echo "Step 1: Updating incremental graph..."
if [[ "$DRY_RUN" == "true" ]]; then
 echo "[DRY-RUN] Would update graph from $NEW_DECKS_PATH"
 echo "[DRY-RUN] Would run: ml.scripts.update_graph_incremental --graph-path $GRAPH_PATH --decks-path $NEW_DECKS_PATH"
elif [[ -f "$NEW_DECKS_PATH" ]]; then
 uv run python -m ml.scripts.update_graph_incremental \
 --graph-path "$GRAPH_PATH" \
 --decks-path "$NEW_DECKS_PATH" \
 2>&1 | tee -a "$LOG_FILE"
 echo "✓ Graph updated"
else
 echo "Warning: No new decks found at $NEW_DECKS_PATH"
 echo " Skipping graph update"
fi
echo ""

# Step 2: Update embeddings (incremental for new cards)
echo "Step 2: Updating embeddings incrementally..."
if [[ "$DRY_RUN" == "true" ]]; then
 echo "[DRY-RUN] Would update embeddings incrementally"
 echo "[DRY-RUN] Would run: ml.scripts.update_embeddings_hybrid --graph-path $GRAPH_PATH --gnn-model-path $GNN_MODEL_PATH --schedule daily"
else
 uv run python -m ml.scripts.update_embeddings_hybrid \
 --graph-path "$GRAPH_PATH" \
 --gnn-model-path "$GNN_MODEL_PATH" \
 --schedule daily \
 2>&1 | tee -a "$LOG_FILE"
 echo "✓ Embeddings updated"
fi
echo ""

# Step 3: Sync to S3 (backup)
echo "Step 3: Syncing critical data to S3..."
if [[ "$DRY_RUN" == "true" ]]; then
 echo "[DRY-RUN] Would sync to S3: graphs, embeddings, experiments"
 echo "[DRY-RUN] Would run: scripts/data_processing/sync_all_to_s3.sh"
else
 if [[ -f "scripts/data_processing/sync_all_to_s3.sh" ]]; then
 bash scripts/data_processing/sync_all_to_s3.sh 2>&1 | tee -a "$LOG_FILE"
 echo "✓ S3 sync complete"
 else
 echo "Warning: Sync script not found, skipping S3 sync"
 fi
fi
echo ""

# Step 4: Quick evaluation (smoke test)
echo "Step 4: Running quick evaluation (smoke test)..."
if [[ "$DRY_RUN" == "true" ]]; then
 echo "[DRY-RUN] Would run quick evaluation"
 echo "[DRY-RUN] Would run: ml.evaluation.evaluate_hybrid_with_runctl --test-set $QUICK_TEST_SET --graph $GRAPH_PATH --gnn-model $GNN_MODEL_PATH --quick --limit 20"
elif [[ -f "$QUICK_TEST_SET" ]]; then
 # Run on subset (first 20 queries)
 uv run python -m ml.evaluation.evaluate_hybrid_with_runctl \
 --test-set "$QUICK_TEST_SET" \
 --graph "$GRAPH_PATH" \
 --gnn-model "$GNN_MODEL_PATH" \
 --quick \
 --limit 20 \
 2>&1 | tee -a "$LOG_FILE"
 echo "✓ Quick evaluation complete"
else
 echo "Warning: Test set not found, skipping evaluation"
fi
echo ""

# Step 4: Report status
echo "======================================================================"
echo "DAILY UPDATE COMPLETE"
echo "======================================================================"
echo "Log: $LOG_FILE"
echo ""

# Upload log to S3 for tracking
if command -v s5cmd >/dev/null 2>&1; then
 s5cmd cp "$LOG_FILE" "s3://games-collections/logs/daily/" 2>&1 | grep -v "^$" || true
 echo "✓ Log uploaded to S3"
fi

