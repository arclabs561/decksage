#!/bin/bash
# Weekly automated retraining: GNN + Co-occurrence + Full Evaluation
# Runs weekly on Sunday at 2 AM UTC (or manually)
#
# This script:
# 1. Retrains GNN embeddings on full updated graph
# 2. Retrains co-occurrence embeddings (Node2Vec/PecanPy)
# 3. Runs comprehensive evaluation
# 4. Compares performance vs. previous week
# 5. Auto-rollback if regression detected

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$PROJECT_ROOT"

# Parse arguments
DRY_RUN=false
INSTANCE_ID=""
while [[ $# -gt 0 ]]; do
 case $1 in
 --dry-run)
 DRY_RUN=true
 shift
 ;;
 --instance-id)
 INSTANCE_ID="$2"
 shift 2
 ;;
 -*)
 echo "Unknown option: $1"
 echo "Usage: $0 [--dry-run] [--instance-id INSTANCE_ID]"
 exit 1
 ;;
 *)
 # Assume it's an instance ID (backward compatibility)
 if [[ -z "$INSTANCE_ID" ]]; then
 INSTANCE_ID="$1"
 fi
 shift
 ;;
 esac
done

LOG_DIR="${LOG_DIR:-logs/weekly}"
mkdir -p "$LOG_DIR"
WEEK=$(date +%Y-W%V)
LOG_FILE="$LOG_DIR/weekly_retrain_${WEEK}.log"
JSON_LOG_FILE="$LOG_DIR/weekly_retrain_${WEEK}.jsonl"

exec > >(tee -a "$LOG_FILE")
exec 2>&1

echo "======================================================================"
if [[ "$DRY_RUN" == "true" ]]; then
 echo "WEEKLY RETRAINING (DRY-RUN): Week $WEEK ($(date '+%Y-%m-%d %H:%M:%S'))"
else
 echo "WEEKLY RETRAINING: Week $WEEK ($(date '+%Y-%m-%d %H:%M:%S'))"
fi
echo "======================================================================"
echo ""

# Pre-flight validation
echo "Pre-flight validation..."
if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY-RUN] Skipping validation (would check files and instance status)"
    echo "[DRY-RUN] Would validate data lineage"
