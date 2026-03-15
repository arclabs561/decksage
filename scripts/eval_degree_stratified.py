# /// script
# requires-python = ">=3.11"
# dependencies = ["gensim>=4.3.0", "numpy>=1.26.0", "pandas>=2.0.0"]
# ///
"""Degree-stratified evaluation of embedding quality.

Hamilton lens: "Report metrics separately for low-degree (< 5 edges),
medium (5-20), and high (> 20) nodes. If low-degree performance is much
worse, the model is learning degree, not structure."

Usage:
    uv run scripts/eval_degree_stratified.py --game magic
    uv run scripts/eval_degree_stratified.py --game magic --emb data/embeddings/magic_cleaned_v4.wv
"""

from __future__ import annotations

import argparse
import pickle
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np


def load_graph(pairs_path: Path) -> dict[str, set[str]]:
    """Load adjacency from pickle cache or CSV."""
    cache = pairs_path.with_suffix(pairs_path.suffix + ".pkl")
    if cache.exists() and cache.stat().st_mtime >= pairs_path.stat().st_mtime:
        data = pickle.load(open(cache, "rb"))
        return data["adj"]
    import pandas as pd

    df = pd.read_csv(pairs_path)
    adj: dict[str, set[str]] = defaultdict(set)
    for _, row in df.iterrows():
        c1, c2 = str(row["NAME_1"]).strip(), str(row["NAME_2"]).strip()
        adj[c1].add(c2)
        adj[c2].add(c1)
    return dict(adj)


def evaluate(emb_path: str, pairs_path: str, k: int = 10) -> None:
    from gensim.models import KeyedVectors

    print(f"Loading embeddings: {emb_path}")
    emb = KeyedVectors.load(emb_path)
    print(f"  vocab: {len(emb)}, dim: {emb.vector_size}")

    print(f"Loading graph: {pairs_path}")
    adj = load_graph(Path(pairs_path))
    print(f"  nodes: {len(adj)}")

    # Stratify by degree
    degree_bins = {"low (<5)": [], "medium (5-20)": [], "high (>20)": []}
    for card in emb.index_to_key:
        deg = len(adj.get(card, set()))
        if deg < 5:
            degree_bins["low (<5)"].append(card)
        elif deg <= 20:
            degree_bins["medium (5-20)"].append(card)
        else:
            degree_bins["high (>20)"].append(card)

    print(f"\nDegree distribution:")
    for label, cards in degree_bins.items():
        print(f"  {label}: {len(cards)} cards")

    # Evaluate: for each card, check if top-k embedding neighbors overlap with graph neighbors
    print(f"\nRecall@{k} by degree stratum:")
    print(f"{'Stratum':<20} {'Cards':<8} {'Recall@k':<10} {'MRR':<10}")
    print("-" * 48)

    for label, cards in degree_bins.items():
        if not cards:
            print(f"{label:<20} {'0':<8} {'--':<10} {'--':<10}")
            continue

        recalls = []
        mrrs = []
        sample = cards[:min(len(cards), 2000)]  # Cap for speed

        for card in sample:
            neighbors = adj.get(card, set())
            if not neighbors:
                continue
            try:
                similar = emb.most_similar(card, topn=k)
                predicted = {c for c, _ in similar}
                overlap = len(predicted & neighbors)
                recall = overlap / min(k, len(neighbors))
                recalls.append(recall)

                # MRR: rank of first true neighbor
                for rank, (c, _) in enumerate(similar, 1):
                    if c in neighbors:
                        mrrs.append(1.0 / rank)
                        break
                else:
                    mrrs.append(0.0)
            except KeyError:
                continue

        if recalls:
            print(
                f"{label:<20} {len(recalls):<8} {np.mean(recalls):<10.4f} {np.mean(mrrs):<10.4f}"
            )
        else:
            print(f"{label:<20} {'0':<8} {'--':<10} {'--':<10}")

    # Singular value spectrum (embedding collapse check)
    print("\nSingular value spectrum (embedding collapse check):")
    matrix = emb.vectors
    _, s, _ = np.linalg.svd(matrix, full_matrices=False)
    stable_rank = (np.sum(s**2) / (s[0] ** 2)) if s[0] > 0 else 0
    effective_dim = emb.vector_size
    print(f"  Top singular value: {s[0]:.2f}")
    print(f"  Median singular value: {np.median(s):.2f}")
    print(f"  Ratio top/median: {s[0]/np.median(s):.1f}x")
    print(f"  Stable rank: {stable_rank:.1f} / {effective_dim} ({stable_rank/effective_dim*100:.0f}%)")
    if s[0] / np.median(s) > 10:
        print("  WARNING: top/median > 10x suggests dimensional collapse")
    if stable_rank / effective_dim < 0.5:
        print("  WARNING: stable rank < 50% of dim suggests low effective dimensionality")


def main():
    parser = argparse.ArgumentParser(description="Degree-stratified embedding evaluation")
    parser.add_argument("--game", default="magic", choices=["magic", "pokemon", "yugioh"])
    parser.add_argument("--emb", help="Embedding path (auto-detected if not provided)")
    parser.add_argument("--pairs", help="Pairs CSV path (auto-detected if not provided)")
    parser.add_argument("--k", type=int, default=10, help="Top-k for recall")
    args = parser.parse_args()

    game = args.game
    emb_path = args.emb
    pairs_path = args.pairs

    if not emb_path:
        candidates = sorted(Path("data/embeddings").glob(f"{game}_*.wv"), key=lambda p: -p.stat().st_mtime)
        if candidates:
            emb_path = str(candidates[0])
        else:
            print(f"No embedding file found for {game} in data/embeddings/")
            sys.exit(1)

    if not pairs_path:
        candidates = sorted(
            Path("data/processed").glob(f"pairs_{game}_*.csv") if game != "magic"
            else Path("data/processed").glob("pairs_large.csv"),
            key=lambda p: -p.stat().st_size,
        )
        if game == "magic" and not candidates:
            candidates = sorted(Path("data/processed").glob("pairs_large.csv"))
        if candidates:
            pairs_path = str(candidates[0])
        else:
            print(f"No pairs file found for {game} in data/processed/")
            sys.exit(1)

    evaluate(emb_path, pairs_path, k=args.k)


if __name__ == "__main__":
    main()
