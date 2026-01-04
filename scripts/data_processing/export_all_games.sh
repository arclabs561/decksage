#!/bin/bash
# Export all games from S3 or local blob storage
# Uses export-blob (Phase 2 - better solution)

set -euo pipefail

BUCKET_URL="${1:-s3://games-collections}"
OUTPUT_DIR="${2:-data/processed}"

echo "=" * 80
echo "EXPORTING ALL GAMES FROM BLOB STORAGE"
echo "=" * 80
echo "Bucket: $BUCKET_URL"
echo "Output: $OUTPUT_DIR"
echo ""

# Check if export-blob exists
EXPORT_BINARY="bin/export-blob"
if [[ ! -f "$EXPORT_BINARY" ]]; then
    echo "Error: export-blob not found. Building..."
    cd src/backend
    go build -o ../../bin/export-blob cmd/export-blob/main.go
    cd ../..
fi

mkdir -p "$OUTPUT_DIR"

# Define all game/dataset combinations
declare -a EXPORTS=(
    "pokemon limitless-web"
    "yugioh ygoprodeck-tournament"
    "digimon digimon-limitless-web"
    "onepiece onepiece-limitless-web"
    "riftbound riftcodex"
    "riftbound riftboundgg"
    "riftbound riftmana"
)

TOTAL_EXPORTED=0

for export_spec in "${EXPORTS[@]}"; do
    read -r game dataset <<< "$export_spec"
    output_file="${OUTPUT_DIR}/decks_${game}_${dataset}.jsonl"

    echo "Exporting ${game}/${dataset}..."

    if "$EXPORT_BINARY" "$BUCKET_URL" "$game" "$dataset" "$output_file" 2>&1; then
        if [[ -f "$output_file" ]]; then
            count=$(wc -l < "$output_file" | tr -d ' ')
            if [[ $count -gt 0 ]]; then
                echo "  Exported ${count} decks to ${output_file}"
                TOTAL_EXPORTED=$((TOTAL_EXPORTED + count))
            else
                echo "  Warning: No decks exported (file empty or not found)"
                rm -f "$output_file"
            fi
        else
            echo "  Warning: Export completed but no output file found"
        fi
    else
        echo "  Warning: Export failed for ${game}/${dataset}"
    fi
    echo ""
done

echo "=" * 80
echo "Total decks exported: ${TOTAL_EXPORTED}"
echo "=" * 80
