#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pecanpy>=2.0.0",
#   "gensim>=4.3.0",
#   "numpy<2.0.0",
# ]
# ///
"""
Train blended co-occurrence embeddings from multiple edgelist sources.

Merges edges from deck and pack (or any number of) edgelists with configurable
weights, then trains PecanPy (Node2Vec) on the merged graph.

Usage:
    uv run scripts/training/train_blended_embeddings.py \
        --edgelist data/graphs/pairs_large.edg --weight 1.0 \
        --edgelist data/graphs/magic_packs.edg --weight 0.5 \
        --output data/embeddings/blended.wv

Edge merge rule: if a card pair (A, B) appears in multiple edgelists,
the merged weight is sum(count_i * weight_i).
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from gensim.models import Word2Vec
from pecanpy.pecanpy import SparseOTF


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train blended co-occurrence embeddings from multiple edgelists.",
    )
    parser.add_argument(
        "--edgelist",
        action="append",
        required=True,
        help="Path to an edgelist file (tab-separated: nodeA nodeB weight). Can be repeated.",
    )
    parser.add_argument(
        "--weight",
        action="append",
        type=float,
        required=True,
        help="Weight for the corresponding --edgelist. Must match 1:1.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/embeddings/blended.wv",
        help="Output path for .wv embeddings.",
    )
    parser.add_argument("--dim", type=int, default=128, help="Embedding dimension.")
    parser.add_argument("--walks", type=int, default=10, help="Number of random walks per node.")
    parser.add_argument("--walk-length", type=int, default=80, help="Length of each random walk.")
    parser.add_argument("--p", type=float, default=1.0, help="Node2Vec return parameter.")
    parser.add_argument("--q", type=float, default=1.0, help="Node2Vec in-out parameter.")
    parser.add_argument("--workers", type=int, default=4, help="Parallel workers.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    return parser.parse_args()


def load_edgelist(path: str) -> dict[tuple[str, str], float]:
    """Load a tab-separated edgelist. Returns {(nodeA, nodeB): weight}."""
    edges: dict[tuple[str, str], float] = {}
    with open(path) as f:
        for line_no, line in enumerate(f, 1):
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                print(f"  Warning: skipping malformed line {line_no} in {path}", file=sys.stderr)
                continue
            a, b = parts[0], parts[1]
            w = float(parts[2]) if len(parts) >= 3 else 1.0
            # Canonical ordering so (A,B) and (B,A) merge
            key = (min(a, b), max(a, b))
            edges[key] = edges.get(key, 0.0) + w
    return edges


def merge_edgelists(
    paths: list[str],
    weights: list[float],
) -> tuple[dict[tuple[str, str], float], dict[str, int]]:
    """
    Merge multiple edgelists with weights.

    Returns:
        merged: {(nodeA, nodeB): blended_weight}
        provenance: {edge_key_str: bitmask} where bit i means edge was in edgelist i
    """
    merged: dict[tuple[str, str], float] = defaultdict(float)
    provenance: dict[tuple[str, str], int] = defaultdict(int)

    for i, (path, w) in enumerate(zip(paths, weights)):
        print(f"  Loading edgelist {i}: {path} (weight={w})")
        edges = load_edgelist(path)
        print(f"    {len(edges)} edges loaded")
        for key, count in edges.items():
            merged[key] += count * w
            provenance[key] |= 1 << i

    return dict(merged), dict(provenance)


def write_merged_edgelist(
    merged: dict[tuple[str, str], float],
    path: str,
) -> None:
    """Write merged graph to a temporary edgelist for PecanPy."""
    with open(path, "w") as f:
        for (a, b), w in merged.items():
            f.write(f"{a}\t{b}\t{w}\n")


def compute_provenance_stats(
    provenance: dict[tuple[str, str], int],
    n_sources: int,
) -> dict[str, int]:
    """Compute how many edges come from each source combination."""
    stats: dict[str, int] = {}
    for i in range(n_sources):
        only_i = sum(1 for v in provenance.values() if v == (1 << i))
        stats[f"source_{i}_only"] = only_i
    both = sum(1 for v in provenance.values() if v == (1 << n_sources) - 1)
    stats["all_sources"] = both
    return stats


def quality_metrics(wv_path: str, merged: dict[tuple[str, str], float], seed: int = 42) -> None:
    """Report quality metrics on trained embeddings."""
    from gensim.models import KeyedVectors

    wv = KeyedVectors.load(wv_path)
    vocab = list(wv.key_to_index.keys())
    n = len(vocab)
    print("\n--- Quality Metrics ---")
    print(f"  Vocabulary size: {n}")

    # Random-pair similarity distribution
    rng = random.Random(seed)
    n_samples = min(10_000, n * (n - 1) // 2)
    sims = []
    for _ in range(n_samples):
        a, b = rng.sample(vocab, 2)
        sims.append(float(wv.similarity(a, b)))
    arr = np.array(sims)
    print(f"  Random-pair cosine similarity (n={n_samples}):")
    print(f"    mean={arr.mean():.4f}  std={arr.std():.4f}")
    print(f"    min={arr.min():.4f}  p25={np.percentile(arr, 25):.4f}  "
          f"median={np.median(arr):.4f}  p75={np.percentile(arr, 75):.4f}  max={arr.max():.4f}")

    # Top-edge similarity (edges with highest weight should have high similarity)
    top_edges = sorted(merged.items(), key=lambda x: -x[1])[:100]
    top_sims = []
    for (a, b), _ in top_edges:
        if a in wv and b in wv:
            top_sims.append(float(wv.similarity(a, b)))
    if top_sims:
        top_arr = np.array(top_sims)
        print("  Top-100 weighted edges similarity:")
        print(f"    mean={top_arr.mean():.4f}  std={top_arr.std():.4f}  "
              f"min={top_arr.min():.4f}  max={top_arr.max():.4f}")


def main() -> int:
    args = parse_args()

    if len(args.edgelist) != len(args.weight):
        print(f"Error: {len(args.edgelist)} edgelists but {len(args.weight)} weights", file=sys.stderr)
        return 1

    print("=" * 70)
    print("Blended Embedding Training")
    print("=" * 70)

    # Step 1: Merge
    print("\n[1/3] Merging edgelists...")
    merged, provenance = merge_edgelists(args.edgelist, args.weight)

    # Collect all nodes
    nodes: set[str] = set()
    for a, b in merged:
        nodes.add(a)
        nodes.add(b)

    n_sources = len(args.edgelist)
    prov_stats = compute_provenance_stats(provenance, n_sources)

    print("\n  Merged graph:")
    print(f"    Nodes: {len(nodes)}")
    print(f"    Edges: {len(merged)}")
    for key, count in prov_stats.items():
        print(f"    {key}: {count}")

    # Step 2: Write temporary edgelist and train
    tmp_edg = args.output.replace(".wv", "_merged.edg")
    Path(tmp_edg).parent.mkdir(parents=True, exist_ok=True)
    write_merged_edgelist(merged, tmp_edg)
    print(f"  Wrote merged edgelist to {tmp_edg}")

    print(f"\n[2/3] Training PecanPy (dim={args.dim}, walks={args.walks}, "
          f"walk_length={args.walk_length}, p={args.p}, q={args.q})...")
    t0 = time.time()
    g = SparseOTF(p=args.p, q=args.q, workers=args.workers, verbose=True, extend=True)
    g.read_edg(tmp_edg, weighted=True, directed=False)
    walks = g.simulate_walks(num_walks=args.walks, walk_length=args.walk_length)
    model = Word2Vec(
        walks,
        vector_size=args.dim,
        window=10,
        min_count=0,
        sg=1,
        workers=args.workers,
        epochs=1,
        seed=args.seed,
    )

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    model.wv.save(args.output)
    elapsed = time.time() - t0
    print(f"  Training complete in {elapsed:.1f}s")
    print(f"  Saved embeddings to {args.output}")

    # Step 3: Quality metrics
    print("\n[3/3] Computing quality metrics...")
    quality_metrics(args.output, merged, seed=args.seed)

    print(f"\n{'=' * 70}")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
