#!/usr/bin/env bash
# Quick agentic validation check
# Fast validation using agentic tools (no LLM required for basic checks)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"

echo "=================================================="
echo "Quick Agentic Validation"
echo "=================================================="
echo ""

# Run agentic pipeline validation (uses tools directly, no LLM)
uv run python -m src.ml.qa.validate_agentic --pipeline

echo ""
echo "=================================================="
echo "Quick Validation Complete"
echo "=================================================="

