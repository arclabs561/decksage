#!/bin/bash
# Export decks from S3 blob storage
# Downloads from S3, runs export-hetero, cleans up

set -euo pipefail

GAME="${1:-}"
DATASET="${2:-}"
OUTPUT="${3:-}"

if [[ -z "$GAME" || -z "$DATASET" || -z "$OUTPUT" ]]; then
    echo "Usage: $0 <game> <dataset> <output.jsonl>"
    echo "Example: $0 pokemon limitless-web data/processed/decks_pokemon_limitless-web.jsonl"
    exit 1
fi

BUCKET="s3://games-collections"
S3_PREFIX="games/${GAME}/${DATASET}"
TEMP_DIR=$(mktemp -d)
EXPORT_BINARY="bin/export-hetero"

echo "=" * 80
echo "EXPORTING FROM S3: ${GAME}/${DATASET}"
echo "=" * 80

# Check if export-hetero exists
if [[ ! -f "$EXPORT_BINARY" ]]; then
    echo "Error: export-hetero not found. Building..."
    cd src/backend
    go build -o ../../bin/export-hetero cmd/export-hetero/main.go
    cd ../..
fi

# Check S3 data exists
echo "Checking S3 data..."
if ! s5cmd ls "${BUCKET}/${S3_PREFIX}/" > /dev/null 2>&1; then
    echo "Warning: No data found at ${BUCKET}/${S3_PREFIX}/"
    exit 1
fi

# Download from S3
echo "Downloading from S3..."
s5cmd cp "${BUCKET}/${S3_PREFIX}/*" "${TEMP_DIR}/" 2>&1 | head -20

# Count downloaded files
FILE_COUNT=$(fd -e json -e zst . "$TEMP_DIR" | wc -l | tr -d ' ')
echo "Downloaded ${FILE_COUNT} files"

if [[ $FILE_COUNT -eq 0 ]]; then
    echo "Warning: No files downloaded"
    rm -rf "$TEMP_DIR"
    exit 1
fi

# Run export-hetero
echo "Running export-hetero..."
mkdir -p "$(dirname "$OUTPUT")"
"$EXPORT_BINARY" "$TEMP_DIR" "$OUTPUT"

# Verify output
if [[ -f "$OUTPUT" ]]; then
    DECK_COUNT=$(wc -l < "$OUTPUT" | tr -d ' ')
    echo "Exported ${DECK_COUNT} decks to ${OUTPUT}"
else
    echo "Error: Export failed - no output file"
    rm -rf "$TEMP_DIR"
    exit 1
fi

# Clean up
echo "Cleaning up..."
rm -rf "$TEMP_DIR"

echo "=" * 80
echo "Export complete!"
echo "=" * 80

