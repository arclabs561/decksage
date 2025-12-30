#!/usr/bin/env python3
"""
Bootstrap annotations for all games to reach 100+ queries.

Generates LLM-drafted annotations for:
- MTG: 12 more (38 -> 50)
- Pokemon: 15 more (10 -> 25)
- Yu-Gi-Oh: 12 more (13 -> 25)
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.ml.annotation.annotation_bootstrap_llm import main as bootstrap_main


def main() -> int:
    """Bootstrap annotations for all games."""
    games = [
        ("magic", 12),
        ("pokemon", 15),
        ("yugioh", 12),
    ]

    for game, num in games:
        print(f"\n{'=' * 60}")
        print(f"Bootstrapping {num} queries for {game}")
        print(f"{'=' * 60}")

        output = Path(__file__).parent.parent.parent / "annotations" / f"batch_{game}_expansion.yaml"

        # Simulate command line args
        sys.argv = [
            "annotation_bootstrap_llm.py",
            "--game",
            game,
            "--num",
            str(num),
            "--output",
            str(output),
        ]

        result = bootstrap_main()
        if result != 0:
            print(f"⚠️ Failed to bootstrap {game}")
            continue

    print(f"\n{'=' * 60}")
    print("Bootstrap complete!")
    print(f"{'=' * 60}")
    print("\nNext steps:")
    print("1. Review generated YAML files in annotations/")
    print("2. Fill in relevance scores (0-4)")
    print("3. Run: python -m src.ml.annotation.hand_annotate merge")

    return 0


if __name__ == "__main__":
    sys.exit(main())

