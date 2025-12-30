#!/bin/bash
# Prepare and start training after hyperparameter search completes
# This script will be called once hyperparameter results are available

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
RUNCTL_BIN="${RUNCTL_BIN:-$PROJECT_ROOT/../runctl/target/release/runctl}"

HYPERPARAM_RESULTS="${HYPERPARAM_RESULTS:-s3://games-collections/experiments/hyperparameter_results.json}"

echo "🔍 Checking for hyperparameter results..."
echo "   Looking for: $HYPERPARAM_RESULTS"

# Check if results exist in S3
if aws s3 ls "$HYPERPARAM_RESULTS" > /dev/null 2>&1; then
    echo "✅ Hyperparameter results found!"
    
    # Download results
    echo "📥 Downloading results..."
    aws s3 cp "$HYPERPARAM_RESULTS" experiments/hyperparameter_results.json
    
    # Extract best hyperparameters
    echo "📊 Extracting best hyperparameters..."
    python3 << 'EOF'
import json
with open('experiments/hyperparameter_results.json') as f:
    results = json.load(f)
    
# Find best config (highest P@10)
best = max(results.get('configs', []), key=lambda x: x.get('p_at_10', 0))
print(f"Best P@10: {best.get('p_at_10', 0):.4f}")
print(f"Best config:")
for key, value in best.items():
    if key != 'p_at_10' and key != 'mrr':
        print(f"  {key}: {value}")

# Save best config
with open('experiments/best_hyperparameters.json', 'w') as f:
    json.dump(best, f, indent=2)
EOF
    
    echo "✅ Best hyperparameters saved to experiments/best_hyperparameters.json"
    echo ""
    echo "🚀 Ready to train with best hyperparameters!"
    echo "   Run: just train-aws <instance-id>"
    echo "   Or: just train-local"
    
else
    echo "⏳ Hyperparameter results not yet available"
    echo "   Check: aws s3 ls $HYPERPARAM_RESULTS"
    echo "   Or monitor: tail -f /tmp/hyperparam_search.log"
fi

