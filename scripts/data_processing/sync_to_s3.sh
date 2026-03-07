#!/bin/bash
# Sync all important data to S3 for backup (using s5cmd for speed)
set -euo pipefail

BUCKET="s3://games-collections"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"

echo "Syncing data to S3 via s5cmd..."
echo ""

# Build s5cmd batch file for parallel uploads
BATCH=$(mktemp)
trap 'rm -f "$BATCH"' EXIT

add() {
    local src="$1" dst="$2"
    if [ -f "$src" ]; then
        echo "cp $src $dst" >> "$BATCH"
    else
        echo "  SKIP: $src (not found)" >&2
    fi
}

# 1. Per-game processed data
echo "=== Per-Game Processed Data ==="
for game in magic pokemon yugioh; do
    for f in data/processed/*_${game}*; do
        [ -f "$f" ] && add "$f" "$BUCKET/processed/$(basename "$f")"
    done
done

# 2. Per-game deck files
echo "=== Per-Game Deck Files ==="
for game in magic pokemon yugioh; do
    for f in data/decks/decks_${game}_*.jsonl; do
        [ -f "$f" ] && add "$f" "$BUCKET/processed/$(basename "$f")"
    done
done

# 3. Per-game deck frequency
echo "=== Deck Frequency ==="
for game in magic pokemon yugioh; do
    add "data/processed/deck_frequency_${game}.json" \
        "$BUCKET/processed/deck_frequency_${game}.json"
done

# 4. Fandom scrape
echo "=== Fandom Scrape ==="
add "data/processed/yugioh_fandom_cards.json" "$BUCKET/processed/yugioh_fandom_cards.json"

# 5. Multi-game processed data
echo "=== Multi-Game Processed Data ==="
add "data/processed/pairs_multi_game.csv" "$BUCKET/processed/pairs_multi_game.csv"
add "data/processed/pairs_large.csv" "$BUCKET/processed/pairs_large.csv"
add "data/processed/card_attributes_enriched.csv" "$BUCKET/processed/card_attributes_enriched.csv"
add "data/processed/card_attributes_minimal.csv" "$BUCKET/processed/card_attributes_minimal.csv"
add "data/processed/decks_all_final.jsonl" "$BUCKET/processed/decks_all_final.jsonl"

# 6. Embeddings (v4)
echo "=== Embeddings (v4) ==="
for game in magic pokemon yugioh; do
    add "data/embeddings/${game}_cleaned_v4.wv" "$BUCKET/embeddings/${game}_cleaned_v4.wv"
done

# 7. Graph data (sync dir via individual files)
echo "=== Graph Data ==="
if [ -d "data/graphs" ]; then
    for f in data/graphs/*; do
        [ -f "$f" ] && add "$f" "$BUCKET/graphs/$(basename "$f")"
    done
fi

# 8. Experiments
echo "=== Experiments ==="
if [ -d "experiments" ]; then
    for f in experiments/*; do
        [ -f "$f" ] && add "$f" "$BUCKET/experiments/$(basename "$f")"
    done
fi

# Show batch stats and run
TOTAL=$(wc -l < "$BATCH" | tr -d ' ')
echo ""
echo "Uploading $TOTAL files via s5cmd (parallel)..."
echo ""

s5cmd --stat run "$BATCH"

echo ""
echo "Sync complete!"
echo ""
echo "Verify:"
echo "  s5cmd ls '$BUCKET/*' | wc -l"
echo "  s5cmd du '$BUCKET/*'"
