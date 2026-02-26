#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "gensim>=4.3",
#     "numpy>=1.24",
# ]
# ///
"""
Generate stratified card pairs for LLM annotation.

Selects 100 pairs across 4 similarity buckets using:
  - production.wv (embedding cosine similarity)
  - pairs_large.edg (co-occurrence weights from tournament decks)

Buckets:
  HIGH          ~25 pairs  top 1% embedding cosine + co-occurrence
  MEDIUM-HIGH   ~25 pairs  top 5-15% cosine + high co-occurrence weight
  MEDIUM-LOW    ~25 pairs  cosine 0.3-0.5 + some co-occurrence
  LOW           ~25 pairs  random pairs with no co-occurrence
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np


def load_embeddings(path: Path) -> tuple[list[str], np.ndarray]:
    """Load gensim KeyedVectors, return (card_names, normalized_vectors)."""
    from gensim.models import KeyedVectors

    wv = KeyedVectors.load(str(path))
    cards = list(wv.key_to_index.keys())
    vecs = wv.vectors.copy()
    # L2-normalize for cosine via dot product
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    vecs /= norms
    return cards, vecs


def load_cooccurrence(path: Path) -> dict[tuple[str, str], int]:
    """Load edge list as {(card_a, card_b): weight} with canonical ordering."""
    edges: dict[tuple[str, str], int] = {}
    with open(path) as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            a, b, w = parts[0], parts[1], int(parts[2])
            key = (min(a, b), max(a, b))
            edges[key] = edges.get(key, 0) + w
    return edges


def cooccurrence_weight(
    edges: dict[tuple[str, str], int], c1: str, c2: str
) -> int:
    key = (min(c1, c2), max(c1, c2))
    return edges.get(key, 0)


def has_cooccurrence(
    edges: dict[tuple[str, str], int], c1: str, c2: str
) -> bool:
    return cooccurrence_weight(edges, c1, c2) > 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate stratified card pairs for LLM annotation"
    )
    parser.add_argument(
        "--embeddings",
        type=Path,
        default=Path("data/embeddings/production.wv"),
        help="Path to gensim KeyedVectors file",
    )
    parser.add_argument(
        "--edges",
        type=Path,
        default=Path("data/graphs/pairs_large.edg"),
        help="Path to co-occurrence edge list (TSV: card1, card2, weight)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("annotations/magic_stratified_pairs.jsonl"),
        help="Output JSONL path",
    )
    parser.add_argument(
        "--total", type=int, default=100, help="Total pairs to generate"
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Random seed for reproducibility"
    )
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)

    # --- Load data -----------------------------------------------------------
    print(f"Loading embeddings from {args.embeddings} ...")
    cards, vecs = load_embeddings(args.embeddings)
    card_to_idx = {c: i for i, c in enumerate(cards)}
    print(f"  {len(cards)} cards, {vecs.shape[1]}-dim vectors")

    print(f"Loading co-occurrence from {args.edges} ...")
    edges = load_cooccurrence(args.edges)
    print(f"  {len(edges)} edges loaded")

    # Restrict to cards present in BOTH sources
    edge_cards: set[str] = set()
    for a, b in edges:
        edge_cards.add(a)
        edge_cards.add(b)
    shared_cards = sorted(set(cards) & edge_cards)
    print(f"  {len(shared_cards)} cards in both embeddings and co-occurrence")

    shared_idx = np.array([card_to_idx[c] for c in shared_cards])
    shared_vecs = vecs[shared_idx]
    shared_card_to_local = {c: i for i, c in enumerate(shared_cards)}

    # --- Precompute pairwise cosine for a manageable random sample -----------
    # Full pairwise is O(n^2) ~ 36B for 8.5K cards.  Instead, sample candidate
    # pairs per bucket and score them.

    n_per_bucket = args.total // 4
    remainder = args.total - 4 * n_per_bucket  # distribute remainder to HIGH
    bucket_sizes = {
        "HIGH": n_per_bucket + remainder,
        "MEDIUM_HIGH": n_per_bucket,
        "MEDIUM_LOW": n_per_bucket,
        "LOW": n_per_bucket,
    }
    print(f"\nTarget bucket sizes: {bucket_sizes}")

    # --- Build co-occurrence lookup by card for efficient sampling -----------
    card_neighbors: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for (a, b), w in edges.items():
        if a in shared_card_to_local and b in shared_card_to_local:
            card_neighbors[a].append((b, w))
            card_neighbors[b].append((a, w))

    # --- HIGH bucket: top 1% cosine among co-occurring pairs -----------------
    print("\nSampling HIGH bucket (top cosine + co-occurrence) ...")
    # Score a large sample of co-occurring pairs by cosine
    cooccur_pairs_scored: list[tuple[str, str, float, int]] = []
    # Use high-weight edges as candidates (weight >= P90 = 5)
    high_weight_edges = [(a, b, w) for (a, b), w in edges.items()
                         if w >= 5
                         and a in shared_card_to_local
                         and b in shared_card_to_local]
    print(f"  {len(high_weight_edges)} edges with weight >= 5")

    for a, b, w in high_weight_edges:
        ia, ib = shared_card_to_local[a], shared_card_to_local[b]
        sim = float(shared_vecs[ia] @ shared_vecs[ib])
        cooccur_pairs_scored.append((a, b, sim, w))

    # Sort by cosine descending, take top pairs
    cooccur_pairs_scored.sort(key=lambda x: x[2], reverse=True)

    high_pairs = []
    seen: set[tuple[str, str]] = set()
    for a, b, sim, w in cooccur_pairs_scored:
        key = (min(a, b), max(a, b))
        if key not in seen:
            seen.add(key)
            high_pairs.append({
                "card1": a,
                "card2": b,
                "expected_bucket": "HIGH",
                "embedding_sim": round(sim, 4),
                "cooccurrence_weight": w,
            })
        if len(high_pairs) >= bucket_sizes["HIGH"]:
            break
    print(f"  Selected {len(high_pairs)} HIGH pairs"
          f" (sim range: {high_pairs[-1]['embedding_sim']:.3f}"
          f" - {high_pairs[0]['embedding_sim']:.3f})")

    # --- MEDIUM-HIGH bucket: top 5-15% cosine + high co-occurrence -----------
    print("\nSampling MEDIUM_HIGH bucket (5-15% cosine + co-occurrence) ...")
    # From the scored co-occurring pairs, skip the ones already used for HIGH,
    # then take pairs in the 85th-95th percentile of cosine among co-occurring.
    remaining_scored = [
        (a, b, sim, w) for a, b, sim, w in cooccur_pairs_scored
        if (min(a, b), max(a, b)) not in seen
    ]

    # Target: pairs with moderate-high cosine similarity
    if remaining_scored:
        sims_arr = np.array([s for _, _, s, _ in remaining_scored])
        p85 = float(np.percentile(sims_arr, 85))
        p95 = float(np.percentile(sims_arr, 95))
        med_high_candidates = [
            (a, b, sim, w) for a, b, sim, w in remaining_scored
            if p85 <= sim <= p95 and w >= 3
        ]
        random.shuffle(med_high_candidates)

    med_high_pairs = []
    for a, b, sim, w in med_high_candidates:
        key = (min(a, b), max(a, b))
        if key not in seen:
            seen.add(key)
            med_high_pairs.append({
                "card1": a,
                "card2": b,
                "expected_bucket": "MEDIUM_HIGH",
                "embedding_sim": round(sim, 4),
                "cooccurrence_weight": w,
            })
        if len(med_high_pairs) >= bucket_sizes["MEDIUM_HIGH"]:
            break
    print(f"  Selected {len(med_high_pairs)} MEDIUM_HIGH pairs"
          f" (cosine in [{p85:.3f}, {p95:.3f}])")

    # --- MEDIUM-LOW bucket: cosine 0.3-0.5, some co-occurrence --------------
    print("\nSampling MEDIUM_LOW bucket (cosine 0.3-0.5, some co-occurrence) ...")
    # Sample random co-occurring pairs and filter by cosine range
    all_shared_edges = [
        (a, b, w) for (a, b), w in edges.items()
        if a in shared_card_to_local and b in shared_card_to_local
    ]
    random.shuffle(all_shared_edges)

    med_low_pairs = []
    for a, b, w in all_shared_edges:
        key = (min(a, b), max(a, b))
        if key in seen:
            continue
        ia, ib = shared_card_to_local[a], shared_card_to_local[b]
        sim = float(shared_vecs[ia] @ shared_vecs[ib])
        if 0.3 <= sim <= 0.5:
            seen.add(key)
            med_low_pairs.append({
                "card1": a,
                "card2": b,
                "expected_bucket": "MEDIUM_LOW",
                "embedding_sim": round(sim, 4),
                "cooccurrence_weight": w,
            })
        if len(med_low_pairs) >= bucket_sizes["MEDIUM_LOW"]:
            break
    print(f"  Selected {len(med_low_pairs)} MEDIUM_LOW pairs")

    # --- LOW bucket: random pairs with NO co-occurrence ----------------------
    print("\nSampling LOW bucket (no co-occurrence, random pairs) ...")
    low_pairs = []
    attempts = 0
    max_attempts = bucket_sizes["LOW"] * 200
    while len(low_pairs) < bucket_sizes["LOW"] and attempts < max_attempts:
        attempts += 1
        i, j = random.sample(range(len(shared_cards)), 2)
        a, b = shared_cards[i], shared_cards[j]
        key = (min(a, b), max(a, b))
        if key in seen:
            continue
        if has_cooccurrence(edges, a, b):
            continue
        sim = float(shared_vecs[i] @ shared_vecs[j])
        seen.add(key)
        low_pairs.append({
            "card1": a,
            "card2": b,
            "expected_bucket": "LOW",
            "embedding_sim": round(sim, 4),
            "cooccurrence_weight": 0,
        })
    print(f"  Selected {len(low_pairs)} LOW pairs ({attempts} attempts)")

    # --- Combine and write ---------------------------------------------------
    all_pairs = high_pairs + med_high_pairs + med_low_pairs + low_pairs
    random.shuffle(all_pairs)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        for pair in all_pairs:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")

    print(f"\nWrote {len(all_pairs)} pairs to {args.output}")

    # --- Summary stats -------------------------------------------------------
    print("\n=== Bucket Summary ===")
    for bucket in ["HIGH", "MEDIUM_HIGH", "MEDIUM_LOW", "LOW"]:
        bucket_items = [p for p in all_pairs if p["expected_bucket"] == bucket]
        if not bucket_items:
            print(f"  {bucket}: 0 pairs")
            continue
        sims = [p["embedding_sim"] for p in bucket_items]
        weights = [p["cooccurrence_weight"] for p in bucket_items]
        print(
            f"  {bucket:12s}: {len(bucket_items):3d} pairs"
            f"  | cosine [{min(sims):.3f}, {max(sims):.3f}]"
            f"  avg {np.mean(sims):.3f}"
            f"  | co-occ [{min(weights)}, {max(weights)}]"
            f"  avg {np.mean(weights):.1f}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
