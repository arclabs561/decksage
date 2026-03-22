#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Build per-format co-occurrence edge lists from deck JSONL files.

Splits deck data by format (Standard, Modern, Commander, etc.) and
generates separate edgelists for each. Enables per-format Cleora
embeddings that capture format-specific substitution signal.

Usage:
    uv run scripts/training/build_format_edges.py --game magic
    uv run scripts/training/build_format_edges.py --game magic --min-cooccurrence 3
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

if not sys.stdout.isatty():
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

BASICS = {
    "Plains", "Island", "Swamp", "Mountain", "Forest",
    "Snow-Covered Plains", "Snow-Covered Island", "Snow-Covered Swamp",
    "Snow-Covered Mountain", "Snow-Covered Forest", "Wastes",
}


def extract_cards(deck: dict) -> set[str]:
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
    return cards - BASICS


def main() -> int:
    parser = argparse.ArgumentParser(description="Build per-format edge lists")
    parser.add_argument("--game", default="magic")
    parser.add_argument("--min-cooccurrence", type=int, default=2)
    parser.add_argument("--min-cards", type=int, default=10)
    args = parser.parse_args()

    deck_dir = DATA_DIR / "decks"
    graph_dir = DATA_DIR / "graphs"
    graph_dir.mkdir(parents=True, exist_ok=True)

    print(f"Building per-format edges for {args.game}")
    t0 = time.monotonic()

    # Load all decks with format labels
    format_decks: dict[str, list[set[str]]] = defaultdict(list)
    n_total = 0
    n_no_format = 0

    for f in sorted(deck_dir.glob(f"decks_{args.game}_*.jsonl")):
        print(f"  Loading {f.name}...")
        with open(f) as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    deck = json.loads(line)
                except json.JSONDecodeError:
                    continue

                cards = extract_cards(deck)
                if len(cards) < args.min_cards:
                    continue

                fmt = deck.get("format", "").lower().strip()
                if not fmt or fmt == "unknown":
                    n_no_format += 1
                    continue

                format_decks[fmt].append(cards)
                n_total += 1

    print(f"\n  {n_total:,} decks with format labels, {n_no_format:,} without")
    print(f"  Formats: {', '.join(f'{k} ({len(v):,})' for k, v in sorted(format_decks.items(), key=lambda x: -len(x[1])))}")

    # Build edges per format
    for fmt, decks in sorted(format_decks.items(), key=lambda x: -len(x[1])):
        if len(decks) < 50:
            print(f"\n  Skipping {fmt} ({len(decks)} decks < 50 minimum)")
            continue

        print(f"\n  === {fmt} ({len(decks):,} decks) ===")
        pair_counts: dict[tuple[str, str], int] = defaultdict(int)

        for cards in decks:
            card_list = sorted(cards)
            for i, a in enumerate(card_list):
                for b in card_list[i + 1:]:
                    pair_counts[(a, b)] += 1

        # Filter and write
        out_path = graph_dir / f"{args.game}_{fmt}_cooccurrence.edg"
        n_edges = 0
        with open(out_path, "w") as f:
            for (a, b), count in sorted(pair_counts.items()):
                if count >= args.min_cooccurrence:
                    f.write(f"{a}\t{b}\t{count}\n")
                    n_edges += 1

        print(f"  {n_edges:,} edges (from {len(pair_counts):,} pairs)")
        print(f"  -> {out_path}")

    elapsed = time.monotonic() - t0
    print(f"\nDone in {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    import traceback
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
