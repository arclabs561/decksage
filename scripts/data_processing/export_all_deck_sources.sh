#!/usr/bin/env bash
# Export all deck sources with game metadata

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

echo "Exporting all deck sources..."
echo ""

# Run unified export pipeline
uv run python scripts/data_processing/unified_export_pipeline.py \
    --output-dir data/decks \
    --unified-file data/processed/decks_all_final.jsonl

echo ""
echo "✓ All deck sources exported"


