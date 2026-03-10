#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Build per-card deck frequency index from deck JSONL files.

For each game, reads all data/decks/decks_{game}_*.jsonl files and counts
how many decks each card appears in (by name, deduplicated per deck).

Output: data/processed/deck_frequency_{game}.json
  {
    "Lightning Bolt": {"total_decks": 12847, "by_format": {"modern": 8320, "legacy": 4527}},
    ...
  }

Usage:
  uv run scripts/data_processing/build_deck_frequency.py [--games magic,pokemon,yugioh]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DECKS_DIR = REPO_ROOT / "data" / "decks"
OUTPUT_DIR = REPO_ROOT / "data" / "processed"

DEFAULT_GAMES = ["magic", "pokemon", "yugioh"]


def build_frequency(game: str) -> dict[str, dict]:
    """Count per-card deck appearances across all deck files for a game."""
    pattern = f"decks_{game}*.jsonl"
    deck_files = sorted(DECKS_DIR.glob(pattern))

    if not deck_files:
        print(f"  No deck files found for {game} (pattern: {pattern})", file=sys.stderr)
        return {}

    total_count: Counter[str] = Counter()
    format_count: dict[str, Counter[str]] = defaultdict(Counter)
    total_decks = 0

    for path in deck_files:
        print(f"  Reading {path.name}...", end="", flush=True)
        file_decks = 0
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    deck = json.loads(line)
                except json.JSONDecodeError:
                    continue

                cards = deck.get("cards", [])
                if not cards:
                    continue

                # Deduplicate card names within this deck
                card_names = {c["name"] for c in cards if isinstance(c, dict) and "name" in c}
                if not card_names:
                    continue

                fmt = deck.get("format", "unknown") or "unknown"
                fmt = fmt.strip().lower()

                for name in card_names:
                    total_count[name] += 1
                    format_count[fmt][name] += 1

                file_decks += 1

        total_decks += file_decks
        print(f" {file_decks:,} decks")

    print(f"  Total: {total_decks:,} decks, {len(total_count):,} unique cards")

    # Build output
    result = {}
    for card_name, total in total_count.most_common():
        by_format = {}
        for fmt, counter in sorted(format_count.items()):
            count = counter.get(card_name, 0)
            if count > 0:
                by_format[fmt] = count
        result[card_name] = {"total_decks": total, "by_format": by_format}

    return result


def main():
    parser = argparse.ArgumentParser(description="Build deck frequency index")
    parser.add_argument(
        "--games",
        default=",".join(DEFAULT_GAMES),
        help="Comma-separated game names (default: magic,pokemon,yugioh)",
    )
    args = parser.parse_args()
    games = [g.strip().lower() for g in args.games.split(",") if g.strip()]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for game in games:
        print(f"\n=== {game} ===")
        freq = build_frequency(game)
        if not freq:
            continue

        out_path = OUTPUT_DIR / f"deck_frequency_{game}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(freq, f, ensure_ascii=False)
        print(f"  Wrote {out_path} ({len(freq):,} cards)")


if __name__ == "__main__":
    main()
