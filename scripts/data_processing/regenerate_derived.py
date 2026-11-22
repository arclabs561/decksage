#!/usr/bin/env python3
"""Regenerate card pairs and unlabeled query sets from locally exported decks."""

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STAGES = {
    2: ROOT / "scripts/data_processing/generate_pairs_for_games.py",
    5: ROOT / "scripts/test_sets/create_test_sets_for_new_games.py",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    stages = parser.add_mutually_exclusive_group(required=True)
    stages.add_argument("--all", action="store_true", help="Generate pairs and query sets")
    stages.add_argument("--order", type=int, choices=STAGES)
    parser.add_argument("--game", default="all")
    args = parser.parse_args()
    if args.all and args.game not in {"all", "digimon", "onepiece", "riftbound"}:
        parser.error("query generation supports digimon, onepiece and riftbound")
    for order in STAGES if args.all else [args.order]:
        subprocess.run(
            [sys.executable, str(STAGES[order]), "--game", args.game], cwd=ROOT, check=True
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
