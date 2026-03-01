#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.24.0"]
# ///
"""
Propagate annotation labels to nearby nodes via graph structure.

Given ~500 labeled pairs and a co-occurrence graph, generates pseudo-labels
for unlabeled pairs by exploiting graph neighborhood overlap.

Strategy:
  For each labeled pair (A, B) with score s:
    1. Find neighbors of A and B in the co-occurrence graph
    2. For each neighbor C of B (not A), compute Jaccard(neighbors(A), neighbors(C))
    3. If Jaccard > threshold, create pseudo-pair (A, C) with score = s * decay * Jaccard
    4. Similarly propagate from B's side

This multiplies labeled pairs by ~10-50x depending on graph density and thresholds.

Usage:
    python scripts/training/propagate_labels.py \
        --annotations data/annotations/yugioh_500_v3.json \
        --edgelist data/graphs/yugioh_ppmi.edg \
        --output data/graphs/pairs_propagated_yugioh.edg \
        --decay 0.7 --jaccard-threshold 0.15 --max-propagated-per-pair 20
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np


def load_edgelist(path: Path) -> dict[str, dict[str, float]]:
    """Load edgelist into adjacency dict: node -> {neighbor: weight}."""
    adj: dict[str, dict[str, float]] = defaultdict(dict)
    with open(path) as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) < 2:
                continue
            c1, c2 = parts[0].strip(), parts[1].strip()
            w = float(parts[2].strip()) if len(parts) > 2 else 1.0
            adj[c1][c2] = max(adj[c1].get(c2, 0.0), w)
            adj[c2][c1] = max(adj[c2].get(c1, 0.0), w)
    return dict(adj)


def load_annotations(paths: list[Path], min_score: float = 0.20) -> list[tuple[str, str, float]]:
    """Load annotation pairs with consensus scores."""
    pairs = []
    seen = set()
    for path in paths:
        data = json.load(open(path))
        labels = data.get("labels", [])
        for label in labels:
            consensus = label.get("consensus")
            if not consensus:
                continue
            score = consensus.get("similarity_score", 0.0)
            if score < min_score:
                continue
            c1, c2 = label["card1"], label["card2"]
            key = tuple(sorted([c1, c2]))
            if key not in seen:
                seen.add(key)
                pairs.append((c1, c2, score))
    return pairs


def jaccard(set_a: set[str], set_b: set[str]) -> float:
    """Jaccard similarity between two sets."""
    if not set_a or not set_b:
        return 0.0
    inter = len(set_a & set_b)
    union = len(set_a | set_b)
    return inter / union if union > 0 else 0.0


def propagate(
    labeled_pairs: list[tuple[str, str, float]],
    adj: dict[str, dict[str, float]],
    decay: float = 0.7,
    jaccard_threshold: float = 0.15,
    max_per_pair: int = 20,
) -> dict[tuple[str, str], float]:
    """Propagate labels to nearby nodes.

    For each labeled (A, B, score):
      - Find neighbors of B in the graph
      - For each neighbor C (C != A, C != B):
        - If Jaccard(neighbors(A), neighbors(C)) > threshold:
          - Pseudo-label (A, C) with score * decay * Jaccard(A, C)
      - Do the same from B's perspective

    Returns dict of (card1, card2) -> propagated_score.
    """
    propagated: dict[tuple[str, str], float] = {}
    original_keys = {tuple(sorted([a, b])) for a, b, _ in labeled_pairs}

    for a, b, score in labeled_pairs:
        # Propagate from A's perspective: find C ~ B, check A ~ C
        neighbors_a = set(adj.get(a, {}).keys())
        neighbors_b = set(adj.get(b, {}).keys())

        # Candidates: neighbors of B that aren't A or B
        candidates_from_b = neighbors_b - {a, b}

        scored_candidates = []
        for c in candidates_from_b:
            neighbors_c = set(adj.get(c, {}).keys())
            j = jaccard(neighbors_a, neighbors_c)
            if j >= jaccard_threshold:
                pseudo_score = score * decay * j
                scored_candidates.append((c, pseudo_score, j))

        # Keep top-K by score
        scored_candidates.sort(key=lambda x: -x[1])
        for c, pseudo_score, j in scored_candidates[:max_per_pair]:
            key = tuple(sorted([a, c]))
            if key not in original_keys:
                propagated[key] = max(propagated.get(key, 0.0), pseudo_score)

        # Propagate from B's perspective: find C ~ A, check B ~ C
        candidates_from_a = neighbors_a - {a, b}

        scored_candidates = []
        for c in candidates_from_a:
            neighbors_c = set(adj.get(c, {}).keys())
            j = jaccard(neighbors_b, neighbors_c)
            if j >= jaccard_threshold:
                pseudo_score = score * decay * j
                scored_candidates.append((c, pseudo_score, j))

        scored_candidates.sort(key=lambda x: -x[1])
        for c, pseudo_score, j in scored_candidates[:max_per_pair]:
            key = tuple(sorted([b, c]))
            if key not in original_keys:
                propagated[key] = max(propagated.get(key, 0.0), pseudo_score)

    return propagated


def main() -> int:
    parser = argparse.ArgumentParser(description="Propagate annotation labels via graph structure")
    parser.add_argument("--annotations", type=Path, nargs="+", required=True,
                        help="Annotation JSON files")
    parser.add_argument("--edgelist", type=Path, required=True,
                        help="Co-occurrence edgelist for neighborhood lookup")
    parser.add_argument("--output", type=Path, required=True,
                        help="Output edgelist with propagated pseudo-labels")
    parser.add_argument("--decay", type=float, default=0.7,
                        help="Score decay factor per hop (default: 0.7)")
    parser.add_argument("--jaccard-threshold", type=float, default=0.15,
                        help="Min Jaccard similarity for propagation (default: 0.15)")
    parser.add_argument("--max-per-pair", type=int, default=20,
                        help="Max propagated pairs per original pair (default: 20)")
    parser.add_argument("--min-score", type=float, default=0.20,
                        help="Min annotation score to use as seed (default: 0.20)")
    parser.add_argument("--weight-scale", type=float, default=10.0,
                        help="Scale factor for output edge weights (default: 10.0)")
    args = parser.parse_args()

    # Load graph
    print(f"Loading graph from {args.edgelist}...")
    adj = load_edgelist(args.edgelist)
    print(f"  {len(adj)} nodes")

    # Load annotations
    print(f"Loading annotations from {len(args.annotations)} file(s)...")
    labeled = load_annotations(args.annotations, args.min_score)
    print(f"  {len(labeled)} labeled pairs (score >= {args.min_score})")

    # Count how many labeled cards are in graph
    graph_nodes = set(adj.keys())
    labeled_cards = set()
    for a, b, _ in labeled:
        labeled_cards.add(a)
        labeled_cards.add(b)
    in_graph = labeled_cards & graph_nodes
    print(f"  {len(in_graph)}/{len(labeled_cards)} labeled cards found in graph ({100*len(in_graph)/len(labeled_cards):.1f}%)")

    # Propagate
    print(f"Propagating (decay={args.decay}, jaccard>={args.jaccard_threshold}, max_per_pair={args.max_per_pair})...")
    propagated = propagate(labeled, adj, args.decay, args.jaccard_threshold, args.max_per_pair)
    print(f"  Generated {len(propagated)} pseudo-labeled pairs")

    # Merge original + propagated
    merged: dict[tuple[str, str], float] = {}
    for a, b, score in labeled:
        key = tuple(sorted([a, b]))
        merged[key] = max(merged.get(key, 0.0), score * args.weight_scale)
    for key, score in propagated.items():
        weight = score * args.weight_scale
        merged[key] = max(merged.get(key, 0.0), weight)

    # Stats
    orig_count = len(labeled)
    prop_count = len(propagated)
    total = len(merged)
    prop_scores = list(propagated.values()) if propagated else [0]
    print(f"\n  Original: {orig_count} pairs")
    print(f"  Propagated: {prop_count} pairs ({prop_count/max(orig_count,1):.1f}x expansion)")
    print(f"  Total (merged): {total} pairs")
    print(f"  Propagated score stats: mean={np.mean(prop_scores):.3f}, "
          f"median={np.median(prop_scores):.3f}, max={np.max(prop_scores):.3f}")

    # Write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        for (c1, c2), weight in sorted(merged.items()):
            f.write(f"{c1}\t{c2}\t{weight:.4f}\n")

    print(f"\nWritten {total} edges to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
