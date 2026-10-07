#!/bin/bash
# Extract ALL collections from all sources - no limits
# This will extract gigabytes of data

# Don't exit on errors - continue with other extractions
set +e

# Select storage explicitly; this helper never creates a cloud bucket.
: "${BUCKET:?Set BUCKET to a file:// or s3:// URL you control}"
PARALLEL="${PARALLEL:-128}"
LOG_LEVEL="${LOG_LEVEL:-info}"

echo "=== EXTRACTING ALL COLLECTIONS ==="
echo "Bucket: $BUCKET"
echo "Parallel workers: $PARALLEL"
echo ""

cd src/backend

# 1. Scryfall - ALL cards and ALL sets
echo "📦 Extracting Scryfall cards and sets..."
SCRAPER_MAX_RESPONSE_SIZE_MB=500 go run ./cmd/dataset/main.go extract scryfall \
  --section "cards" \
  --bucket "$BUCKET" \
  --parallel "$PARALLEL" \
  --log "$LOG_LEVEL" \
  --reparse || echo "Scryfall cards extraction had errors (may already exist)"

go run ./cmd/dataset/main.go extract scryfall \
  --section "collections" \
  --bucket "$BUCKET" \
  --parallel "$PARALLEL" \
  --log "$LOG_LEVEL" \
  --reparse || echo "Scryfall sets extraction had errors (may already exist)"

# 2. MTGTop8 - ALL tournament decks (no page limit, no item limit)
echo ""
echo "🏆 Extracting MTGTop8 tournament decks (ALL pages, ALL decks)..."
go run ./cmd/dataset/main.go extract mtgtop8 \
  --bucket "$BUCKET" \
  --parallel "$PARALLEL" \
  --log "$LOG_LEVEL" \
  --reparse \
  || echo "MTGTop8 extraction had errors (continuing...)"

# 3. Goldfish - ALL metagame decks (no scroll limit, no item limit)
echo ""
echo "🐟 Extracting Goldfish metagame decks (ALL sections, ALL decks)..."
go run ./cmd/dataset/main.go extract goldfish \
  --bucket "$BUCKET" \
  --parallel "$PARALLEL" \
  --log "$LOG_LEVEL" \
  --reparse \
  || echo "Goldfish extraction had errors (continuing...)"

# 4. Deckbox - ALL user collections (no page limit, no item limit)
echo ""
echo "📚 Extracting Deckbox user collections (ALL pages, ALL collections)..."
go run ./cmd/dataset/main.go extract deckbox \
  --bucket "$BUCKET" \
  --parallel "$PARALLEL" \
  --log "$LOG_LEVEL" \
  --reparse \
  || echo "Deckbox extraction had errors (continuing...)"

echo ""
echo "✅ Extraction complete!"
echo ""
echo "Summary:"
find "$(echo $BUCKET | sed 's|file://||')/games/magic" -type f -name "*.zst" 2>/dev/null | wc -l | xargs echo "Total collections:"
