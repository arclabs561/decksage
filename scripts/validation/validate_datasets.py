#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
# "pandas",
# ]
# ///
"""
Validate dataset consistency and quality.
Checks:
- Card names in pairs match card attributes
- Test set queries exist in card attributes
- Deck files are non-empty
- No duplicate pairs
- Card coverage and duplicate pairs in the first million rows
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path


def card_names(path: Path) -> set[str]:
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        if "name" not in (reader.fieldnames or ()):
            raise ValueError(f"{path}: missing name column")
        names = {name for row in reader if (name := (row.get("name") or "").strip().lower())}
    if not names:
        raise ValueError(f"{path}: no card names")
    return names


def check_card_attributes_coverage(
    pairs_csv: Path,
    attributes_csv: Path,
) -> list[str]:
    """Check that card names in pairs exist in attributes."""
    issues = []
    print("Loading card attributes...")
    known = card_names(attributes_csv)
    print(f"Found {len(known)} cards in attributes")
    print("Checking pairs...")
    missing_cards = set()
    with open(pairs_csv) as f:
        reader = csv.DictReader(f)
        if not {"NAME_1", "NAME_2"} <= set(reader.fieldnames or ()):
            raise ValueError(f"{pairs_csv}: expected NAME_1 and NAME_2")
        for i, row in enumerate(reader):
            if i % 100000 == 0 and i > 0:
                print(f" Processed {i:,} pairs...")
            n1 = (row.get("NAME_1") or "").strip().lower()
            n2 = (row.get("NAME_2") or "").strip().lower()
            if not n1 or not n2:
                raise ValueError(f"{pairs_csv}: empty card name at row {i + 2}")
            if n1 and n1 not in known:
                missing_cards.add(n1)
            if n2 and n2 not in known:
                missing_cards.add(n2)
            if i >= 1000000:  # Sample
                break
    if missing_cards:
        issues.append(f"Found {len(missing_cards)} cards in pairs not in attributes (sample)")
        if len(missing_cards) <= 20:
            issues.append(f" Examples: {', '.join(list(missing_cards)[:10])}")
    return issues


def check_test_set_coverage(
    test_set_path: Path,
    attributes_csv: Path,
) -> list[str]:
    """Check that test set queries exist in card attributes."""
    issues = []
    print(f"Loading test set: {test_set_path}")
    with open(test_set_path) as f:
        test_set = json.load(f)
    queries = test_set.get("queries", test_set) if isinstance(test_set, dict) else test_set
    if isinstance(queries, dict):
        query_names = set(queries)
    elif isinstance(queries, list):
        query_names = {q.get("query", "") if isinstance(q, dict) else "" for q in queries}
    else:
        raise ValueError(f"{test_set_path}: expected a queries mapping or list")
    if not query_names or not all(isinstance(q, str) and q.strip() for q in query_names):
        raise ValueError(f"{test_set_path}: missing query names")
    print(f"Found {len(query_names)} queries")
    print("Loading card attributes...")
    known = card_names(attributes_csv)
    missing_queries = {q for q in query_names if q.strip().lower() not in known}
    if missing_queries:
        issues.append(f"Found {len(missing_queries)} queries not in card attributes")
        issues.append(f" Missing: {', '.join(list(missing_queries)[:10])}")
    return issues


def check_deck_files() -> list[str]:
    """Check that deck files are non-empty."""
    issues = []
    deck_files = [
        Path("data/decks/yugioh_decks.jsonl"),
        Path("data/processed/decks_pokemon.jsonl"),
    ]
    for deck_file in deck_files:
        if not deck_file.exists():
            issues.append(f"Deck file missing: {deck_file}")
            continue
        with open(deck_file) as f:
            count = sum(1 for _ in f)
        if count == 0:
            issues.append(f"Deck file is empty: {deck_file}")
        else:
            print(f"{deck_file.name}: {count} decks")
    return issues


def check_duplicate_pairs(pairs_csv: Path) -> list[str]:
    """Check for duplicate pairs."""
    issues = []
    print(f"Checking for duplicate pairs in {pairs_csv.name}...")
    seen = set()
    duplicates = []
    with open(pairs_csv) as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i % 100000 == 0 and i > 0:
                print(f" Processed {i:,} pairs...")
            n1 = row.get("NAME_1", "").strip()
            n2 = row.get("NAME_2", "").strip()
            # Normalize pair (order-independent)
            pair = tuple(sorted([n1, n2]))
            if pair in seen:
                duplicates.append(pair)
            seen.add(pair)
            if i >= 1000000:  # Sample
                break
    if not seen:
        issues.append(f"{pairs_csv}: no data rows")
    if duplicates:
        issues.append(f"Found {len(duplicates)} duplicate pairs (sample)")
    return issues


def check_multi_game_claim(pairs_csv: Path) -> list[str]:
    """Check if pairs_multi_game.csv actually contains multiple games."""
    issues = []
    if "multi_game" not in pairs_csv.name:
        return issues
    print(f"Checking game distribution in {pairs_csv.name}...")
    games = Counter()
    with open(pairs_csv) as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            g1 = row.get("GAME_1", "").strip()
            g2 = row.get("GAME_2", "").strip()
            games[g1] += 1
            games[g2] += 1
            if i >= 100000:  # Sample
                break
    unique_games = {g for g in games.keys() if g}
    if len(unique_games) <= 1:
        issues.append(f"File named 'multi_game' but only contains: {unique_games}")
        issues.append(" Consider renaming to reflect single-game content")
    else:
        print(f" Found games: {sorted(unique_games)}")
    return issues


def main() -> int:
    """Run dataset validation."""
    parser = argparse.ArgumentParser(description="Validate dataset consistency")
    parser.add_argument("--pairs", type=Path, help="Pairs CSV to validate")
    parser.add_argument("--test-set", type=Path, help="Test set JSON to validate")
    parser.add_argument("--all", action="store_true", help="Run all checks")
    parser.add_argument(
        "--attributes", type=Path, default=Path("data/processed/card_attributes_enriched.csv")
    )
    args = parser.parse_args()
    all_issues = []
    pairs = [args.pairs] if args.pairs else []
    sets = [args.test_set] if args.test_set else []
    if args.all or not (pairs or sets):
        all_issues.extend(check_deck_files())
        pairs.extend(
            [Path("data/processed/pairs_large.csv"), Path("data/processed/pairs_multi_game.csv")]
        )
        sets.extend(
            Path(f"experiments/test_set_canonical_{game}.json")
            for game in ("magic", "pokemon", "yugioh")
        )
    for path in dict.fromkeys(pairs):
        try:
            all_issues.extend(check_card_attributes_coverage(path, args.attributes))
            all_issues.extend(check_duplicate_pairs(path))
            all_issues.extend(check_multi_game_claim(path))
        except (OSError, ValueError, csv.Error) as exc:
            all_issues.append(str(exc))
    for path in dict.fromkeys(sets):
        try:
            all_issues.extend(check_test_set_coverage(path, args.attributes))
        except (OSError, ValueError, csv.Error) as exc:
            all_issues.append(str(exc))
    # Report results
    print("\n" + "=" * 60)
    print("Validation Results")
    print("=" * 60)
    if all_issues:
        print(f"\nFound {len(all_issues)} issues:")
        for issue in all_issues:
            print(f" Warning: {issue}")
        return 1
    else:
        print("\n No issues found!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
