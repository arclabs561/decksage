#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Normalize card names in training corpus files to canonical English forms.

Loads canonical name sets from enriched CSVs, then rewrites collections
or pairs CSV files, dropping names not in the canonical set. This removes
non-English card names (Spanish, French, Japanese) that enter the corpus
from multilingual tournament sites.

Supports two input formats:
  - Collections CSV: each row is a deck (list of card names)
  - Pairs CSV: NAME_1, NAME_2, COUNT_SET, COUNT_MULTISET columns

Usage:
  # Dry run — show what would be removed
  uv run scripts/data_processing/normalize_corpus_names.py --dry-run

  # Clean collections CSVs in place
  uv run scripts/data_processing/normalize_corpus_names.py --collections

  # Clean pairs CSV (pairs_large.csv)
  uv run scripts/data_processing/normalize_corpus_names.py --pairs

  # Both
  uv run scripts/data_processing/normalize_corpus_names.py --collections --pairs
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path


# YGOProDeck numeric IDs that leak from deck JSONLs when --name-mapping is
# incomplete or omitted.  These have no metadata and form isolated subgraphs.
_NUMERIC_ID_RE = re.compile(r"^Card_\d+$")


REPO_ROOT = Path(__file__).resolve().parents[2]

# Enriched CSVs — canonical name source
ENRICHED_CSVS = {
    "magic": REPO_ROOT / "data" / "processed" / "card_attributes_magic_enriched.csv",
    "pokemon": REPO_ROOT / "data" / "processed" / "card_attributes_pokemon_enriched.csv",
    "yugioh": REPO_ROOT / "data" / "processed" / "card_attributes_yugioh_enriched.csv",
}

# Training corpus files
COLLECTIONS_FILES = {
    "pokemon": REPO_ROOT / "data" / "decks" / "collections_pokemon.csv",
    "yugioh": REPO_ROOT / "data" / "decks" / "collections_yugioh.csv",
}

PAIRS_FILE = REPO_ROOT / "data" / "processed" / "pairs_large.csv"


def is_valid_card_name(name: str, canonical: set[str]) -> bool:
    """Check if a card name is canonical and not a numeric ID leak."""
    return name in canonical and not _NUMERIC_ID_RE.match(name)


def load_canonical_names() -> set[str]:
    """Load all canonical card names from enriched CSVs."""
    names: set[str] = set()
    for game, path in ENRICHED_CSVS.items():
        if not path.exists():
            print(f"  Warning: {path} not found, skipping {game}")
            continue
        count = 0
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                name = row.get("name", "").strip()
                if name:
                    names.add(name)
                    count += 1
        print(f"  {game}: {count:,} canonical names")
    return names


def audit_collections(canonical: set[str]) -> dict[str, set[str]]:
    """Audit collections CSVs for non-canonical names (dry run)."""
    dropped_by_file: dict[str, set[str]] = {}
    for game, path in COLLECTIONS_FILES.items():
        if not path.exists():
            print(f"  {path}: not found")
            continue
        dropped: set[str] = set()
        total_names: set[str] = set()
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.reader(f):
                for name in row:
                    name = name.strip()
                    if name:
                        total_names.add(name)
                        if not is_valid_card_name(name, canonical):
                            dropped.add(name)
        numeric_ids = {n for n in dropped if _NUMERIC_ID_RE.match(n)}
        non_canonical = dropped - numeric_ids
        pct = len(dropped) / len(total_names) * 100 if total_names else 0
        print(
            f"  {game}: {len(total_names):,} unique names, "
            f"{len(dropped):,} non-canonical ({pct:.1f}%)"
        )
        if numeric_ids:
            print(f"    ({len(numeric_ids)} Card_XXXX numeric IDs)")
        if non_canonical:
            for n in sorted(non_canonical)[:10]:
                print(f"    - {n}")
            if len(non_canonical) > 10:
                print(f"    ... and {len(non_canonical) - 10} more")
        dropped_by_file[game] = dropped
    return dropped_by_file


