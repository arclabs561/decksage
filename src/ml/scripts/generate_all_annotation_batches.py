#!/usr/bin/env python3
"""
Generate annotation batches for all games to expand test sets.

Targets:
- MTG: 50 queries (currently 38, need 12 more)
- Pokemon: 25 queries (currently 10, need 15 more)
- Yu-Gi-Oh: 25 queries (currently 13, need 12 more)

Total: 100 queries (currently 61, need 39 more)
"""

from __future__ import annotations

import json
from pathlib import Path

from ..annotation.hand_annotate import create_annotation_batch
from ..utils.paths import PATHS


def main():
    """Generate annotation batches for all games"""

    # Game configurations
    games = {
        "magic": {
            "target": 50,
            "current": 38,
            "test_set": PATHS.test_magic,
            "pairs": PATHS.pairs_large if PATHS.pairs_large.exists() else PATHS.pairs_500,
        },
        "pokemon": {
            "target": 25,
            "current": 10,
            "test_set": PATHS.test_pokemon,
            "pairs": PATHS.pairs_large if PATHS.pairs_large.exists() else PATHS.pairs_500,
        },
        "yugioh": {
            "target": 25,
            "current": 13,
            "test_set": PATHS.test_yugioh,
            "pairs": PATHS.pairs_large if PATHS.pairs_large.exists() else PATHS.pairs_500,
        },
    }

    print("=" * 60)
    print("  Hand Annotation Batch Generator")
    print("=" * 60)
    print()

    # Load current test sets and count queries
    for game, config in games.items():
        test_set_path = config["test_set"]
        if test_set_path.exists():
            with open(test_set_path) as f:
                test_set = json.load(f)
            # Handle both formats
            queries = test_set.get("queries", test_set)
            actual_current = len(queries)
            config["current"] = actual_current
            config["existing_test_set"] = test_set
        else:
            config["existing_test_set"] = None
            print(f"⚠️  Test set not found: {test_set_path}")

    # Generate batches
    output_dir = Path("annotations")
    output_dir.mkdir(exist_ok=True)

    for game, config in games.items():
        n_new = config["target"] - config["current"]
        if n_new <= 0:
            print(f"✓ {game.upper()}: Already has {config['current']} queries (target: {config['target']})")
            continue

        print(f"\n📋 Generating batch for {game.upper()}:")
        print(f"   Current: {config['current']} queries")
        print(f"   Target: {config['target']} queries")
        print(f"   Need: {n_new} new queries")

        if not config["pairs"].exists():
            print(f"   ❌ Pairs CSV not found: {config['pairs']}")
            continue

        output_file = output_dir / f"hand_batch_{game}_expansion.yaml"

        try:
            create_annotation_batch(
                game=game,
                target_queries=config["target"],
                current_queries=config["current"],
                pairs_csv=config["pairs"],
                embeddings_path=None,  # Can add later if embeddings available
                output_path=output_file,
                existing_test_set=config.get("existing_test_set"),
                seed=42,
            )
        except Exception as e:
            print(f"   ❌ Error: {e}")
            import traceback

            traceback.print_exc()

    print("\n" + "=" * 60)
    print("  Summary")
    print("=" * 60)
    total_current = sum(c["current"] for c in games.values())
    total_target = sum(c["target"] for c in games.values())
    total_needed = total_target - total_current

    print(f"Total queries: {total_current} → {total_target} (need {total_needed} more)")
    print(f"\nNext steps:")
    print(f"1. Review and annotate batches in annotations/")
    print(f"2. Grade annotations: python -m ml.annotation.hand_annotate grade --input <file>")
    print(f"3. Merge to test sets: python -m ml.annotation.hand_annotate merge --input <file> --test-set <test_set.json>")


if __name__ == "__main__":
    main()

