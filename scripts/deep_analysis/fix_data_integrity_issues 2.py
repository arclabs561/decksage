#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Fix data integrity issues found in test sets.

Fixes:
- Cards appearing in multiple relevance levels (should be in one level only)
- Duplicate labels within same level
- Invalid label formats
"""

import json
import sys
from pathlib import Path
from typing import Any


# Add src to path
script_dir = Path(__file__).parent
src_dir = script_dir.parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))


def fix_test_set_integrity(test_set_path: Path, output_path: Path | None = None) -> dict[str, Any]:
    """Fix integrity issues in test set."""
    with open(test_set_path) as f:
        data = json.load(f)

    queries = data.get("queries", data)
    if not isinstance(queries, dict):
        return {
            "success": False,
            "error": "Invalid format",
        }

    fixes = []
    stats = {
        "queries_processed": 0,
        "cards_fixed": 0,
        "duplicates_removed": 0,
    }

    # Fix each query
    for query, labels in queries.items():
        if not isinstance(labels, dict):
            continue

        stats["queries_processed"] += 1
        fixed_labels = {}

        # Priority order: highly_relevant > relevant > somewhat_relevant > marginally_relevant > irrelevant
        priority_order = [
            "highly_relevant",
            "relevant",
            "somewhat_relevant",
            "marginally_relevant",
            "irrelevant",
        ]

        # Track all cards seen
        seen_cards = set()

        # Process in priority order
        for level in priority_order:
            level_cards = labels.get(level, [])
            if not isinstance(level_cards, list):
                level_cards = []

            # Remove duplicates within level
            unique_cards = []
            for card in level_cards:
                if card not in unique_cards:
                    unique_cards.append(card)

            if len(unique_cards) != len(level_cards):
                fixes.append(
                    {
                        "type": "duplicate_removed",
                        "query": query,
                        "level": level,
                        "removed": len(level_cards) - len(unique_cards),
                    }
                )
                stats["duplicates_removed"] += len(level_cards) - len(unique_cards)

            # Remove cards already seen in higher priority level
            new_cards = [c for c in unique_cards if c not in seen_cards]
            removed_cards = [c for c in unique_cards if c in seen_cards]

            if removed_cards:
                fixes.append(
                    {
                        "type": "card_moved_to_higher_priority",
                        "query": query,
                        "level": level,
                        "removed_cards": removed_cards,
                    }
                )
                stats["cards_fixed"] += len(removed_cards)

            fixed_labels[level] = new_cards
            seen_cards.update(new_cards)

        queries[query] = fixed_labels

    # Create fixed test set
    fixed_data = {
        "version": data.get("version", "fixed"),
        "description": data.get("description", "") + " (integrity fixes applied)",
        "queries": queries,
    }

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(fixed_data, f, indent=2)

    return {
        "success": True,
        "stats": stats,
        "fixes": fixes,
        "output_path": str(output_path) if output_path else None,
    }


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Fix data integrity issues")
    parser.add_argument(
        "--test-set",
        type=Path,
        required=True,
        help="Test set to fix",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output fixed test set (default: adds _fixed suffix)",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Backup original",
    )

    args = parser.parse_args()

    if not args.test_set.exists():
        print(f"Error: Test set not found: {args.test_set}")
        return 1

    if args.output is None:
        args.output = args.test_set.parent / f"{args.test_set.stem}_fixed.json"

    print(f"Fixing integrity issues in {args.test_set.name}...")
    print()

    # Backup if requested
    if args.backup:
        backup_path = args.test_set.parent / f"{args.test_set.stem}_backup.json"
        import shutil

        shutil.copy2(args.test_set, backup_path)
        print(f"Backed up to: {backup_path}")
        print()

    result = fix_test_set_integrity(args.test_set, args.output)

    if not result["success"]:
        print(f"Error: {result.get('error', 'Unknown error')}")
        return 1

    stats = result["stats"]
    print("Fix Summary")
    print("=" * 70)
    print(f"Queries processed: {stats['queries_processed']}")
    print(f"Cards fixed (moved to higher priority): {stats['cards_fixed']}")
    print(f"Duplicates removed: {stats['duplicates_removed']}")
    print()

    if result["fixes"]:
        print("Top fixes:")
        for fix in result["fixes"][:10]:
            if fix["type"] == "duplicate_removed":
                print(f"  {fix['query']}/{fix['level']}: removed {fix['removed']} duplicates")
            elif fix["type"] == "card_moved_to_higher_priority":
                print(
                    f"  {fix['query']}/{fix['level']}: removed {len(fix['removed_cards'])} cards (already in higher priority)"
                )
        if len(result["fixes"]) > 10:
            print(f"  ... and {len(result['fixes']) - 10} more fixes")

    print(f"\nFixed test set saved to: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
