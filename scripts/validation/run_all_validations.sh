#!/usr/bin/env bash
# Run all validation scripts

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

echo "=" | tr -d '\n'
printf '=%.0s' {1..69}
echo ""
echo "Comprehensive Repository Validation"
echo "=" | tr -d '\n'
printf '=%.0s' {1..69}
echo ""
echo ""

# 1. Comprehensive validation
echo "1. Running comprehensive validation..."
echo "─────────────────────────────────────────────────────────────────────"
if python3 scripts/validation/validate_all.py; then
    echo "✓ Comprehensive validation complete"
else
    echo "⚠ Some validation checks failed"
fi
echo ""

# 2. Test set quality
echo "2. Validating test set quality..."
echo "─────────────────────────────────────────────────────────────────────"
for test_set in "experiments/test_set_canonical_magic.json" "experiments/test_set_unified_magic.json"; do
    if [ -f "$test_set" ]; then
        echo "  Validating $(basename $test_set)..."
        python3 scripts/validation/validate_test_set_quality.py --test-set "$test_set" 2>&1 | grep -E "(Quality score|Issues|✓)" || true
    fi
done
echo ""

# 3. Embedding quality
echo "3. Validating embedding quality..."
echo "─────────────────────────────────────────────────────────────────────"
if command -v uv >/dev/null 2>&1; then
    if uv run scripts/validation/validate_embedding_quality.py 2>&1 | head -30; then
        echo "✓ Embedding quality validation complete"
    else
        echo "⚠ Embedding quality validation had issues"
    fi
else
    echo "⚠ uv not found, skipping embedding validation"
fi
echo ""

# 4. Data pipeline
echo "4. Validating data pipeline..."
echo "─────────────────────────────────────────────────────────────────────"
if python3 scripts/diagnostics/validate_data_pipeline.py 2>&1 | tail -10; then
    echo "✓ Data pipeline validation complete"
else
    echo "⚠ Some data files missing"
fi
echo ""

echo "=" | tr -d '\n'
printf '=%.0s' {1..69}
echo ""
echo "Validation Complete"
echo ""
echo "Reports saved to:"
echo "  - experiments/validation_report.json"
echo "  - experiments/test_set_quality_report.json (if generated)"
echo "  - experiments/embedding_quality_report.json (if generated)"
echo ""

