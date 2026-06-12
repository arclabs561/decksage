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
Train SEPARATE co-occurrence embeddings from multiple edgelist sources.

Unlike blended training, this produces one .wv file per source,
enabling independent signal fusion (e.g., "deck_embed" + "pack_embed"
as separate modalities in fusion.py).

Usage:
    uv run scripts/training/train_separate_embeddings.py \
        --edgelist data/graphs/pairs_large.edg --label deck \
        --edgelist data/graphs/magic_packs.edg --label pack \
        --output-dir data/embeddings/separate

Evaluation: for overlapping cards, shows how the same query-candidate pair
ranks in each embedding space.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
from gensim.models import KeyedVectors, Word2Vec
from pecanpy.pecanpy import SparseOTF


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train separate co-occurrence embeddings per edgelist source.",
    )
    parser.add_argument(
        "--edgelist",
        action="append",
        required=True,
        help="Path to an edgelist file. Can be repeated.",
    )
    parser.add_argument(
        "--label",
        action="append",
        required=True,
        help="Label for the corresponding --edgelist (used in output filename). Must match 1:1.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/embeddings/separate",
        help="Output directory for .wv files.",
    )
    parser.add_argument("--dim", type=int, default=128, help="Embedding dimension.")
    parser.add_argument("--walks", type=int, default=10, help="Number of random walks per node.")
    parser.add_argument("--walk-length", type=int, default=80, help="Length of each random walk.")
    parser.add_argument("--p", type=float, default=1.0, help="Node2Vec return parameter.")
    parser.add_argument("--q", type=float, default=1.0, help="Node2Vec in-out parameter.")
    parser.add_argument("--workers", type=int, default=4, help="Parallel workers.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument(
        "--compare-topn",
        type=int,
        default=20,
        help="Show top-N neighbors for comparison cards.",
    )
    parser.add_argument(
        "--compare-cards",
        nargs="*",
        default=None,
        help="Specific cards to compare across spaces. If not given, picks 5 random overlapping cards.",
    )
    return parser.parse_args()


def train_one(
    edgelist_path: str,
    label: str,
    output_dir: str,
    dim: int,
    walks: int,
    walk_length: int,
    p: float,
    q: float,
    workers: int,
    seed: int,
) -> str:
    """Train PecanPy on a single edgelist. Returns output .wv path."""
    out_path = str(Path(output_dir) / f"{label}.wv")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    print(f"\n  Training '{label}' from {edgelist_path}")
    t0 = time.time()
    g = SparseOTF(p=p, q=q, workers=workers, verbose=True, extend=True)
    g.read_edg(edgelist_path, weighted=True, directed=False)
    walks_data = g.simulate_walks(num_walks=walks, walk_length=walk_length)
    model = Word2Vec(
        walks_data,
        vector_size=dim,
        window=10,
        min_count=0,
        sg=1,
        workers=workers,
        epochs=1,
        seed=seed,
    )
    model.wv.save(out_path)
    elapsed = time.time() - t0
    print(f"    Nodes: {len(model.wv)}, Trained in {elapsed:.1f}s -> {out_path}")
    return out_path


def compare_embedding_spaces(
    wv_paths: list[str],
    labels: list[str],
    compare_cards: list[str] | None,
    topn: int,
) -> None:
    """Show how the same card's neighbors differ across embedding spaces."""
    models = {}
    vocabs = {}
    for path, label in zip(wv_paths, labels):
        wv = KeyedVectors.load(path)
        models[label] = wv
        vocabs[label] = set(wv.key_to_index.keys())

    # Find overlapping vocabulary
    overlap = set.intersection(*vocabs.values()) if vocabs else set()
    print("\n--- Cross-Space Comparison ---")
    for label, vocab in vocabs.items():
        print(f"  {label}: {len(vocab)} nodes")
    print(f"  Overlap: {len(overlap)} nodes")

    if not overlap:
        print("  No overlapping nodes; cannot compare.")
        return

    # Select cards to compare
    if compare_cards:
        cards = [c for c in compare_cards if c in overlap]
        if not cards:
            print("  Warning: none of the requested cards are in the overlap set.")
            return
    else:
        import random

        rng = random.Random(42)
        cards = rng.sample(sorted(overlap), min(5, len(overlap)))

    for card in cards:
        print(f"\n  Card: {card}")
        for label in labels:
            wv = models[label]
            if card not in wv:
                print(f"    [{label}] not in vocabulary")
                continue
            neighbors = wv.most_similar(card, topn=topn)
            print(f"    [{label}] top-{topn} neighbors:")
            for rank, (name, sim) in enumerate(neighbors, 1):
                # Mark if this neighbor exists in the other space(s)
                markers = []
                for other_label in labels:
                    if other_label == label:
                        continue
                    if name in models[other_label]:
                        other_wv = models[other_label]
                        if card in other_wv:
                            other_sim = float(other_wv.similarity(card, name))
                            markers.append(f"{other_label}={other_sim:+.3f}")
                marker_str = f"  ({', '.join(markers)})" if markers else ""
                print(f"      {rank:3d}. {sim:+.4f}  {name}{marker_str}")

    # Rank correlation for overlapping pairs
    print(f"\n  Rank correlation (top-{topn}, overlapping cards):")
    if len(labels) == 2:
        _rank_correlation(models[labels[0]], models[labels[1]], labels[0], labels[1], overlap, topn)


def _rank_correlation(
    wv_a: KeyedVectors,
    wv_b: KeyedVectors,
    label_a: str,
    label_b: str,
    overlap: set[str],
    topn: int,
) -> None:
    """Compute rank overlap between two embedding spaces for shared nodes."""
    import random

    rng = random.Random(42)
    sample = rng.sample(sorted(overlap), min(200, len(overlap)))

    overlaps = []
    for card in sample:
        top_a = {name for name, _ in wv_a.most_similar(card, topn=topn)}
        top_b = {name for name, _ in wv_b.most_similar(card, topn=topn)}
        shared = len(top_a & top_b)
        overlaps.append(shared / topn)

    arr = np.array(overlaps)
    print(
        f"    Mean top-{topn} overlap between [{label_a}] and [{label_b}]: "
        f"{arr.mean():.3f} (std={arr.std():.3f})"
    )


def main() -> int:
    args = parse_args()

    if len(args.edgelist) != len(args.label):
        print(
            f"Error: {len(args.edgelist)} edgelists but {len(args.label)} labels", file=sys.stderr
        )
        return 1

    print("=" * 70)
    print("Separate Embedding Training")
    print("=" * 70)

    wv_paths = []
    for edgelist, label in zip(args.edgelist, args.label):
        path = train_one(
            edgelist_path=edgelist,
            label=label,
            output_dir=args.output_dir,
            dim=args.dim,
            walks=args.walks,
            walk_length=args.walk_length,
            p=args.p,
            q=args.q,
            workers=args.workers,
            seed=args.seed,
        )
        wv_paths.append(path)

    # Cross-space comparison
    compare_embedding_spaces(
        wv_paths=wv_paths,
        labels=args.label,
        compare_cards=args.compare_cards,
        topn=args.compare_topn,
    )

    print(f"\n{'=' * 70}")
    print("Done. Output files:")
    for label, path in zip(args.label, wv_paths):
        print(f"  {label}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
