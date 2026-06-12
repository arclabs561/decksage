#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Convert deck JSONL files to collections CSV for corpus word2vec training.

The CollectionsCorpus (src/ml/training/corpus.py) expects a CSV where each
row is a deck represented as a list of card names. This script reads the
standard deck JSONL format (as exported by the Go `dataset cat` command
or stored on S3) and produces that CSV.

JSONL format (per line):
  {"deck_id": "...", "cards": [{"name": "...", "count": N, "partition": "Deck"}, ...]}

Collections CSV format (per line):
  CardA,CardB,CardC,...  (one row per deck, card repeated by count)

Data flow position: Order 1 (deck JSONL) -> Order 1.5 (collections CSV)
Consumed by: src/ml/training/word2vec.py via CollectionsCorpus

Usage:
  uv run scripts/data_processing/jsonl_to_collections_csv.py \\
    --input data/decks/decks_pokemon_limitless-web.jsonl \\
    --output data/decks/collections_pokemon.csv

  # Multiple inputs (merged):
  uv run scripts/data_processing/jsonl_to_collections_csv.py \\
    --input data/decks/decks_pokemon.jsonl data/decks/decks_pokemon_limitless-web.jsonl \\
    --output data/decks/collections_pokemon.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path


# YGOProDeck numeric IDs (e.g., Card_10000080) that should never enter the
# training corpus.  Dropped even when --canonical-names is not provided.
_NUMERIC_ID_RE = re.compile(r"^Card_\d+$")


def load_name_mapping(mapping_path: Path) -> dict[str, str]:
    """Load a Card_ID -> real name mapping JSON."""
    with open(mapping_path) as f:
        return json.load(f)


def convert_jsonl_to_collections(
    input_paths: list[Path],
    output_path: Path,
    partition_filter: str | None = None,
    deduplicate: bool = True,
    name_mapping: dict[str, str] | None = None,
    canonical_names: set[str] | None = None,
) -> dict[str, int]:
    """Convert deck JSONL files to collections CSV.

    Returns stats dict with deck_count, card_count, unique_cards, skipped.
    """
    seen_ids: set[str] = set()
    stats = {
        "deck_count": 0,
        "card_count": 0,
        "unique_cards": set(),
        "skipped": 0,
        "remapped": 0,
        "filtered": 0,
    }

    with open(output_path, "w", newline="") as out_f:
        writer = csv.writer(out_f)

        for input_path in input_paths:
            with open(input_path) as in_f:
                for line_no, line in enumerate(in_f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        deck = json.loads(line)
                    except json.JSONDecodeError:
                        print(
                            f"  Warning: invalid JSON at {input_path.name}:{line_no}",
                            file=sys.stderr,
                        )
                        stats["skipped"] += 1
                        continue

                    # Deduplicate by deck_id
                    deck_id = deck.get("deck_id", f"{input_path.name}:{line_no}")
                    if deduplicate and deck_id in seen_ids:
                        stats["skipped"] += 1
                        continue
                    seen_ids.add(deck_id)

                    # Extract card names, expanding by count
                    cards_list: list[str] = []
                    for card in deck.get("cards", []):
                        name = card.get("name", "")
                        if not name:
                            continue
                        # Apply name mapping (e.g., Card_<passcode> -> real name)
                        if name_mapping and name in name_mapping:
                            name = name_mapping[name]
                            stats["remapped"] += 1
                        # Drop numeric IDs not resolved by name mapping
                        if _NUMERIC_ID_RE.match(name):
                            stats["filtered"] += 1
                            continue
                        # Optional partition filter (e.g., "Deck" to exclude sideboard)
                        if partition_filter and card.get("partition", "") != partition_filter:
                            continue
                        # Filter to canonical names only (drops non-English variants)
                        if canonical_names and name not in canonical_names:
                            stats["filtered"] += 1
                            continue
                        count = card.get("count", 1)
                        cards_list.extend([name] * count)

                    if not cards_list:
                        stats["skipped"] += 1
                        continue

                    writer.writerow(cards_list)
                    stats["deck_count"] += 1
                    stats["card_count"] += len(cards_list)
                    stats["unique_cards"].update(cards_list)

    unique_count = len(stats["unique_cards"])
    del stats["unique_cards"]
    stats["unique_cards"] = unique_count
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert deck JSONL to collections CSV for word2vec training",
    )
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        nargs="+",
        required=True,
        help="Input deck JSONL file(s)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        required=True,
        help="Output collections CSV",
    )
    parser.add_argument(
        "--partition",
        type=str,
        default=None,
        help="Filter cards by partition (e.g., 'Deck' to exclude sideboard)",
    )
    parser.add_argument(
        "--no-dedup",
        action="store_true",
        help="Don't deduplicate by deck_id",
    )
    parser.add_argument(
        "--name-mapping",
        type=Path,
        default=None,
        help="JSON file mapping Card_IDs to real names (e.g., data/yugioh_card_mapping.json)",
    )
    parser.add_argument(
        "--canonical-names",
        type=Path,
        default=None,
        help="CSV with 'name' column; only names in this file are kept (drops non-English variants)",
    )
    args = parser.parse_args()

    # Validate inputs
    for p in args.input:
        if not p.exists():
            print(f"Error: {p} not found", file=sys.stderr)
            return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)

    # Load name mapping if provided
    mapping = None
    if args.name_mapping:
        if not args.name_mapping.exists():
            print(f"Error: mapping file {args.name_mapping} not found", file=sys.stderr)
            return 1
        mapping = load_name_mapping(args.name_mapping)
        print(f"Loaded {len(mapping):,} name mappings from {args.name_mapping.name}")

    # Load canonical names if provided
    canonical = None
    if args.canonical_names:
        if not args.canonical_names.exists():
            print(f"Error: canonical names file {args.canonical_names} not found", file=sys.stderr)
            return 1
        canonical = set()
        import csv as csv_mod

        with open(args.canonical_names, newline="", encoding="utf-8") as cf:
            for row in csv_mod.DictReader(cf):
                name = row.get("name", "").strip()
                if name:
                    canonical.add(name)
        print(f"Loaded {len(canonical):,} canonical names from {args.canonical_names.name}")

    print(f"Converting {len(args.input)} file(s) to collections CSV...")
    stats = convert_jsonl_to_collections(
        args.input,
        args.output,
        partition_filter=args.partition,
        deduplicate=not args.no_dedup,
        name_mapping=mapping,
        canonical_names=canonical,
    )

    print(f"  Decks:        {stats['deck_count']:,}")
    print(f"  Total cards:  {stats['card_count']:,}")
    print(f"  Unique cards: {stats['unique_cards']:,}")
    print(f"  Skipped:      {stats['skipped']:,}")
    if stats.get("remapped"):
        print(f"  Remapped:     {stats['remapped']:,} card name references")
    if stats.get("filtered"):
        print(f"  Filtered:     {stats['filtered']:,} non-canonical name occurrences")
    print(f"  Output:       {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
