#!/usr/bin/env bash
# Auto-detect if evaluation is big and use runctl if needed
# Usage: ./scripts/evaluation/auto_runctl_if_big.sh [args...]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Parse arguments to find test set
TEST_SET=""
GAME="magic"
MIN_PAIRS=1000

while [[ $# -gt 0 ]]; do
 case $1 in
 --test-substitutions)
 TEST_SET="$2"
 shift 2
 ;;
 --game)
 GAME="$2"
 shift 2
 ;;
 --min-pairs)
 MIN_PAIRS="$2"
 shift 2
 ;;
 *)
 shift
 ;;
 esac
done

# Count pairs in test set
if [ -n "$TEST_SET" ] && [ -f "$TEST_SET" ]; then
 PAIR_COUNT=$(python3 -c "
import json
from pathlib import Path

test_path = Path('$TEST_SET')
with open(test_path) as f:
 data = json.load(f)
 if isinstance(data, dict) and 'queries' in data:
 count = 0
 for query, labels in data['queries'].items():
 count += len(labels.get('highly_relevant', []))
 count += len(labels.get('relevant', []))
 print(count)
 elif isinstance(data, list):
 print(len(data))
 else:
 print(0)
" 2>/dev/null || echo "0")

 if [ "$PAIR_COUNT" -gt "$MIN_PAIRS" ]; then
 echo "═══════════════════════════════════════════════════════════════════════"
 echo "Warning: LARGE EVALUATION DETECTED: $PAIR_COUNT pairs"
 echo "═══════════════════════════════════════════════════════════════════════"
 echo ""
 echo "Recommendation: Use runctl on AWS for faster execution"
 echo ""
 echo "Run:"
 echo " ./scripts/evaluation/validate_e2e_runctl.sh $GAME"
 echo ""
 echo "Or continue locally (will be slow):"
 echo " Press Ctrl+C to cancel, or wait 5 seconds to continue..."
 sleep 5
 echo "Continuing with local evaluation..."
 fi
fi

# Continue with original command
exec uv run python src/ml/scripts/evaluate_downstream_complete.py "$@"
