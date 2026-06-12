#!/usr/bin/env bash
# Export blob data to JSONL files
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "$0")" && pwd)"
DECKS_DIR="$BACKEND_DIR/../../data/decks"
BINARY="$BACKEND_DIR/collections-export"

# Build the dataset CLI
cd "$BACKEND_DIR"
go build -o "$BINARY" ./cmd/dataset

# Export datasets
datasets=(
    "onepiece-limitless-web:decks_onepiece_limitless-web"
    "onepiece-limitless:decks_onepiece_limitless"
    "digimon-limitless-web:decks_digimon_limitless-web"
    "goldfish:decks_magic_goldfish_new"
    "mtgtop8:decks_magic_mtgtop8_new"
    "scryfall:decks_magic_scryfall_sets"
)

for entry in "${datasets[@]}"; do
    dataset="${entry%%:*}"
    outfile="${entry#*:}"
    echo "Exporting $dataset -> $outfile.jsonl"
    if "$BINARY" cat "$dataset" --bucket file://./data-local --limit 200000 --log error > "$DECKS_DIR/$outfile.jsonl" 2>/dev/null; then
        count=$(wc -l < "$DECKS_DIR/$outfile.jsonl")
        if [ "$count" -eq 0 ]; then
            echo "  WARNING: export produced empty file"
        else
            echo "  -> $count lines"
        fi
    else
        echo "  ERROR: export failed for $dataset (exit $?)"
        rm -f "$DECKS_DIR/$outfile.jsonl"  # don't leave empty file
    fi
done

rm -f "$BINARY"
echo "Done"
