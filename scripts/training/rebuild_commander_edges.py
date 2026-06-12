#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.24.0"]
# ///
"""
Rebuild commander co-occurrence edges from Archidekt deck JSONL.

Faster than running full build_unified_graph.py -- just produces the
{game}_archidekt_commander.edg file from deck data.

Usage:
    uv run scripts/training/rebuild_commander_edges.py --game magic
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path


if not sys.stdout.isatty():
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild commander co-occurrence edges")
    parser.add_argument("--game", default="magic")
    parser.add_argument(
        "--min-cooccurrence",
        type=int,
        default=2,
        help="Minimum deck co-occurrence count to emit edge",
    )
    args = parser.parse_args()

    deck_dir = DATA_DIR / "decks"
    patterns = [f"decks_{args.game}_archidekt*.jsonl", f"decks_{args.game}_commander*.jsonl"]

    print(f"Rebuilding commander edges for {args.game}")
    t0 = time.monotonic()

    # Count co-occurrences
    pair_counts: dict[tuple[str, str], int] = defaultdict(int)
    n_decks = 0
    n_cards_total = 0

    for pattern in patterns:
        for f in sorted(deck_dir.glob(pattern)):
            print(f"  Loading {f.name}...")
            with open(f) as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    try:
                        deck = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    # Extract card names
                    cards = set()
                    if "cards" in deck:
                        for card in deck["cards"]:
                            name = card.get("name", "") if isinstance(card, dict) else str(card)
                            if name:
                                cards.add(name)
                    if "partitions" in deck:
                        for part in deck["partitions"]:
                            for card in part.get("cards", []):
                                name = card.get("name", "") if isinstance(card, dict) else str(card)
                                if name:
                                    cards.add(name)

                    if len(cards) < 10:
                        continue

                    # Skip basic lands
                    basics = {
                        "Plains",
                        "Island",
                        "Swamp",
                        "Mountain",
                        "Forest",
                        "Snow-Covered Plains",
                        "Snow-Covered Island",
                        "Snow-Covered Swamp",
                        "Snow-Covered Mountain",
                        "Snow-Covered Forest",
                        "Wastes",
                    }
                    cards -= basics

                    n_decks += 1
                    n_cards_total += len(cards)

                    # Count all pairs
                    card_list = sorted(cards)
                    for i, a in enumerate(card_list):
                        for b in card_list[i + 1 :]:
                            pair_counts[(a, b)] += 1

    print(
        f"  {n_decks:,} decks, {n_cards_total:,} card-instances, {len(pair_counts):,} unique pairs"
    )

    # Filter by min co-occurrence and write
    out_path = DATA_DIR / "graphs" / f"{args.game}_archidekt_commander.edg"
    n_edges = 0
    with open(out_path, "w") as f:
        for (a, b), count in sorted(pair_counts.items()):
            if count >= args.min_cooccurrence:
                f.write(f"{a}\t{b}\t{count}\n")
                n_edges += 1

    elapsed = time.monotonic() - t0
    print(f"  Wrote {n_edges:,} edges to {out_path} ({elapsed:.1f}s)")
    print(
        f"  (filtered from {len(pair_counts):,} pairs at min_cooccurrence={args.min_cooccurrence})"
    )

    return 0


if __name__ == "__main__":
    import traceback

    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
