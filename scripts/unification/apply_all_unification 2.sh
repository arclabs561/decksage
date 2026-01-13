#!/usr/bin/env bash
# Apply all unification fixes

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

echo "=" | tr -d '\n'
printf '=%.0s' {1..69}
echo ""
echo "Repository Unification"
echo "=" | tr -d '\n'
printf '=%.0s' {1..69}
echo ""
echo ""

# Step 1: Fix syntax error
echo "Step 1: Fixing syntax error..."
echo "─────────────────────────────────────────────────────────────────────"
if python3 -m py_compile src/ml/scripts/train_hybrid_full.py 2>&1; then
    echo "✓ Syntax error fixed"
else
    echo "⚠ Syntax error still present (may need manual fix)"
fi
echo ""

# Step 2: Fix unified test set integrity
echo "Step 2: Fixing unified test set integrity..."
echo "─────────────────────────────────────────────────────────────────────"
if [ -f "experiments/test_set_unified_magic.json" ]; then
    if python3 scripts/deep_analysis/fix_data_integrity_issues.py \
        --test-set experiments/test_set_unified_magic.json \
        --output experiments/test_set_unified_magic_fixed.json 2>&1 | tail -10; then
        echo "✓ Unified test set integrity fixed"
    else
        echo "⚠ Unified test set fix had issues"
    fi
else
    echo "⚠ Unified test set not found"
fi
echo ""

# Step 3: Unify test set formats
echo "Step 3: Unifying test set formats..."
echo "─────────────────────────────────────────────────────────────────────"
for test_set in "experiments/test_set_canonical_magic_improved_fixed.json" \
                "experiments/test_set_unified_magic_fixed.json"; do
    if [ -f "$test_set" ]; then
        echo "  Unifying $(basename $test_set)..."
        python3 scripts/unification/unify_test_set_formats.py \
            --test-set "$test_set" 2>&1 | grep -E "(✓|Error)" || true
    fi
done
echo ""

# Step 4: Analyze error handling
echo "Step 4: Analyzing error handling..."
echo "─────────────────────────────────────────────────────────────────────"
python3 scripts/unification/unify_error_handling.py \
    --path src/ml/scripts \
    --output experiments/error_handling_analysis.json 2>&1 | tail -10
echo ""

echo "=" | tr -d '\n'
printf '=%.0s' {1..69}
echo ""
echo "Unification Complete"
echo ""
echo "Next steps:"
echo "  1. Review error handling analysis: experiments/error_handling_analysis.json"
echo "  2. Run tests: pytest tests/"
echo "  3. Validate: python3 scripts/validation/validate_all.py"
echo ""
