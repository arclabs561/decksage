#!/usr/bin/env bash
# Comprehensive fix script - runs all fixes in order

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "=" | tr -d '\n'
printf '=%.0s' {1..69}
echo ""
echo "Comprehensive Repository Fix"
echo "=" | tr -d '\n'
printf '=%.0s' {1..69}
echo ""
echo ""

# Step 1: Validate data pipeline
echo "Step 1: Validating data pipeline..."
echo "─────────────────────────────────────────────────────────────────────"
if python3 scripts/diagnostics/validate_data_pipeline.py; then
    echo "✓ Data pipeline validation complete"
else
    echo "⚠ Some data files missing (see above)"
fi
echo ""

# Step 2: Check if we can generate missing files
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
    echo "  Missing $MISSING deck file(s). To generate:"
    echo "    ./scripts/generate_missing_deck_files.sh"
    echo ""
    echo "  Or manually:"
    echo "    uv run scripts/data_processing/unified_export_pipeline.py"
else
    echo "  ✓ All deck files exist"
fi
echo ""

# Step 3: Check vocabulary coverage
echo "Step 3: Checking vocabulary coverage..."
echo "─────────────────────────────────────────────────────────────────────"
if command -v uv >/dev/null 2>&1; then
    if uv run scripts/diagnostics/fix_evaluation_coverage.py 2>&1 | head -20; then
        echo "✓ Vocabulary coverage check complete"
    else
        echo "⚠ Vocabulary coverage check had issues (may need gensim)"
    fi
else
    echo "⚠ uv not found, skipping vocabulary check"
    echo "  Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
fi
echo ""

# Step 4: Summary
echo "=" | tr -d '\n'
printf '=%.0s' {1..69}
echo ""
echo "Fix Summary"
echo "=" | tr -d '\n'
printf '=%.0s' {1..69}
echo ""
echo ""
echo "Next steps:"
echo ""
echo "1. Generate missing deck files (if needed):"
echo "   ./scripts/generate_missing_deck_files.sh"
echo ""
echo "2. Check vocabulary coverage:"
echo "   uv run scripts/diagnostics/audit_all_embeddings.py"
echo ""
echo "3. Run reliable evaluation:"
echo "   uv run scripts/evaluation/ensure_full_evaluation.py"
echo ""
echo "4. View comprehensive report:"
echo "   python3 scripts/fix_repository_issues.py"
echo ""

