#!/usr/bin/env bash
set -euo pipefail
#
# Epoch sweep: find optimal training duration per game.
# Trains at multiple epoch counts and evaluates each, producing a TSV summary.
#
# Usage:
#   ./scripts/training/sweep_epochs.sh              # All games
#   GAMES="pokemon" ./scripts/training/sweep_epochs.sh  # Single game
#
# Output: data/logs/epoch_sweep_results.tsv

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

GAMES="${GAMES:-pokemon yugioh magic}"
EPOCHS_LIST="${EPOCHS_LIST:-5 10 20 40 80 160}"
LR="${LR:-0.003}"
WALKS="${WALKS:-30}"
BATCH="${BATCH:-256}"

OUT="data/logs/epoch_sweep_results.tsv"
mkdir -p data/logs

# Only write header if file doesn't exist (avoids overwriting previous game results)
if [ ! -f "$OUT" ]; then
    echo -e "game\tepochs\tnum_cards\tsub_ndcg\tsyn_ndcg\tmeta_ndcg\tctx_recall\tcomp_recall\tduration_s\tfinal_loss" > "$OUT"
fi

for game in $GAMES; do
    echo ""
    echo "========================================"
    echo "  Sweep: $game"
    echo "========================================"

    for epochs in $EPOCHS_LIST; do
        echo ""
        echo "--- $game @ $epochs epochs ---"

        # Clear checkpoint to train fresh
        rm -f data/checkpoints/metapath2vec_*n_128d.pt 2>/dev/null

        suffix="sweep_${epochs}ep"
        uv run scripts/training/train_metapath2vec.py \
            --game "$game" \
            --epochs "$epochs" \
            --walks-per-node "$WALKS" \
            --lr "$LR" \
            --batch-size "$BATCH" \
            --output-suffix "$suffix" 2>&1 | tail -10

        # Extract metrics from run JSON
        json_file="data/logs/${game}_metapath2vec_${suffix}_run.json"
        if [ -f "$json_file" ]; then
            python3 -c "
import json
with open('$json_file') as f:
    r = json.load(f)
ev = r.get('eval') or {}
ds = r.get('downstream') or {}
tr = r.get('training') or {}
row = '\t'.join([
    '$game', '$epochs',
    str(r.get('data', {}).get('num_cards', '')),
    str(ev.get('sub_ndcg', '')),
    str(ev.get('syn_ndcg', '')),
    str(ev.get('meta_ndcg', '')),
    str(ds.get('contextual_recall_at_20', '')),
    str(ds.get('completion_recall_at_30', '')),
    str(tr.get('duration_s', '')),
    str(tr.get('final_loss', '')),
])
print(row)
" >> "$OUT"
            echo "  -> recorded in $OUT"
        else
            echo "  -> MISSING run JSON"
        fi
    done
done

echo ""
echo "========================================"
echo "  Results: $OUT"
echo "========================================"
column -t -s $'\t' "$OUT"
