#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
PPMI (Pointwise Mutual Information) graph sparsification.

Reweights co-occurrence edges by PMI, removing popularity-driven noise.
PPMI(i,j) = max(0, log2(p(i,j) / (p(i) * p(j))))

High PPMI means the co-occurrence is significantly more than expected by chance.
This removes edges between cards that co-occur only because both are popular.

Usage:
    PYTHONPATH=src .venv/bin/python scripts/data_processing/ppmi_sparsify.py \
        --edgelist data/graphs/yugioh_blended.edg \
        --output data/graphs/yugioh_ppmi.edg \
        --threshold 1.0 --top-k 20
"""
from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="PPMI graph sparsification")
    parser.add_argument("--edgelist", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=0.0,
                        help="Minimum PPMI to keep edge (default: 0.0, keep all positive)")
    parser.add_argument("--top-k", type=int, default=0,
                        help="Keep only top-K PPMI neighbors per node (0=no limit)")
    parser.add_argument("--keep-weight", choices=["ppmi", "original", "ppmi_scaled"],
                        default="ppmi_scaled",
                        help="Edge weight in output: ppmi, original, or ppmi*original")
    args = parser.parse_args()

    # Load edgelist
    print(f"Loading {args.edgelist}...")
    edges: list[tuple[str, str, float]] = []
    node_degree: dict[str, float] = defaultdict(float)
    total_weight = 0.0

    with open(args.edgelist) as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) < 2:
                continue
            n1, n2 = parts[0], parts[1]
            w = float(parts[2]) if len(parts) > 2 else 1.0
            edges.append((n1, n2, w))
            node_degree[n1] += w
            node_degree[n2] += w
            total_weight += w

    num_nodes = len(node_degree)
    print(f"  {num_nodes} nodes, {len(edges)} edges, total_weight={total_weight:.0f}")

    # Compute PPMI for each edge
    print("Computing PPMI...")
    ppmi_edges: list[tuple[str, str, float, float]] = []  # (n1, n2, ppmi, orig_weight)

    for n1, n2, w in edges:
        # p(i,j) = w / total_weight
        # p(i) = degree(i) / (2 * total_weight)  [each edge contributes to both endpoints]
        # p(j) = degree(j) / (2 * total_weight)
        # PMI = log2(p(i,j) / (p(i) * p(j)))
        #     = log2(w * (2 * total_weight) / (degree(i) * degree(j)))
        p_ij = w / total_weight
        p_i = node_degree[n1] / (2 * total_weight)
        p_j = node_degree[n2] / (2 * total_weight)

        if p_i == 0 or p_j == 0:
            continue

        pmi = math.log2(p_ij / (p_i * p_j))
        ppmi = max(0.0, pmi)

        if ppmi >= args.threshold:
            ppmi_edges.append((n1, n2, ppmi, w))

    print(f"  {len(ppmi_edges)} edges with PPMI >= {args.threshold}")

    # Top-K filtering per node
    if args.top_k > 0:
        print(f"  Filtering to top-{args.top_k} PPMI neighbors per node...")
        # Build neighbor lists
        node_neighbors: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
        for n1, n2, ppmi, w in ppmi_edges:
            node_neighbors[n1].append((n2, ppmi, w))
            node_neighbors[n2].append((n1, ppmi, w))

        # Keep top-k per node
        kept_pairs: set[tuple[str, str]] = set()
        for node in node_neighbors:
            neighbors = sorted(node_neighbors[node], key=lambda x: -x[1])
            for nb, ppmi, w in neighbors[:args.top_k]:
                pair = tuple(sorted([node, nb]))
                kept_pairs.add(pair)

        ppmi_edges = [
            (n1, n2, ppmi, w) for n1, n2, ppmi, w in ppmi_edges
            if tuple(sorted([n1, n2])) in kept_pairs
        ]
        print(f"  After top-{args.top_k}: {len(ppmi_edges)} edges")

    # Determine output weight
    output_edges: list[tuple[str, str, float]] = []
    for n1, n2, ppmi, w in ppmi_edges:
        if args.keep_weight == "ppmi":
            out_w = ppmi
        elif args.keep_weight == "original":
            out_w = w
        else:  # ppmi_scaled
            out_w = ppmi * w
        output_edges.append((n1, n2, out_w))

    # Stats
    nodes_out = set()
    for n1, n2, _ in output_edges:
        nodes_out.add(n1)
        nodes_out.add(n2)

    ppmi_values = [e[2] for e in ppmi_edges]
    if ppmi_values:
        import statistics
        print(f"\nPPMI stats: mean={statistics.mean(ppmi_values):.3f}, "
              f"median={statistics.median(ppmi_values):.3f}, "
              f"max={max(ppmi_values):.3f}")

    print(f"\nOutput: {len(nodes_out)} nodes, {len(output_edges)} edges")
    print(f"  Sparsification ratio: {len(output_edges)/len(edges)*100:.1f}% of original")

    # Write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        for n1, n2, w in output_edges:
            f.write(f"{n1}\t{n2}\t{w:.6f}\n")

    print(f"Written to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