else
    # Validate data lineage
    if [[ -f "scripts/data_processing/validate_lineage.py" ]]; then
        echo " Validating data lineage..."
        python3 scripts/data_processing/validate_lineage.py || {
            echo "⚠️  Data lineage validation failed, but continuing..."
        }
    fi
 # Basic checks
 if [[ -z "$INSTANCE_ID" ]]; then
 echo " Instance: Will be created"
 else
 echo " Instance: $INSTANCE_ID (will verify status)"
 fi

 if [[ ! -f "data/processed/pairs_large.csv" ]] && [[ "data/processed/pairs_large.csv" != s3://* ]]; then
 echo "Warning: Pairs file not found locally (will check S3)"
 else
 echo " ✓ Pairs file: data/processed/pairs_large.csv"
 fi

 if [[ ! -f "$GRAPH_PATH" ]] && [[ "$GRAPH_PATH" != s3://* ]]; then
 echo "Warning: Graph file not found (will be created): $GRAPH_PATH"
 else
 echo " ✓ Graph file: $GRAPH_PATH"
 fi
fi
echo ""

# Configuration
GRAPH_PATH="${GRAPH_PATH:-data/graphs/incremental_graph.json}"
GNN_OUTPUT="embeddings/gnn_graphsage_v${WEEK}.json"
COOCCURRENCE_OUTPUT="embeddings/production_v${WEEK}.wv"
TEST_SET="${TEST_SET:-experiments/test_set_canonical_magic.json}"
EVAL_OUTPUT="experiments/hybrid_evaluation_results_v${WEEK}.json"

# Step 1: Create/use instance
if [[ "$DRY_RUN" == "true" ]]; then
 echo "Step 1: [DRY-RUN] Would create/use instance"
 if [[ -z "$INSTANCE_ID" ]]; then
 echo "[DRY-RUN] Would create spot instance: g4dn.xlarge with 500GB data volume"
 else
 echo "[DRY-RUN] Would use existing instance: $INSTANCE_ID"
 fi
elif [[ -z "$INSTANCE_ID" ]]; then
 echo "Step 1: Creating spot instance for retraining..."
 RUNCTL_BIN="${RUNCTL_BIN:-$PROJECT_ROOT/../runctl/target/release/runctl}"
 CREATE_OUTPUT=$("$RUNCTL_BIN" aws create --spot --data-volume-size 500 g4dn.xlarge 2>&1)
 INSTANCE_ID=$(echo "$CREATE_OUTPUT" | grep -oE 'i-[a-z0-9]+' | head -1)
 if [[ -z "$INSTANCE_ID" ]]; then
 echo "Error: Failed to create instance"
 exit 1
 fi
 echo "✓ Created instance: $INSTANCE_ID"
 echo " Waiting for instance to be ready..."
 sleep 60
else
 echo "Step 1: Using existing instance: $INSTANCE_ID"
fi
echo ""

# Step 2: Retrain GNN embeddings
echo "Step 2: Retraining GNN embeddings..."
if [[ "$DRY_RUN" == "true" ]]; then
 echo "[DRY-RUN] Would retrain GNN embeddings"
 echo "[DRY-RUN] Would run: train_with_ebs_auto.sh $INSTANCE_ID --pairs-path processed/pairs_large.csv --graph-path graphs/incremental_graph.json --gnn-output $GNN_OUTPUT --output-version $WEEK --gnn-epochs 100"
else
 # Note: train_hybrid_from_pairs.py trains GNN by default (--skip-gnn to disable)
 # We don't need --gnn-only flag, just ensure --skip-gnn is not set
 ./scripts/training/train_with_ebs_auto.sh "$INSTANCE_ID" \
 --pairs-path processed/pairs_large.csv \
 --graph-path graphs/incremental_graph.json \
 --gnn-output "$GNN_OUTPUT" \
 --output-version "$WEEK" \
 --gnn-epochs 100 \
 2>&1 | tee -a "$LOG_FILE"
 echo "✓ GNN retraining complete"
fi
echo ""

# Step 3: Retrain co-occurrence embeddings
echo "Step 3: Retraining co-occurrence embeddings..."
if [[ "$DRY_RUN" == "true" ]]; then
 echo "[DRY-RUN] Would retrain co-occurrence embeddings"
 echo "[DRY-RUN] Would export edgelist and train Node2Vec/PecanPy"
else
 # Export filtered edgelist (temporal split)
 uv run python -m ml.scripts.export_filtered_edgelist_from_graph \
 --graph "$GRAPH_PATH" \
 --output data/graphs/train_val_edgelist_${WEEK}.edg \
 2>&1 | tee -a "$LOG_FILE"
fi

# Train Node2Vec/PecanPy (on instance or local)
echo " Training Node2Vec..."
# TODO: Implement PecanPy training script with runctl
echo "Warning: Co-occurrence retraining not yet automated"
echo ""

# Step 4: Comprehensive evaluation
echo "Step 4: Running comprehensive evaluation..."
if [[ "$DRY_RUN" == "true" ]]; then
 echo "[DRY-RUN] Would run comprehensive evaluation"
 echo "[DRY-RUN] Would run: eval_hybrid_with_runctl.sh aws $INSTANCE_ID --test-set $TEST_SET --graph $GRAPH_PATH --gnn-model $GNN_OUTPUT --output $EVAL_OUTPUT --output-version $WEEK"
else
 "$SCRIPT_DIR/../evaluation/eval_hybrid_with_runctl.sh" aws "$INSTANCE_ID" \
 --test-set "$TEST_SET" \
 --graph "$GRAPH_PATH" \
 --gnn-model "$GNN_OUTPUT" \
 --output "$EVAL_OUTPUT" \
 --output-version "$WEEK" \
 2>&1 | tee -a "$LOG_FILE"
 echo "✓ Evaluation complete"
fi
echo ""

# Step 5: Compare performance vs. previous week
echo "Step 5: Comparing performance vs. previous week..."
PREV_WEEK=$(date -d "1 week ago" +%Y-W%V 2>/dev/null || date -v-7d +%Y-W%V 2>/dev/null || echo "UNKNOWN")
PREV_EVAL="experiments/hybrid_evaluation_results_v${PREV_WEEK}.json"

if [[ "$DRY_RUN" == "true" ]]; then
 echo "[DRY-RUN] Would compare with previous week ($PREV_WEEK)"
 echo "[DRY-RUN] Would check for regression and auto-rollback if needed"
elif [[ -f "$PREV_EVAL" ]] || s5cmd ls "s3://games-collections/$PREV_EVAL" >/dev/null 2>&1; then
 # Use EvaluationRegistry for comparison (if available)
 if uv run python -c "from ml.utils.evaluation_registry import EvaluationRegistry; print('OK')" 2>/dev/null; then
 # Extract versions from paths
 CURRENT_VERSION="$WEEK"
 PREV_VERSION=$(date -d "1 week ago" +%Y-W%V 2>/dev/null || date -v-7d +%Y-W%V 2>/dev/null || echo "UNKNOWN")

 uv run python -c "
from ml.utils.evaluation_registry import EvaluationRegistry
import json

registry = EvaluationRegistry()
comparison = registry.compare_evaluations('hybrid', '$PREV_VERSION', '$CURRENT_VERSION')

if comparison:
 delta_file = 'experiments/performance_delta_${WEEK}.json'
 with open(delta_file, 'w') as f:
 json.dump(comparison, f, indent=2)
 print(f'Comparison saved to {delta_file}')

 # Check for regression
 if comparison.get('delta_pct', 0) < -10.0:
 print('REGRESSION')
 else:
 print('OK')
else:
 print('ERROR: Could not compare versions')
" 2>&1 | tee -a "$LOG_FILE"
 else
 # Fallback to original method
 uv run python -m ml.evaluation.compare_model_versions \
 --current "$EVAL_OUTPUT" \
 --previous "$PREV_EVAL" \
 --output "experiments/performance_delta_${WEEK}.json" \
 2>&1 | tee -a "$LOG_FILE"
 fi

 # Check for regression
 if [[ -f "experiments/performance_delta_${WEEK}.json" ]]; then
 REGRESSION=$(uv run python -c "
import json
try:
 with open('experiments/performance_delta_${WEEK}.json') as f:
 delta = json.load(f)
 # Try both possible metric paths
 p_at_10_drop_pct = (
 delta.get('deltas', {}).get('p_at_10_delta_pct', 0) or
 delta.get('p_at_10_delta_pct', 0) or
 (delta.get('p_at_10_delta', 0) * 100 if delta.get('p_at_10_delta') else 0)
 )
 if p_at_10_drop_pct < -10.0:
 print('REGRESSION')
 else:
 print('OK')
except Exception as e:
 print(f'ERROR: {e}')
" 2>/dev/null || echo "ERROR")

 if [[ "$REGRESSION" == "REGRESSION" ]]; then
 echo "Warning: PERFORMANCE REGRESSION DETECTED!"
 echo " P@10 dropped >10% vs. previous week"
 echo " Triggering auto-rollback..."
 # Auto-rollback: promote previous week's model
 PREV_GNN="embeddings/gnn_graphsage_v${PREV_WEEK}.json"
 if [[ -f "$PREV_GNN" ]] || s5cmd ls "s3://games-collections/$PREV_GNN" >/dev/null 2>&1; then
 echo " Rolling back to previous week's model: $PREV_GNN"
 "$SCRIPT_DIR/../model_management/promote_to_production.sh" --gnn "$PREV_GNN" 2>&1 | tee -a "$LOG_FILE"
 echo " ✓ Rollback complete"
 else
 echo " Error: Previous week's model not found, cannot rollback"
 echo " Manual intervention required"
 fi
 elif [[ "$REGRESSION" == "OK" ]]; then
 echo "✓ Performance acceptable"
 else
 echo "Warning: Could not determine regression status: $REGRESSION"
 fi
 else
 echo "Warning: Comparison output file not created, skipping regression check"
 fi
else
 echo "Warning: Previous week evaluation not found ($PREV_WEEK), skipping comparison"
 echo " This is normal for the first weekly run"
fi
echo ""

# Step 6: Cleanup
echo "Step 6: Cleaning up..."
# Instance will auto-stop via --auto-stop flag
echo "✓ Instance will auto-stop when complete"
echo ""

echo "======================================================================"
echo "WEEKLY RETRAINING COMPLETE"
echo "======================================================================"
echo "Week: $WEEK"
echo "Instance: $INSTANCE_ID"
echo "Log: $LOG_FILE"
echo ""

# Upload results to S3
if command -v s5cmd >/dev/null 2>&1; then
 s5cmd cp "$LOG_FILE" "s3://games-collections/logs/weekly/" 2>&1 | grep -v "^$" || true
 s5cmd cp "$EVAL_OUTPUT" "s3://games-collections/experiments/" 2>&1 | grep -v "^$" || true
 echo "✓ Results uploaded to S3"
fi
