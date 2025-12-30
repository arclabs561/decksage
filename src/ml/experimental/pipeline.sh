#!/bin/bash
# Complete ML Pipeline: Data → Embeddings → Evaluation → Comparison
set -e

# Configurable parameters
DATA_DIR="${DATA_DIR:-../backend/data-full/games/magic}"
OUTPUT_DIR="${OUTPUT_DIR:-../backend}"
DIMS="${DIMS:-64 128 256}"
EXPERIMENT_DIR="${EXPERIMENT_DIR:-../../assets/experiments}"

echo "════════════════════════════════════════════════════════════"
echo "  DeckSage ML Pipeline"
echo "════════════════════════════════════════════════════════════"
echo ""

# Step 1: Export graph
echo "Step 1/5: Exporting deck co-occurrence graph..."
cd ../backend
go run ./cmd/export-decks-only "$DATA_DIR" pairs_decks_new.csv
echo "✓ Graph exported: pairs_decks_new.csv"
echo ""

# Step 2: Analyze data quality
echo "Step 2/5: Analyzing data quality..."
go run ./cmd/analyze-decks "$DATA_DIR" > data_analysis.txt
cat data_analysis.txt | head -50
echo "✓ Analysis saved: data_analysis.txt"
echo ""

# Step 3: Train multiple models
echo "Step 3/5: Training embedding models..."
cd ../ml
source .venv/bin/activate

for dim in $DIMS; do
    echo "  Training ${dim}d model..."
    python card_similarity_pecan.py \
        --input ../backend/pairs_decks_new.csv \
        --dim "$dim" \
        --output "magic_${dim}d" \
        --workers 8
    echo "  ✓ Saved: magic_${dim}d_pecanpy.wv"
done
echo ""

# Step 4: Run evaluation
echo "Step 4/5: Evaluating against baselines..."
python evaluate.py \
    --pairs ../backend/pairs_decks_new.csv \
    --embeddings ../backend/magic_128d_pecanpy.wv \
    --log "$EXPERIMENT_DIR/experiments.jsonl"
echo ""

# Step 5: Compare all models
echo "Step 5/5: Comparing models..."
# Would need test set first, so skip for now
# python compare_models.py --test-set test_set.json --models ../backend/magic_*_pecanpy.wv

echo "════════════════════════════════════════════════════════════"
echo "  Pipeline Complete"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "Generated reports:"
ls -lh "$EXPERIMENT_DIR"/*.html 2>/dev/null || echo "  (none yet - need test set)"
echo ""
echo "Next steps:"
echo "  1. Review evaluation_report.html"
echo "  2. Create annotated test set if results look good"
echo "  3. Run full model comparison"
echo "  4. Deploy best model"


