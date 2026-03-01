#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Convert LLM annotation data into training edgelists.

Reads finalized annotation JSON files and produces tab-separated edgelists
suitable for train_blended_embeddings.py. Pairs with high similarity get
high edge weights; low-similarity pairs are excluded (they'd add noise).

Also converts card set data (hyperedges) into pairwise edgelists.

Pipeline position: Order 2 (generated from annotations, feeds into training)

Usage:
    # Annotations -> edgelist
    python scripts/training/annotations_to_edgelist.py \
        --annotations data/annotations/yugioh_500_v3.json \
        --output data/graphs/pairs_annotation_yugioh.edg \
        --min-score 0.20

    # Card sets -> edgelist
    python scripts/training/annotations_to_edgelist.py \
        --card-sets data/processed/card_sets_yugioh_top.jsonl \
        --output data/graphs/pairs_cardsets_yugioh.edg

    # Both at once (merged)
    python scripts/training/annotations_to_edgelist.py \
        --annotations data/annotations/yugioh_500_v3.json \
        --card-sets data/processed/card_sets_yugioh_top.jsonl \
        --output data/graphs/pairs_enriched_yugioh.edg
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path


def annotations_to_edges(
    annotation_paths: list[Path],
    min_score: float = 0.20,
    weight_scale: float = 10.0,
) -> dict[tuple[str, str], float]:
    """Convert annotation pairs to weighted edges.

    Weight = similarity_score * weight_scale for pairs above min_score.
    Pairs below min_score are excluded (they'd dilute signal).
    Deduplicates across multiple annotation files, keeping max score.
    """
    edges: dict[tuple[str, str], float] = {}

    for path in annotation_paths:
        labels = _load_annotation_labels(path)
        for label in labels:
            consensus = label.get("consensus")
            if not consensus:
                continue
            score = consensus["similarity_score"]
            if score < min_score:
                continue

            c1, c2 = label["card1"], label["card2"]
            key = tuple(sorted([c1, c2]))
            weight = score * weight_scale

            # Keep max weight if duplicate
            if key not in edges or weight > edges[key]:
                edges[key] = weight

    return edges


def _load_annotation_labels(path: Path) -> list[dict]:
    """Load annotation labels from JSON (batch output) or JSONL (checkpoint)."""
    with open(path) as f:
        first = f.read(1)

    if not first:
        return []

    if path.suffix == ".jsonl" or first != "{":
        # JSONL format (one label per line)
        labels = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    labels.append(json.loads(line))
        return labels
    else:
        # JSON format (batch output with "labels" array)
        with open(path) as f:
            data = json.load(f)
        return data.get("labels", [])


def card_sets_to_edges(
    card_set_paths: list[Path],
    min_lift: float = 5.0,
    min_support: int = 5,
    weight_scale: float = 1.0,
) -> dict[tuple[str, str], float]:
    """Convert card sets to pairwise edges.

    Each card set generates all-pairs edges.
    Weight = log2(lift) * weight_scale, capped to avoid outliers.
    """
    import math

    edges: dict[tuple[str, str], float] = defaultdict(float)

    for path in card_set_paths:
        with open(path) as f:
            for line in f:
                data = json.loads(line)
                if data.get("_meta"):
                    continue

                lift = data.get("lift", 0)
                support = data.get("support", 0)

                if lift < min_lift or support < min_support:
                    continue

                cards = data["cards"]
                # Weight: log2(lift) to compress the huge range, cap at 15
                w = min(math.log2(max(lift, 1)), 15) * weight_scale

                for c1, c2 in combinations(cards, 2):
                    key = tuple(sorted([c1, c2]))
                    # Accumulate: more sets containing this pair = stronger signal
                    edges[key] += w

    return dict(edges)


def write_edgelist(edges: dict[tuple[str, str], float], output: Path):
    """Write tab-separated edgelist."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        for (c1, c2), weight in sorted(edges.items()):
            f.write(f"{c1}\t{c2}\t{weight:.4f}\n")


def main():
    parser = argparse.ArgumentParser(description="Convert annotations/card-sets to training edgelists")
    parser.add_argument("--annotations", type=Path, nargs="*", default=[],
                        help="Finalized annotation JSON files")
    parser.add_argument("--card-sets", type=Path, nargs="*", default=[],
                        help="Card set JSONL files")
    parser.add_argument("--output", type=Path, required=True,
                        help="Output .edg file")
    parser.add_argument("--min-score", type=float, default=0.20,
                        help="Min annotation similarity score to include (default: 0.20)")
    parser.add_argument("--annotation-weight", type=float, default=10.0,
                        help="Weight multiplier for annotation edges (default: 10.0)")
    parser.add_argument("--card-set-weight", type=float, default=1.0,
                        help="Weight multiplier for card set edges (default: 1.0)")
    parser.add_argument("--min-lift", type=float, default=5.0,
                        help="Min lift for card set edges (default: 5.0)")
    args = parser.parse_args()

    if not args.annotations and not args.card_sets:
        print("Error: provide --annotations and/or --card-sets", file=sys.stderr)
        sys.exit(1)

    all_edges: dict[tuple[str, str], float] = {}

    # Process annotations
    if args.annotations:
        valid = [p for p in args.annotations if p.exists()]
        if not valid:
            print(f"Warning: no annotation files found", file=sys.stderr)
        else:
            ann_edges = annotations_to_edges(valid, args.min_score, args.annotation_weight)
            print(f"Annotations: {len(ann_edges)} edges from {len(valid)} files (min_score={args.min_score})")

            # Score distribution of kept edges
            if ann_edges:
                weights = list(ann_edges.values())
                print(f"  Weight range: [{min(weights):.2f}, {max(weights):.2f}]")

            for key, w in ann_edges.items():
                all_edges[key] = all_edges.get(key, 0) + w

    # Process card sets
    if args.card_sets:
        valid = [p for p in args.card_sets if p.exists()]
        if not valid:
            print(f"Warning: no card set files found", file=sys.stderr)
        else:
            cs_edges = card_sets_to_edges(valid, args.min_lift, weight_scale=args.card_set_weight)
            print(f"Card sets: {len(cs_edges)} edges from {len(valid)} files (min_lift={args.min_lift})")

            if cs_edges:
                weights = list(cs_edges.values())
                print(f"  Weight range: [{min(weights):.2f}, {max(weights):.2f}]")

            for key, w in cs_edges.items():
                all_edges[key] = all_edges.get(key, 0) + w

    # Merge and write
    print(f"\nTotal edges: {len(all_edges)}")
    write_edgelist(all_edges, args.output)
    print(f"Written to {args.output}")


if __name__ == "__main__":
    main()