def audit_pairs(canonical: set[str]) -> set[str]:
    """Audit pairs CSV for non-canonical names."""
    if not PAIRS_FILE.exists():
        print(f"  {PAIRS_FILE}: not found")
        return set()
    dropped: set[str] = set()
    total_names: set[str] = set()
    with open(PAIRS_FILE, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header:
            return set()
        for row in reader:
            if len(row) < 2:
                continue
            for name in row[:2]:
                name = name.strip()
                if name:
                    total_names.add(name)
                    if not is_valid_card_name(name, canonical):
                        dropped.add(name)
    numeric_ids = {n for n in dropped if _NUMERIC_ID_RE.match(n)}
    non_canonical = dropped - numeric_ids
    pct = len(dropped) / len(total_names) * 100 if total_names else 0
    print(
        f"  pairs_large: {len(total_names):,} unique names, "
        f"{len(dropped):,} non-canonical ({pct:.1f}%)"
    )
    if numeric_ids:
        print(f"    ({len(numeric_ids)} Card_XXXX numeric IDs)")
    if non_canonical:
        for n in sorted(non_canonical)[:10]:
            print(f"    - {n}")
        if len(non_canonical) > 10:
            print(f"    ... and {len(non_canonical) - 10} more")
    return dropped


def clean_collections(canonical: set[str]) -> None:
    """Rewrite collections CSVs, dropping non-canonical names."""
    for game, path in COLLECTIONS_FILES.items():
        if not path.exists():
            continue
        rows_in = 0
        rows_out = 0
        names_dropped = 0
        cleaned_rows: list[list[str]] = []
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.reader(f):
                rows_in += 1
                cleaned = [n for n in row if is_valid_card_name(n.strip(), canonical)]
                names_dropped += len(row) - len(cleaned)
                if cleaned:  # Don't write empty decks
                    cleaned_rows.append(cleaned)
                    rows_out += 1

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(cleaned_rows)

        print(
            f"  {game}: {rows_in} -> {rows_out} decks, {names_dropped:,} name occurrences removed"
        )


def clean_pairs(canonical: set[str]) -> None:
    """Rewrite pairs CSV, dropping rows with non-canonical names."""
    if not PAIRS_FILE.exists():
        return
    rows_in = 0
    rows_out = 0
    cleaned_rows: list[list[str]] = []

    with open(PAIRS_FILE, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header:
            return
        for row in reader:
            rows_in += 1
            if len(row) < 2:
                continue
            name1, name2 = row[0].strip(), row[1].strip()
            if is_valid_card_name(name1, canonical) and is_valid_card_name(name2, canonical):
                cleaned_rows.append(row)
                rows_out += 1

    with open(PAIRS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(cleaned_rows)

    dropped = rows_in - rows_out
    print(
        f"  pairs_large: {rows_in:,} -> {rows_out:,} rows "
        f"({dropped:,} dropped, {dropped / rows_in * 100:.1f}%)"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize card names in training corpus to canonical English forms"
    )
    parser.add_argument("--dry-run", action="store_true", help="Audit only, don't modify files")
    parser.add_argument("--collections", action="store_true", help="Clean collections CSVs")
    parser.add_argument("--pairs", action="store_true", help="Clean pairs CSV")
    args = parser.parse_args()

    if not args.dry_run and not args.collections and not args.pairs:
        args.dry_run = True  # Default to dry run

    print("Loading canonical names from enriched CSVs...")
    canonical = load_canonical_names()
    print(f"  Total canonical names: {len(canonical):,}\n")

    if args.dry_run:
        print("=== Audit: Collections CSVs ===")
        audit_collections(canonical)
        print("\n=== Audit: Pairs CSV ===")
        audit_pairs(canonical)
        print("\nDry run complete. Use --collections and/or --pairs to clean.")
        return 0

    if args.collections:
        print("=== Cleaning collections CSVs ===")
        clean_collections(canonical)

    if args.pairs:
        print("\n=== Cleaning pairs CSV ===")
        clean_pairs(canonical)

    print("\nDone. Rebuild embeddings with the cleaned corpus.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
