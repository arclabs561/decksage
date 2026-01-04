#!/usr/bin/env bash
# Generate missing deck files if raw data exists

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "=" | tr -d '\n'
printf '=%.0s' {1..69}
echo ""
echo "Generate Missing Deck Files"
echo "=" | tr -d '\n'
printf '=%.0s' {1..69}
echo ""
echo ""

# Check if raw data exists
RAW_DATA_DIR="src/backend/data-full/games"
if [ ! -d "$RAW_DATA_DIR" ]; then
    echo "⚠ Raw data directory not found: $RAW_DATA_DIR"
    echo ""
    echo "Raw data is stored on S3. To generate deck files:"
    echo "  1. Sync data from S3: s5cmd sync s3://games-collections/games/ $RAW_DATA_DIR/"
    echo "  2. Run this script again"
    echo ""
    exit 1
fi

echo "✓ Raw data directory exists"
echo ""

# Check what's missing
MISSING_FILES=()
if [ ! -f "data/processed/decks_all_final.jsonl" ]; then
    MISSING_FILES+=("decks_all_final.jsonl")
fi
if [ ! -f "data/processed/decks_all_enhanced.jsonl" ]; then
    MISSING_FILES+=("decks_all_enhanced.jsonl")
fi
if [ ! -f "data/processed/decks_all_unified.jsonl" ]; then
    MISSING_FILES+=("decks_all_unified.jsonl")
fi

if [ ${#MISSING_FILES[@]} -eq 0 ]; then
    echo "✓ All deck files exist"
    exit 0
fi

echo "Missing files:"
for file in "${MISSING_FILES[@]}"; do
    echo "  - $file"
done
echo ""

# Generate files
echo "Generating missing files..."
echo ""

if uv run scripts/data_processing/unified_export_pipeline.py; then
    echo ""
    echo "✓ Deck files generated successfully"
    echo ""
    echo "Generated files:"
    for file in "${MISSING_FILES[@]}"; do
        if [ -f "data/processed/$file" ]; then
            SIZE=$(du -h "data/processed/$file" | cut -f1)
            LINES=$(wc -l < "data/processed/$file" | tr -d ' ')
            echo "  ✓ $file ($SIZE, $LINES lines)"
        else
            echo "  ✗ $file (generation failed)"
        fi
    done
else
    echo ""
    echo "✗ Generation failed"
    echo ""
    echo "Check errors above. Common issues:"
    echo "  - Go export tool not built (run: cd src/backend && go build ./cmd/export-hetero)"
    echo "  - Missing dependencies"
    echo "  - Insufficient disk space"
    exit 1
fi

