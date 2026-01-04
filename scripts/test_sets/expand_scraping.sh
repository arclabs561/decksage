#!/bin/bash
set -euo pipefail
#
# Expand scraping to 20K+ decks
#
# Usage: ./scripts/expand_scraping.sh [quick|full]
#

set -e

MODE=${1:-quick}
BACKEND_DIR="src/backend"

cd "$(dirname "$0")/.."

echo "=================================================="
echo "DeckSage Scraping Expansion"
echo "=================================================="
echo ""
echo "Mode: $MODE"
echo "Backend: $BACKEND_DIR"
echo ""

# Check current state
echo "Current state:"
CURRENT_COUNT=$(find $BACKEND_DIR/data-full/games/magic/mtgtop8/collections -name "*.zst" 2>/dev/null | wc -l | tr -d ' ')
echo " MTGTop8 decks: $CURRENT_COUNT"
echo ""

if [ "$MODE" = "quick" ]; then
 echo "QUICK MODE: Scraping 100 more pages (~2K decks)"
 echo ""
 
 # MTGTop8 - expand by 100 pages
 echo "[1/3] MTGTop8 expansion..."
 cd $BACKEND_DIR
 go run cmd/dataset/main.go \
 --bucket file://./data-full \
 extract mtgtop8 \
 --pages 100 \
 --parallel 32 \
 2>&1 | tee -a ../../logs/mtgtop8_expand_quick.log
 
 # MTGGoldfish - test extraction
 echo ""
 echo "[2/3] MTGGoldfish test (100 decks)..."
 go run cmd/dataset/main.go \
 --bucket file://./data-full \
 extract goldfish \
 --limit 100 \
 --parallel 16 \
 2>&1 | tee -a ../../logs/goldfish_expand_quick.log
 
 # Pokemon cards - complete the scraping
 echo ""
 echo "[3/3] Pokemon cards completion..."
 go run cmd/dataset/main.go \
 --bucket file://./data-full \
 extract pokemontcg \
 --parallel 8 \
 2>&1 | tee -a ../../logs/pokemon_cards_complete.log
 
 cd ../..
 
elif [ "$MODE" = "full" ]; then
 echo "FULL MODE: Scraping 500 pages (~10K decks)"
 echo ""
 echo "Warning: This will take 1-2 hours with rate limiting"
 echo "Press Ctrl-C to cancel, or wait 5 seconds to continue..."
 sleep 5
 
 mkdir -p ../../logs
 
 # MTGTop8 - deep scrape
 echo "[1/3] MTGTop8 deep scrape (500 pages)..."
 cd $BACKEND_DIR
 go run cmd/dataset/main.go \
 --bucket file://./data-full \
 extract mtgtop8 \
 --pages 500 \
 --parallel 64 \
 2>&1 | tee ../../logs/mtgtop8_scrape_$(date +%Y%m%d_%H%M%S).log
 
 # MTGGoldfish - full extraction
 echo ""
 echo "[2/3] MTGGoldfish full extract (2000 decks)..."
 go run cmd/dataset/main.go \
 --bucket file://./data-full \
 extract goldfish \
 --limit 2000 \
 --parallel 32 \
 2>&1 | tee ../../logs/goldfish_scrape_$(date +%Y%m%d_%H%M%S).log
 
 # Deckbox - test
 echo ""
 echo "[3/3] Deckbox sample (100 decks)..."
 go run cmd/dataset/main.go \
 --bucket file://./data-full \
 extract deckbox \
 --limit 100 \
 --parallel 16 \
 2>&1 | tee ../../logs/deckbox_scrape_$(date +%Y%m%d_%H%M%S).log
 
 cd ../..
 
else
 echo "Unknown mode: $MODE"
 echo "Use: ./scripts/expand_scraping.sh [quick|full]"
 exit 1
fi

# Check new state
echo ""
echo "=================================================="
NEW_COUNT=$(find $BACKEND_DIR/data-full/games/magic/mtgtop8/collections -name "*.zst" 2>/dev/null | wc -l | tr -d ' ')
ADDED=$((NEW_COUNT - CURRENT_COUNT))
echo "Scraping complete!"
echo " Previous: $CURRENT_COUNT decks"
echo " Current: $NEW_COUNT decks"
echo " Added: $ADDED decks"
echo ""

# Export new data
echo "Exporting metadata..."
cd $BACKEND_DIR
go run cmd/export-hetero/main.go \
 data-full/games/magic/mtgtop8/collections \
 ../../data/processed/decks_with_metadata_expanded.jsonl

cd ../..
EXPORT_COUNT=$(wc -l < data/processed/decks_with_metadata_expanded.jsonl | tr -d ' ')
echo " Exported: $EXPORT_COUNT decks with metadata"
echo ""

echo "=================================================="
echo "Next steps:"
echo " 1. Run quality validation: python src/ml/llm_data_validator.py"
echo " 2. Re-run experiments with expanded data"
echo " 3. Check if P@10 improves with more data"
echo "=================================================="

