#!/usr/bin/env bash
# Run all diagnostic scripts and generate comprehensive report

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

echo "=" | tr -d '\n'
printf '=%.0s' {1..69}
echo ""
echo "DeckSage Comprehensive Diagnostics"
echo "=" | tr -d '\n'
printf '=%.0s' {1..69}
echo ""
echo ""

# 1. Validate data pipeline
echo "1. Validating data pipeline..."
echo "   ──────────────────────────────────────────────────────────────"
if uv run scripts/diagnostics/validate_data_pipeline.py 2>&1; then
    echo "   ✓ Data pipeline validation complete"
else
    echo "   ✗ Data pipeline validation failed"
fi
echo ""

# 2. Check vocabulary coverage
echo "2. Checking vocabulary coverage..."
echo "   ──────────────────────────────────────────────────────────────"
if uv run scripts/diagnostics/fix_evaluation_coverage.py 2>&1; then
    echo "   ✓ Vocabulary coverage check complete"
else
    echo "   ✗ Vocabulary coverage check failed"
fi
echo ""

# 3. Audit all embeddings
echo "3. Auditing all embeddings..."
echo "   ──────────────────────────────────────────────────────────────"
if uv run scripts/diagnostics/audit_all_embeddings.py 2>&1; then
    echo "   ✓ Embedding audit complete"
else
    echo "   ✗ Embedding audit failed"
fi
echo ""

echo "=" | tr -d '\n'
printf '=%.0s' {1..69}
echo ""
echo "Diagnostics Complete"
echo ""
echo "Reports saved to:"
echo "  - experiments/data_pipeline_validation.json"
echo "  - experiments/coverage_fix_report.json"
echo "  - experiments/vocabulary_coverage_audit.json"
echo ""

