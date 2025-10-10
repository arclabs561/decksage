#!/bin/bash
# Comprehensive cache recovery and re-parsing
set -e

cd "$(dirname "$0")/../src/backend"

echo "🚀 COMPREHENSIVE CACHE RECOVERY"
echo "================================"
echo ""
echo "This will:"
echo "  1. Backup cache and data"
echo "  2. Extract 280K HTTP responses from cache"
echo "  3. Re-parse 337K MTGTop8 decks with metadata extraction"
echo "  4. Re-parse Goldfish decks with fixed sideboard code"
echo "  5. Extract pre-parsed data as fallback"
echo ""
echo "Estimated time: 3-5 hours"
echo "Network cost: $0 (uses cached HTML)"
echo ""
read -p "Continue? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted"
    exit 1
fi

# Phase 1: Backup
echo ""
echo "=== PHASE 1: BACKUP ==="
mkdir -p ../../backups ../../logs
tar -czf ../../backups/badger-cache-$(date +%Y%m%d_%H%M%S).tar.gz cache/
tar -czf ../../backups/data-full-$(date +%Y%m%d_%H%M%S).tar.gz data-full/
echo "✅ Backups created"

# Phase 2: Extract HTTP
echo ""
echo "=== PHASE 2: EXTRACT HTTP FROM CACHE ==="
cd tools/cache-extract
echo "y" | go run main.go --only-scraper --workers 16 | tee ../../../logs/extract_http_$(date +%Y%m%d).log
cd ../..
echo "✅ HTTP extraction complete"

# Phase 3: Re-parse MTGTop8
echo ""
echo "=== PHASE 3: RE-PARSE MTGTOP8 WITH METADATA ==="
go run cmd/dataset/main.go extract mtgtop8 \
  --reparse --parallel 128 \
  2>&1 | tee ../../logs/reparse_mtgtop8_$(date +%Y%m%d).log
echo "✅ MTGTop8 re-parsing complete"

# Phase 4: Re-parse Goldfish
echo ""
echo "=== PHASE 4: RE-PARSE GOLDFISH (FIX SIDEBOARDS) ==="
go run cmd/dataset/main.go extract goldfish \
  --reparse --parallel 64 \
  2>&1 | tee ../../logs/reparse_goldfish_$(date +%Y%m%d).log
echo "✅ Goldfish re-parsing complete"

# Phase 5: Extract game data
echo ""
echo "=== PHASE 5: EXTRACT GAME DATA (FALLBACK) ==="
cd tools/cache-extract
echo "y" | go run main.go --only-games --workers 16 | tee ../../../logs/extract_games_$(date +%Y%m%d).log
cd ../..
echo "✅ Game data extraction complete"

# Phase 6: Verify
echo ""
echo "=== PHASE 6: VERIFICATION ==="
go run cmd/analyze-decks/main.go data-full/games/magic | tee ../../logs/analysis_final_$(date +%Y%m%d).log

# Phase 7: Export
echo ""
echo "=== PHASE 7: EXPORT WITH METADATA ==="
go run cmd/export-hetero/main.go \
  data-full/games/magic \
  ../../data/processed/decks_complete_$(date +%Y%m%d).jsonl

DECK_COUNT=$(wc -l < ../../data/processed/decks_complete_$(date +%Y%m%d).jsonl)

echo ""
echo "================================"
echo "🎉 RECOVERY COMPLETE"
echo "================================"
echo ""
echo "Results:"
echo "  Total decks exported: $DECK_COUNT"
echo "  Logs saved to: logs/"
echo "  Data saved to: data/processed/"
echo ""
echo "Next: Test in Python with src/ml/test_source_filtering.py"
