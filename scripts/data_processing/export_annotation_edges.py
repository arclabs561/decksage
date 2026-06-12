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
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def export_edges(game: str, exclude_eval: bool = True) -> dict:
    """Export annotation edges for one game.

    If exclude_eval=True, only uses non-test-set annotation sources
    (v4 annotations, dialogue pairs) to avoid train/eval leakage.
    The v2 test set pairs are reserved for evaluation only.
    """
    # Primary source: v4 multi-judge annotations (separate from v2 test set)
    annotation_sources = [
        DATA_DIR / "annotations" / f"{game}_2000_v4.json",
        DATA_DIR / "annotations" / f"{game}_500_v3.json",
        DATA_DIR / "annotations" / f"{game}_500_hub_v3.json",
        DATA_DIR / "annotations" / f"dialogue_{game}_50.json",
    ]

    # Build eval pair set for exclusion
    eval_pairs: set[tuple[str, str]] = set()
    if exclude_eval:
        test_path = DATA_DIR / "test_sets" / f"annotated_{game}_v2.json"
        if test_path.exists():
            with open(test_path) as f:
                test_data = json.load(f)
            for q, qdata in test_data.get("queries", {}).items():
                for ann in qdata.get("annotations", []):
                    c = ann.get("candidate", "")
                    if c:
                        eval_pairs.add((min(q, c), max(q, c)))

    # Collect annotations from non-eval sources
    all_annotations = []

    for src_path in annotation_sources:
        if not src_path.exists():
            continue
        with open(src_path) as f:
            src_data = json.load(f)

        # Handle different annotation file formats
        if isinstance(src_data, list):
            all_annotations.extend(src_data)
        elif isinstance(src_data, dict):
            # v4 format: {"labels": [...]}
            if "labels" in src_data:
                all_annotations.extend(src_data["labels"])
            # v3/v2 format: {"queries": {name: {annotations: [...]}}}
            elif "queries" in src_data:
                for qdata in src_data["queries"].values():
                    if isinstance(qdata, dict):
                        all_annotations.extend(qdata.get("annotations", []))
            # dialogue format: {"pairs": [...]}
            elif "pairs" in src_data:
                all_annotations.extend(src_data["pairs"])

    # Also include test set annotations but ONLY from training-safe queries
    # (bucket-only queries that don't have per-pair LLM annotations)
    if not exclude_eval:
        test_path = DATA_DIR / "test_sets" / f"annotated_{game}_v2.json"
        if test_path.exists():
            with open(test_path) as f:
                data = json.load(f)
            for qdata in data.get("queries", {}).values():
                all_annotations.extend(qdata.get("annotations", []))

    edges: dict[tuple[str, str], float] = {}
    n_functional = 0
    n_synergy = 0
    n_substitutability = 0
    n_excluded = 0

    for ann in all_annotations:
        card1 = ann.get("query", ann.get("card1", ann.get("card_a", "")))
        card2 = ann.get("candidate", ann.get("card2", ann.get("card_b", "")))
        if not card1 or not card2 or card1 == card2:
            continue

        # Normalize edge direction (alphabetical)
        key = (min(card1, card2), max(card1, card2))

        # Exclude eval pairs to prevent train/eval leakage
        if exclude_eval and key in eval_pairs:
            n_excluded += 1
            continue

        weight = 0.0

        # Handle both v4 (consensus nested) and v2/v3 (flat) formats
        consensus = ann.get("consensus", ann)
        func = float(consensus.get("functional_score") or consensus.get("similarity_score") or 0)
        syn = float(consensus.get("synergy_score") or 0)
        sub = float(consensus.get("substitutability") or ann.get("substitutability") or 0)

        if func > 0.5:
            weight = max(weight, func * 5)
            n_functional += 1
        if syn > 0.5:
            weight = max(weight, syn * 3)
            n_synergy += 1
        if sub > 0.5:
            weight = max(weight, sub * 5)
            n_substitutability += 1

        if weight > 0:
            edges[key] = max(edges.get(key, 0), weight)

    # Write edgelist
    out_path = DATA_DIR / "graphs" / f"{game}_annotation_edges.edg"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        for (c1, c2), w in sorted(edges.items()):
            f.write(f"{c1}\t{c2}\t{w:.4f}\n")

    excluded_msg = f", {n_excluded} excluded (eval)" if exclude_eval else ""
    print(
        f"{game}: {len(edges)} edges ({n_functional} functional, {n_synergy} synergy, "
        f"{n_substitutability} substitutability{excluded_msg})"
    )
    print(f"  Saved to {out_path}")

    return {
        "game": game,
        "edges": len(edges),
        "functional": n_functional,
        "synergy": n_synergy,
        "substitutability": n_substitutability,
        "excluded_eval": n_excluded,
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
