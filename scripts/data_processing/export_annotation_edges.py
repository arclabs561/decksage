#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Export high-confidence annotation pairs as graph edges.

Reads annotated test sets and exports pairs with high similarity scores
as edgelist entries that can be fed into the unified graph builder.
This closes the loop: annotations improve the graph, which improves
embeddings, which produce better candidates for annotation.

Edge weight is derived from annotation scores:
- functional_score > 0.5 -> weight = functional_score * 5
- synergy_score > 0.5 -> weight = synergy_score * 3
- substitutability > 0.5 -> weight = substitutability * 5

Output: edgelist file compatible with build_unified_graph.py

Usage:
    uv run scripts/data_processing/export_annotation_edges.py --game magic
    uv run scripts/data_processing/export_annotation_edges.py --all-games
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def export_edges(game: str) -> dict:
    """Export annotation edges for one game."""
    test_path = DATA_DIR / "test_sets" / f"annotated_{game}_v2.json"
    if not test_path.exists():
        return {"game": game, "error": "no test set"}

    with open(test_path) as f:
        data = json.load(f)

    edges: dict[tuple[str, str], float] = {}
    n_functional = 0
    n_synergy = 0
    n_substitutability = 0

    for qdata in data.get("queries", {}).values():
        for ann in qdata.get("annotations", []):
            card1 = ann.get("query", "")
            card2 = ann.get("candidate", "")
            if not card1 or not card2 or card1 == card2:
                continue

            # Normalize edge direction (alphabetical)
            key = (min(card1, card2), max(card1, card2))
            weight = 0.0

            func = ann.get("functional_score") or 0
            syn = ann.get("synergy_score") or 0
            sub = ann.get("substitutability") or 0

            if float(func) > 0.5:
                weight = max(weight, float(func) * 5)
                n_functional += 1
            if float(syn) > 0.5:
                weight = max(weight, float(syn) * 3)
                n_synergy += 1
            if float(sub) > 0.5:
                weight = max(weight, float(sub) * 5)
                n_substitutability += 1

            if weight > 0:
                edges[key] = max(edges.get(key, 0), weight)

    # Write edgelist
    out_path = DATA_DIR / "graphs" / f"{game}_annotation_edges.edg"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        for (c1, c2), w in sorted(edges.items()):
            f.write(f"{c1}\t{c2}\t{w:.4f}\n")

    print(
        f"{game}: {len(edges)} edges ({n_functional} functional, {n_synergy} synergy, {n_substitutability} substitutability)"
    )
    print(f"  Saved to {out_path}")

    return {
        "game": game,
        "edges": len(edges),
        "functional": n_functional,
        "synergy": n_synergy,
        "substitutability": n_substitutability,
        "path": str(out_path),
    }


def main():
    parser = argparse.ArgumentParser(description="Export annotation edges")
    parser.add_argument("--game", default="magic", choices=["magic", "pokemon", "yugioh"])
    parser.add_argument("--all-games", action="store_true")
    args = parser.parse_args()

    games = ["magic", "pokemon", "yugioh"] if args.all_games else [args.game]
    for game in games:
        result = export_edges(game)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
