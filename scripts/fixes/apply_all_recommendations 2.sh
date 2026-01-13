#!/usr/bin/env bash
# Apply all recommendations from validation

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

echo "=" | tr -d '\n'
printf '=%.0s' {1..69}
echo ""
echo "Applying All Recommendations"
echo "=" | tr -d '\n'
printf '=%.0s' {1..69}
echo ""
echo ""

# Step 1: Improve canonical test set
echo "Step 1: Improving canonical test set..."
echo "─────────────────────────────────────────────────────────────────────"
if python3 scripts/fixes/improve_canonical_test_set.py --backup; then
    echo "✓ Canonical test set improved"
else
    echo "⚠ Failed to improve canonical test set"
fi
echo ""

# Step 2: Check if we can generate missing deck files
echo "Step 2: Checking for missing deck files..."
echo "─────────────────────────────────────────────────────────────────────"
MISSING=0
for file in "decks_all_final.jsonl" "decks_all_enhanced.jsonl" "decks_all_unified.jsonl"; do
    if [ ! -f "data/processed/$file" ]; then
        echo "  ✗ Missing: $file"
        MISSING=$((MISSING + 1))
    else
        echo "  ✓ Exists: $file"
    fi
done

if [ $MISSING -gt 0 ]; then
    echo ""
    echo "  Missing $MISSING deck file(s)."
    if [ -d "src/backend/data-full/games" ]; then
        echo "  Attempting to generate..."
        if uv run scripts/data_processing/unified_export_pipeline.py 2>&1 | tail -20; then
            echo "  ✓ Deck files generated"
        else
            echo "  ⚠ Generation failed (may need raw data from S3)"
        fi
    else
        echo "  ⚠ Raw data not found. To generate:"
        echo "    1. Sync from S3: s5cmd sync s3://games-collections/games/ src/backend/data-full/games/"
        echo "    2. Run: uv run scripts/data_processing/unified_export_pipeline.py"
    fi
else
    echo "  ✓ All deck files exist"
fi
echo ""

# Step 3: Re-run evaluations with unified test set
echo "Step 3: Re-running evaluations with unified test set..."
echo "─────────────────────────────────────────────────────────────────────"
if command -v uv >/dev/null 2>&1; then
    if uv run scripts/fixes/rerun_evaluations_unified.py 2>&1; then
        echo "✓ Evaluations re-run with unified test set"
    else
        echo "⚠ Evaluation re-run had issues (may need gensim)"
    fi
else
    echo "⚠ uv not found, skipping evaluation re-run"
    echo "  Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo "  Then run: uv run scripts/fixes/rerun_evaluations_unified.py"
fi
echo ""

# Step 4: Validate improvements
echo "Step 4: Validating improvements..."
echo "─────────────────────────────────────────────────────────────────────"
if [ -f "experiments/test_set_canonical_magic_improved.json" ]; then
    echo "  Validating improved canonical test set..."
    python3 scripts/validation/validate_test_set_quality.py \
        --test-set experiments/test_set_canonical_magic_improved.json 2>&1 | grep -E "(Quality score|Issues|✓)" || true
fi

if [ -f "experiments/evaluation_results_unified.json" ]; then
    echo ""
    echo "  Validating new evaluation results..."
    python3 scripts/validation/validate_evaluation_results.py \
        --results experiments/evaluation_results_unified.json 2>&1 | head -20 || true
fi
echo ""

echo "=" | tr -d '\n'
printf '=%.0s' {1..69}
echo ""
echo "Recommendations Applied"
echo ""
echo "Summary:"
echo "  ✓ Canonical test set improved (if successful)"
echo "  ✓ Deck files checked/generated (if possible)"
echo "  ✓ Evaluations re-run with unified test set (if successful)"
echo ""
echo "Next steps:"
echo "  1. Review improved test set: experiments/test_set_canonical_magic_improved.json"
echo "  2. Review new evaluations: experiments/evaluation_results_unified.json"
echo "  3. Run validation: python3 scripts/validation/validate_all.py"
echo ""
