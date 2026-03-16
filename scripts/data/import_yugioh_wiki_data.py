#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
Import Yu-Gi-Oh! wiki enrichment data into ygoprodeck card JSON files.

Reads wiki-scraped JSON files from a source directory and enriches
existing ygoprodeck card blobs with:
  - classifications: list of card classifications from wiki
  - wiki_url: first card_references URL (wiki page link)

Usage:
    uv run scripts/data/import_yugioh_wiki_data.py \
        --wiki-dir /path/to/devdev-yugi/cards/ \
        --blob-dir /path/to/blob/games/yugioh/ygoprodeck/cards/

Cards are matched by passcode (numeric ID).
"""

import argparse
import json
import os
import sys
from pathlib import Path


def load_wiki_cards(wiki_dir: Path) -> dict[int, dict]:
    """Load wiki card data, keyed by passcode."""
    cards: dict[int, dict] = {}
    count = 0
    errors = 0

    for path in wiki_dir.glob("*.json"):
        try:
            with open(path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            errors += 1
            if errors <= 10:
                print(f"  WARN: failed to read {path.name}: {e}", file=sys.stderr)
            continue

        passcode = data.get("passcode")
        if not isinstance(passcode, int) or passcode <= 0:
            continue

        entry: dict = {}

        classifications = data.get("classifications")
        if isinstance(classifications, list) and classifications:
            entry["classifications"] = [str(c) for c in classifications if c]

        card_refs = data.get("card_references")
        if isinstance(card_refs, list) and card_refs:
            first_ref = card_refs[0]
            if isinstance(first_ref, str) and first_ref:
                entry["wiki_url"] = first_ref
            elif isinstance(first_ref, dict) and first_ref.get("url"):
                entry["wiki_url"] = first_ref["url"]

        if entry:
            cards[passcode] = entry
            count += 1

    print(f"Loaded {count} wiki cards with enrichment data ({errors} read errors)")
    return cards


def enrich_blob_cards(
    blob_dir: Path,
    wiki_cards: dict[int, dict],
    *,
    dry_run: bool = False,
) -> tuple[int, int, int]:
    """Enrich ygoprodeck card JSONs with wiki data. Returns (matched, updated, skipped)."""
    matched = 0
    updated = 0
    skipped = 0

    for path in blob_dir.glob("*.json"):
        try:
            with open(path) as f:
                card = json.load(f)
        except (json.JSONDecodeError, OSError):
            skipped += 1
            continue

        passcode = card.get("passcode")
        if not isinstance(passcode, int) or passcode <= 0:
            skipped += 1
            continue

        wiki = wiki_cards.get(passcode)
        if wiki is None:
            continue

        matched += 1

        # Check if already enriched with same data
        existing_class = card.get("classifications", [])
        existing_wiki = card.get("wiki_url", "")
        new_class = wiki.get("classifications", [])
        new_wiki = wiki.get("wiki_url", "")

        if existing_class == new_class and existing_wiki == new_wiki:
            continue

        # Apply enrichment
        if new_class:
            card["classifications"] = new_class
        if new_wiki:
            card["wiki_url"] = new_wiki

        if not dry_run:
            with open(path, "w") as f:
                json.dump(card, f, ensure_ascii=False, separators=(",", ":"))

        updated += 1

    return matched, updated, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich ygoprodeck card blobs with wiki data")
    parser.add_argument(
        "--wiki-dir",
        type=Path,
        required=True,
        help="Directory containing wiki-scraped card JSON files",
    )
    parser.add_argument(
        "--blob-dir",
        type=Path,
        required=True,
        help="Directory containing ygoprodeck card JSON blobs",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing",
    )
    args = parser.parse_args()

    if not args.wiki_dir.is_dir():
        print(f"ERROR: wiki directory does not exist: {args.wiki_dir}", file=sys.stderr)
        sys.exit(1)
    if not args.blob_dir.is_dir():
        print(f"ERROR: blob directory does not exist: {args.blob_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading wiki cards from {args.wiki_dir}...")
    wiki_cards = load_wiki_cards(args.wiki_dir)

    if not wiki_cards:
        print("No wiki cards with enrichment data found, nothing to do.")
        return

    action = "Would update" if args.dry_run else "Enriching"
    print(f"{action} cards in {args.blob_dir}...")

    matched, updated, skipped = enrich_blob_cards(
        args.blob_dir,
        wiki_cards,
        dry_run=args.dry_run,
    )

    print(f"Done: {matched} matched by passcode, {updated} updated, {skipped} skipped")


if __name__ == "__main__":
    main()
