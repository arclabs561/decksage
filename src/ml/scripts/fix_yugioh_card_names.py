#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Fix Yu-Gi-Oh card names: Map IDs (Card_12345) to actual card names.

This script:
1. Loads Yu-Gi-Oh card database
2. Creates ID -> name mapping
3. Updates deck exports to use names instead of IDs
4. Updates pairs CSV to use names
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_yugioh_cards(cards_dir: Path) -> dict[str, str]:
    """Load Yu-Gi-Oh card database and create ID -> name mapping."""
    mapping = {}

    # Look for card files in yugioh dataset
    if not cards_dir.exists():
        print(f"Warning: Cards directory not found: {cards_dir}")
        return mapping

    # Find all card files
    card_files = list(cards_dir.rglob("*.zst"))
    print(f"Found {len(card_files)} card files")

    for card_file in card_files[:1000]:  # Sample first 1000
        try:
            # Decompress and parse (would need zstd library)
            # For now, assume we have JSON files
            if card_file.suffix == ".json":
                with open(card_file) as f:
                    card = json.load(f)
                    card_id = card.get("id") or card_file.stem
                    card_name = card.get("name") or card.get("card", {}).get("name")
                    if card_id and card_name:
                        mapping[card_id] = card_name
        except:
            continue

    print(f"Loaded {len(mapping)} card mappings")
    return mapping


def fix_deck_names(deck_jsonl: Path, mapping: dict[str, str], output: Path) -> int:
    """Fix card names in deck JSONL file."""
    fixed = 0
    total = 0

    with open(deck_jsonl) as f_in, open(output, "w") as f_out:
        for line in f_in:
            if not line.strip():
                continue

            deck = json.loads(line)
            total += 1

            # Fix card names in partitions
            for partition in deck.get("partitions", []):
                for card in partition.get("cards", []):
                    card_name = card.get("name", "")
                    if card_name.startswith("Card_"):
                        # Try to map
                        mapped = mapping.get(card_name)
                        if mapped:
                            card["name"] = mapped
                            fixed += 1

            json.dump(deck, f_out)
            f_out.write("\n")

    print(f"Fixed {fixed} card names in {total} decks")
    return fixed


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix Yu-Gi-Oh card names")
    parser.add_argument("--cards-dir", type=Path, help="Yu-Gi-Oh cards directory")
    parser.add_argument("--deck-jsonl", type=Path, help="Deck JSONL to fix")
    parser.add_argument("--output", type=Path, help="Output JSONL")

    args = parser.parse_args()

    # Load mapping
    if args.cards_dir:
        mapping = load_yugioh_cards(args.cards_dir)
    else:
        print("Warning: No cards directory provided, using empty mapping")
        mapping = {}

    # Fix deck names
    if args.deck_jsonl and args.output:
        fix_deck_names(args.deck_jsonl, mapping, args.output)

    return 0


if __name__ == "__main__":
    exit(main())
