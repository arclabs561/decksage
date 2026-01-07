#!/usr/bin/env bash
# Full agentic validation with LLM analysis
# Comprehensive validation using agentic tools with LLM reasoning

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"

echo "=================================================="
echo "Full Agentic Validation"
echo "=================================================="
echo ""

# Run comprehensive agentic analysis
uv run python -m src.ml.qa.validate_agentic --comprehensive \
    --output experiments/agentic_validation_$(date +%Y%m%d_%H%M%S).json

echo ""
echo "=================================================="
echo "Full Validation Complete"
echo "=================================================="
echo "Results saved to: experiments/agentic_validation_*.json"

