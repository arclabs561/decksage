#!/usr/bin/env bash
# Smart evaluation wrapper - auto-detects if runctl needed
# Usage: ./scripts/evaluation/run_eval_smart.sh [args...]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Parse arguments to find test set and count pairs
TEST_SET=""
GAME="magic"
MIN_PAIRS=1000
USE_RUNCTL=false

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
 --use-runctl)
 USE_RUNCTL=true
 shift
 ;;
 *)
 # Pass through other args
 shift
 ;;
 esac
done

# Count pairs if test set provided
if [ -n "$TEST_SET" ] && [ -f "$TEST_SET" ]; then
 PAIR_COUNT=$(python3 << 'PYEOF'
import json
import sys
from pathlib import Path

test_path = Path(sys.argv[1])
try:
 with open(test_path) as f:
 data = json.load(f)
 if isinstance(data, dict) and 'queries' in data:
 count = 0
 for query, labels in data['queries'].items():
 if isinstance(labels, dict):
 count += len(labels.get('highly_relevant', []))
 count += len(labels.get('relevant', []))
 print(count)
 elif isinstance(data, list):
 print(len(data))
 else:
 print(0)
except Exception:
 print(0)
PYEOF
"$TEST_SET" 2>/dev/null || echo "0")
 
 if [ "$PAIR_COUNT" -gt "$MIN_PAIRS" ] && [ "$USE_RUNCTL" != "true" ]; then
 echo "═══════════════════════════════════════════════════════════════════════"
 echo "Warning: LARGE EVALUATION DETECTED: $PAIR_COUNT pairs"
 echo "═══════════════════════════════════════════════════════════════════════"
 echo ""
 echo "Recommendation: Use runctl on AWS for faster execution"
 echo ""
 echo "Options:"
 echo " 1. Run on AWS: ./scripts/evaluation/validate_e2e_runctl.sh $GAME"
 echo " 2. Continue locally (slow): Press Enter"
 echo " 3. Cancel: Ctrl+C"
 echo ""
 read -t 10 -p "Choice [Enter=local, Ctrl+C=cancel]: " choice || choice="local"
 
 if [ "$choice" != "local" ]; then
 echo "Running on AWS..."
 exec "$SCRIPT_DIR/validate_e2e_runctl.sh" "$GAME"
 exit 0
 fi
 echo "Continuing with local evaluation (will be slow)..."
 fi
fi

# Run locally
exec uv run python src/ml/scripts/evaluate_downstream_complete.py "$@"

