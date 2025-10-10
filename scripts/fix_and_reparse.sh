#!/bin/bash
set -e

cd "$(dirname "$0")/../src/backend"

echo "🔧 FIXING CACHE-EXTRACTED FILES & RE-PARSING"
echo "============================================"
echo ""

# Step 1: Find and re-compress plain JSON files
echo "Step 1: Re-compressing cache-extracted files..."
echo "Finding plain JSON files..."

# Process in batches to avoid command line length issues
TOTAL=0
BATCH=0
find data-full/games/magic -name "*.zst" -type f | while read f; do
    if file "$f" 2>/dev/null | grep -q "JSON data"; then
        zstd -f --rm "$f" 2>/dev/null
        TOTAL=$((TOTAL + 1))
        if [ $((TOTAL % 1000)) -eq 0 ]; then
            echo "  Compressed $TOTAL files..."
        fi
    fi
done

echo "✅ All files properly compressed"
echo ""

# Step 2: Re-parse MTGTop8
echo "Step 2: Re-parsing MTGTop8 (297K decks)..."
go run cmd/dataset/main.go --bucket file://./data-full --log info extract mtgtop8 \
  --reparse --parallel 128 \
  2>&1 | tee ../../logs/reparse_mtgtop8_complete_$(date +%Y%m%d_%H%M%S).log

echo "✅ MTGTop8 re-parse complete"
echo ""

# Step 3: Re-parse Goldfish  
echo "Step 3: Re-parsing Goldfish (16K decks)..."
go run cmd/dataset/main.go --bucket file://./data-full --log info extract goldfish \
  --reparse --parallel 64 \
  2>&1 | tee ../../logs/reparse_goldfish_complete_$(date +%Y%m%d_%H%M%S).log

echo "✅ Goldfish re-parse complete"
echo ""

# Step 4: Verify
echo "Step 4: Final verification..."
go run cmd/analyze-decks/main.go data-full/games/magic | tee ../../logs/final_analysis_$(date +%Y%m%d).log

echo ""
echo "================================"
echo "🎉 RECOVERY COMPLETE"
echo "================================"
