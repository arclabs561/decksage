#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Extract set co-membership and keyword-sharing edges from Scryfall data.

Creates edges between cards that share:
1. Set membership (cards released in the same expansion/set)
2. Keyword mechanics (cards sharing keyword abilities)
3. Preconstructed deck membership (Commander precons, duel decks, starter decks)

These are "designed synergy" signals -- cards the game designers intended
to work together, distinct from emergent co-occurrence in player-built decks.

Usage:
    uv run scripts/training/extract_set_edges.py --game magic
    uv run scripts/training/extract_set_edges.py --game magic --max-set-size 200
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def load_scryfall_cards() -> list[dict]:
    path = DATA_DIR / "raw" / "scryfall" / "oracle-cards.json"
    if not path.exists():
        print(f"Scryfall oracle cards not found: {path}")
        return []
    with open(path) as f:
        return json.load(f)


def extract_edges(
    cards: list[dict],
    max_set_size: int = 300,
    min_keywords_overlap: int = 2,
) -> dict[str, list[tuple[str, str, float]]]:
    """Extract edges from set membership and keyword sharing.

    Args:
        cards: Scryfall card objects
        max_set_size: Skip sets larger than this (core sets create too many edges)
        min_keywords_overlap: Minimum shared keywords for keyword edges

    Returns:
        Dict of edge_type -> [(card1, card2, weight)]
    """
    # Group cards by set
    sets: dict[str, list[str]] = defaultdict(list)
    # Group cards by keywords
    card_keywords: dict[str, set[str]] = {}

    # Precon set types
    precon_types = {"commander", "duel_deck", "starter", "planechase", "archenemy"}

    for card in cards:
        name = card.get("name", "")
        if not name or "//" in name:  # Skip split cards for simplicity
            continue

        set_name = card.get("set_name", "")
        set_type = card.get("set_type", "")
        keywords = card.get("keywords", [])

        if set_name:
            sets[f"{set_name}|{set_type}"].append(name)

        if keywords:
            card_keywords[name] = set(keywords)

    print(f"Cards processed: {len(card_keywords)} with keywords, {len(sets)} sets")

    edges: dict[str, list[tuple[str, str, float]]] = {
        "set_cooccurrence": [],
        "precon_cooccurrence": [],
        "keyword_sharing": [],
    }

    # Set co-membership edges
    n_set_edges = 0
    n_precon_edges = 0
    for set_key, members in sets.items():
        set_name, set_type = set_key.rsplit("|", 1)

        if len(members) > max_set_size:
            continue  # Skip huge sets (core sets, masters)
        if len(members) < 2:
            continue

        # Deduplicate card names within set
        unique = list(set(members))

        # Weight: smaller sets = stronger signal (precon of 100 cards > expansion of 300)
        weight = 1.0 / max(len(unique) / 50, 1.0)  # Normalize around 50 cards

        edge_type = "precon_cooccurrence" if set_type in precon_types else "set_cooccurrence"

        for i in range(len(unique)):
            for j in range(i + 1, len(unique)):
                edges[edge_type].append((unique[i], unique[j], weight))

        if edge_type == "precon_cooccurrence":
            n_precon_edges += len(unique) * (len(unique) - 1) // 2
        else:
            n_set_edges += len(unique) * (len(unique) - 1) // 2

    print(f"Set edges: {n_set_edges:,}, Precon edges: {n_precon_edges:,}")

    # Keyword sharing edges
    names = list(card_keywords.keys())
    n_keyword_edges = 0
    for i in range(len(names)):
        kw_i = card_keywords[names[i]]
        if len(kw_i) < min_keywords_overlap:
            continue
        for j in range(i + 1, len(names)):
            kw_j = card_keywords[names[j]]
            overlap = len(kw_i & kw_j)
            if overlap >= min_keywords_overlap:
                weight = overlap / max(len(kw_i | kw_j), 1)  # Jaccard
                edges["keyword_sharing"].append((names[i], names[j], weight))
                n_keyword_edges += 1

    print(f"Keyword sharing edges: {n_keyword_edges:,}")

    return edges


def save_edges(edges: dict[str, list[tuple[str, str, float]]], game: str) -> None:
    """Save edges as edgelist files."""
    out_dir = DATA_DIR / "graphs"
    out_dir.mkdir(parents=True, exist_ok=True)

    for edge_type, edge_list in edges.items():
        if not edge_list:
            continue
        path = out_dir / f"{game}_{edge_type}.edg"
        with open(path, "w") as f:
            for c1, c2, w in edge_list:
                f.write(f"{c1}\t{c2}\t{w:.4f}\n")
        print(f"Saved {len(edge_list):,} {edge_type} edges to {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract set/keyword edges")
    parser.add_argument("--game", default="magic")
    parser.add_argument("--max-set-size", type=int, default=300)
    parser.add_argument("--min-keywords", type=int, default=2)
    args = parser.parse_args()

    if args.game != "magic":
        print(f"Currently only supports magic (Scryfall data). Got: {args.game}")
        return 1

    cards = load_scryfall_cards()
    if not cards:
        return 1

    print(f"Loaded {len(cards)} Scryfall cards")

    edges = extract_edges(
        cards,
        max_set_size=args.max_set_size,
        min_keywords_overlap=args.min_keywords,
    )

    save_edges(edges, args.game)

    total = sum(len(e) for e in edges.values())
    print(f"\nTotal: {total:,} edges across {len([e for e in edges.values() if e])} edge types")
    return 0


if __name__ == "__main__":
    sys.exit(main())
