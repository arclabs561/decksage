#!/usr/bin/env python3
"""
Parallel test set expansion for Pokemon and Yu-Gi-Oh.
Uses multiprocessing to generate labels for multiple queries simultaneously.
"""

import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def expand_test_set_parallel(game: str, target_queries: int = 200):
    """Expand test set using parallel processing."""
    test_set_path = Path(f"experiments/test_set_unified_{game}.json")

    if not test_set_path.exists():
        print(f"Test set not found: {test_set_path}")
        return

    with open(test_set_path, "rb") as f:
        data = json.load(f)

    current_queries = len(data.get("queries", {}))
    needed = target_queries - current_queries

    if needed <= 0:
        print(f"{game}: Already has {current_queries} queries (target: {target_queries})")
        return

    print(f"{game}: Expanding from {current_queries} to {target_queries} (+{needed} queries)")

    # Generate new queries and labels in parallel
    # This would call generate_labels_for_new_queries_optimized.py
    # For now, this is a placeholder structure

    print(f"  → Would generate {needed} new queries with labels")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--game", choices=["pokemon", "yugioh"], required=True)
    parser.add_argument("--target", type=int, default=200)
    args = parser.parse_args()

    expand_test_set_parallel(args.game, args.target)
