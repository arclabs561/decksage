#!/usr/bin/env bash
# Update evaluation scripts to use unified test sets

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# Update default test set paths in evaluation scripts
echo "Updating evaluation scripts to use unified test sets..."

# Find evaluation scripts
EVAL_SCRIPTS=(
    "src/ml/scripts/evaluate_all_embeddings.py"
    "scripts/runctl_evaluation.sh"
)

for script in "${EVAL_SCRIPTS[@]}"; do
    if [ -f "$script" ]; then
        echo "Checking $script..."
        # Use sed to update test set paths
        if grep -q "test_set_canonical_magic.json" "$script" 2>/dev/null; then
            sed -i.bak 's|test_set_canonical_magic\.json|test_set_unified_magic.json|g' "$script"
            echo "  Updated $script"
        fi
        if grep -q "test_set_expanded_magic.json" "$script" 2>/dev/null; then
            sed -i.bak 's|test_set_expanded_magic\.json|test_set_unified_magic.json|g' "$script"
            echo "  Updated $script"
        fi
    fi
done

# Clean up backup files
find . -name "*.bak" -type f -delete 2>/dev/null || true

echo "Done updating evaluation scripts"
