#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
data=${1:-data/processed}
stage=$(mktemp -d "$data/.deck-fixes.XXXXXXXX")
trap 'rm -rf -- "$stage"' EXIT
python3 -m scripts.enhance_exported_decks --input "$data/decks_all_unified.jsonl" --output "$stage/enhanced.jsonl"
python3 -m scripts.backfill_metadata --input "$stage/enhanced.jsonl" --output "$stage/final.jsonl"
if [[ ! -s "$stage/final.jsonl" ]]; then
    echo "No decks survived processing" >&2
    exit 1
fi
python3 -m scripts.validation.validate_exported_decks --input "$stage/final.jsonl" --strict
mv -- "$stage/enhanced.jsonl" "$data/decks_all_enhanced.jsonl"
mv -- "$stage/final.jsonl" "$data/decks_all_final.jsonl"
