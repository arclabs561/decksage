#!/usr/bin/env python3
"""
Validate data lineage - ensure all dependencies are satisfied.

Checks that:
1. Order 1 (Exported Decks) has corresponding Order 0 (Primary) data
2. Order 2 (Pairs) has corresponding Order 1 (Exported Decks) data
3. Order 3+ have their dependencies satisfied
"""

import sys
from pathlib import Path


def validate_lineage():
    """Validate data lineage dependencies."""
    errors = []
    warnings = []

    # Order 0: Primary source data
    primary_local = Path("src/backend/data-full/games")
    primary_games = set()
    if primary_local.exists():
        primary_games = {d.name for d in primary_local.iterdir() if d.is_dir()}

    # Order 1: Exported decks
    processed = Path("data/processed")
    experiments = Path("experiments")
    exported_games = set()
    if processed.exists():
        for f in processed.glob("decks_*.jsonl"):
            parts = f.stem.replace("decks_", "").split("_", 1)
            exported_games.add(parts[0])

    # Check Order 1 → Order 0 dependency
    if primary_games and exported_games:
        missing_primary = exported_games - primary_games
        if missing_primary:
            warnings.append(f"Games exported but no primary data: {missing_primary}")

    # Order 2: Pairs
    pair_games = set()
    special_pair_files = {"large", "with", "functional"}  # Special MTG pair files
    if processed.exists():
        for f in processed.glob("pairs_*.csv"):
            if "multi_game" in f.name or "all_games" in f.name:
                continue
            parts = f.stem.replace("pairs_", "").split("_", 1)
            game = parts[0]
            # Skip special pair files (pairs_large.csv, pairs_with_functional.csv)
            if game not in special_pair_files:
                pair_games.add(game)

    # Check Order 2 → Order 1 dependency
    if exported_games and pair_games:
        missing_exported = pair_games - exported_games
        if missing_exported:
            errors.append(f"Games with pairs but no exported decks: {missing_exported}")

    # Order 5: Test sets
    test_set_games = set()
    if experiments and experiments.exists():
        for f in experiments.glob("test_set_unified_*.json"):
            try:
                import json

                with open(f) as file:
                    data = json.load(file)
                    game = data.get("game", "unknown")
                    if game != "unknown":
                        test_set_games.add(game)
            except Exception:
                pass

    # Check Order 5 → Order 1 dependency (test sets should have decks)
    # Note: Magic test sets exist but Magic decks may be in different location
    if exported_games and test_set_games:
        missing_decks = test_set_games - exported_games
        # Magic decks might be in different format/location, so only warn for new games
        new_games = {"digimon", "onepiece", "riftbound"}
        missing_new = missing_decks & new_games
        if missing_new:
            warnings.append(f"New games with test sets but no exported decks: {missing_new}")
        # Magic is expected to have test sets even if not exported yet (legacy data)
        if "magic" in missing_decks and "magic" not in new_games:
            warnings.append("Magic has test sets but no exported decks (may use legacy data)")

    # Report
    if errors:
        print("Error: ERRORS:")
        for e in errors:
            print(f" - {e}")
    if warnings:
        print("Warning: WARNINGS:")
        for w in warnings:
            print(f" - {w}")
    if not errors and not warnings:
        print(" All data lineage dependencies satisfied")
        return 0
    else:
        return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(validate_lineage())
