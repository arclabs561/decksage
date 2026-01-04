#!/usr/bin/env bash
# Run all deep analysis scripts

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

echo "=" | tr -d '\n'
printf '=%.0s' {1..69}
echo ""
echo "Deep Analysis - Comprehensive Scrutiny"
echo "=" | tr -d '\n'
printf '=%.0s' {1..69}
echo ""
echo ""

# 1. Data integrity
echo "1. Checking data integrity..."
echo "─────────────────────────────────────────────────────────────────────"
python3 scripts/deep_analysis/check_data_integrity.py \
  --output experiments/deep_analysis_integrity.json 2>&1 | tail -20
echo ""

# 2. Code quality
echo "2. Analyzing code quality..."
echo "─────────────────────────────────────────────────────────────────────"
python3 scripts/deep_analysis/analyze_code_quality.py \
  --path src/ml \
  --output experiments/deep_analysis_code_quality.json 2>&1 | tail -20
echo ""

# 3. Inconsistencies
echo "3. Finding inconsistencies..."
echo "─────────────────────────────────────────────────────────────────────"
python3 scripts/deep_analysis/find_inconsistencies.py \
  --output experiments/deep_analysis_inconsistencies.json 2>&1 | tail -20
echo ""

echo "=" | tr -d '\n'
printf '=%.0s' {1..69}
echo ""
echo "Deep Analysis Complete"
echo ""
echo "Reports saved to:"
echo "  - experiments/deep_analysis_integrity.json"
echo "  - experiments/deep_analysis_code_quality.json"
echo "  - experiments/deep_analysis_inconsistencies.json"
echo ""

