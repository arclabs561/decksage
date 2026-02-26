#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "gensim>=4.3",
#     "numpy>=1.24",
# ]
# ///
"""
Generate stratified card pairs for LLM annotation (YuGiOh / Pokemon).

Selects 100 pairs across 4 similarity buckets using:
  - blended.wv (embedding cosine similarity)
  - edge list (co-occurrence weights from decks/packs)

Buckets:
  HIGH          ~25 pairs  top cosine + co-occurrence
  MEDIUM-HIGH   ~25 pairs  moderate-high cosine + co-occurrence
  MEDIUM-LOW    ~25 pairs  cosine 0.3-0.5 + some co-occurrence
  LOW           ~25 pairs  random pairs with no co-occurrence

Usage:
  uv run scripts/annotation/generate_game_stratified_pairs.py --game yugioh
  uv run scripts/annotation/generate_game_stratified_pairs.py --game pokemon
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np


GAME_PRESETS: dict[str, dict[str, str]] = {
    "yugioh": {
        "embeddings": "data/embeddings/yugioh_blended.wv",
        "edges": "data/graphs/yugioh_named.edg",
        "output": "annotations/yugioh_stratified_pairs.jsonl",
        "high_weight_threshold": "5",
        "med_high_weight_threshold": "3",
    },
    "pokemon": {
        "embeddings": "data/embeddings/pokemon_blended.wv",
        "edges": "data/graphs/pokemon_packs.edg",
        "output": "annotations/pokemon_stratified_pairs.jsonl",
        # Pokemon pack edges are unweighted (all weight=1), so thresholds are 1
        "high_weight_threshold": "1",
        "med_high_weight_threshold": "1",
    },
}


def load_embeddings(path: Path) -> tuple[list[str], np.ndarray]:
    """Load gensim KeyedVectors, return (card_names, normalized_vectors)."""
    from gensim.models import KeyedVectors

    wv = KeyedVectors.load(str(path))
    cards = list(wv.key_to_index.keys())
    vecs = wv.vectors.copy()
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
            if len(parts) < 2:
                continue
            a, b = parts[0], parts[1]
            w = int(parts[2]) if len(parts) >= 3 else 1
            # Skip self-loops
            if a == b:
                continue
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


def is_placeholder_id(name: str) -> bool:
    """Return True for Card_XXXXX placeholder names (unmapped YGO cards)."""
    return name.startswith("Card_") and name[5:].isdigit()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate stratified card pairs for LLM annotation"
    )
    parser.add_argument(
        "--game",
        choices=list(GAME_PRESETS.keys()),
        required=True,
        help="Game to generate pairs for",
    )
    parser.add_argument(
        "--embeddings", type=Path, default=None,
        help="Override: path to gensim KeyedVectors file",
    )
    parser.add_argument(
        "--edges", type=Path, default=None,
        help="Override: path to co-occurrence edge list",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Override: output JSONL path",
    )
    parser.add_argument(
        "--total", type=int, default=100, help="Total pairs to generate"
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Random seed for reproducibility"
    )
    args = parser.parse_args()

    preset = GAME_PRESETS[args.game]
    emb_path = args.embeddings or Path(preset["embeddings"])
    edge_path = args.edges or Path(preset["edges"])
    out_path = args.output or Path(preset["output"])
    high_w_thresh = int(preset["high_weight_threshold"])
    med_high_w_thresh = int(preset["med_high_weight_threshold"])

    random.seed(args.seed)
    np.random.seed(args.seed)

    # --- Load data -----------------------------------------------------------
    print(f"Loading embeddings from {emb_path} ...")
    cards, vecs = load_embeddings(emb_path)
    card_to_idx = {c: i for i, c in enumerate(cards)}
    print(f"  {len(cards)} cards, {vecs.shape[1]}-dim vectors")

    print(f"Loading co-occurrence from {edge_path} ...")
    edges = load_cooccurrence(edge_path)
    print(f"  {len(edges)} edges loaded")

    # Restrict to cards present in BOTH sources, excluding placeholder IDs
    edge_cards: set[str] = set()
    for a, b in edges:
        edge_cards.add(a)
        edge_cards.add(b)
    shared_cards = sorted(
        c for c in (set(cards) & edge_cards) if not is_placeholder_id(c)
    )
    print(f"  {len(shared_cards)} cards in both embeddings and co-occurrence"
          f" (excluding placeholder IDs)")

    shared_idx = np.array([card_to_idx[c] for c in shared_cards])
    shared_vecs = vecs[shared_idx]
    shared_card_to_local = {c: i for i, c in enumerate(shared_cards)}

    # --- Bucket sizes --------------------------------------------------------
    n_per_bucket = args.total // 4
    remainder = args.total - 4 * n_per_bucket
    bucket_sizes = {
        "HIGH": n_per_bucket + remainder,
        "MEDIUM_HIGH": n_per_bucket,
        "MEDIUM_LOW": n_per_bucket,
        "LOW": n_per_bucket,
    }
    print(f"\nTarget bucket sizes: {bucket_sizes}")

    seen: set[tuple[str, str]] = set()

    # --- HIGH bucket: top cosine among co-occurring pairs --------------------
    print(f"\nSampling HIGH bucket (top cosine + co-occurrence, w>={high_w_thresh}) ...")
    high_weight_edges = [
        (a, b, w) for (a, b), w in edges.items()
        if w >= high_w_thresh
        and a in shared_card_to_local
        and b in shared_card_to_local
    ]
    print(f"  {len(high_weight_edges)} candidate edges")

    cooccur_pairs_scored: list[tuple[str, str, float, int]] = []
    for a, b, w in high_weight_edges:
        ia, ib = shared_card_to_local[a], shared_card_to_local[b]
        sim = float(shared_vecs[ia] @ shared_vecs[ib])
        cooccur_pairs_scored.append((a, b, sim, w))

    cooccur_pairs_scored.sort(key=lambda x: x[2], reverse=True)

    high_pairs = []
    for a, b, sim, w in cooccur_pairs_scored:
        key = (min(a, b), max(a, b))
        if key not in seen:
            seen.add(key)
            high_pairs.append({
                "card1": a,
                "card2": b,
                "game": args.game,
                "expected_bucket": "HIGH",
                "embedding_sim": round(sim, 4),
                "cooccurrence_weight": w,
            })
        if len(high_pairs) >= bucket_sizes["HIGH"]:
            break
    if high_pairs:
        print(f"  Selected {len(high_pairs)} HIGH pairs"
              f" (sim range: {high_pairs[-1]['embedding_sim']:.3f}"
              f" - {high_pairs[0]['embedding_sim']:.3f})")
    else:
        print("  WARNING: 0 HIGH pairs selected")

    # --- MEDIUM-HIGH bucket --------------------------------------------------
    print(f"\nSampling MEDIUM_HIGH bucket (moderate cosine + co-occurrence, w>={med_high_w_thresh}) ...")

    # For Pokemon (all weights=1), we need ALL co-occurring pairs, not just high-weight
    if med_high_w_thresh <= 1:
        # Re-score all co-occurring pairs
        all_cooccur_scored: list[tuple[str, str, float, int]] = []
        for (a, b), w in edges.items():
            if a in shared_card_to_local and b in shared_card_to_local:
                key = (min(a, b), max(a, b))
                if key in seen:
                    continue
                ia, ib = shared_card_to_local[a], shared_card_to_local[b]
                sim = float(shared_vecs[ia] @ shared_vecs[ib])
                all_cooccur_scored.append((a, b, sim, w))
        remaining_scored = all_cooccur_scored
    else:
        remaining_scored = [
            (a, b, sim, w) for a, b, sim, w in cooccur_pairs_scored
            if (min(a, b), max(a, b)) not in seen
        ]

    med_high_pairs = []
    if remaining_scored:
        sims_arr = np.array([s for _, _, s, _ in remaining_scored])
        p85 = float(np.percentile(sims_arr, 85))
        p95 = float(np.percentile(sims_arr, 95))
        med_high_candidates = [
            (a, b, sim, w) for a, b, sim, w in remaining_scored
            if p85 <= sim <= p95 and w >= med_high_w_thresh
        ]
        random.shuffle(med_high_candidates)

        for a, b, sim, w in med_high_candidates:
            key = (min(a, b), max(a, b))
            if key not in seen:
                seen.add(key)
                med_high_pairs.append({
                    "card1": a,
                    "card2": b,
                    "game": args.game,
                    "expected_bucket": "MEDIUM_HIGH",
                    "embedding_sim": round(sim, 4),
                    "cooccurrence_weight": w,
                })
            if len(med_high_pairs) >= bucket_sizes["MEDIUM_HIGH"]:
                break
        print(f"  Selected {len(med_high_pairs)} MEDIUM_HIGH pairs"
              f" (cosine in [{p85:.3f}, {p95:.3f}])")
    else:
        print("  WARNING: no remaining scored pairs for MEDIUM_HIGH")

    # --- MEDIUM-LOW bucket: cosine 0.3-0.5, some co-occurrence --------------
    print("\nSampling MEDIUM_LOW bucket (cosine 0.3-0.5, some co-occurrence) ...")
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
                "game": args.game,
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
            "game": args.game,
            "expected_bucket": "LOW",
            "embedding_sim": round(sim, 4),
            "cooccurrence_weight": 0,
        })
    print(f"  Selected {len(low_pairs)} LOW pairs ({attempts} attempts)")

    # --- Combine and write ---------------------------------------------------
    all_pairs = high_pairs + med_high_pairs + med_low_pairs + low_pairs
    random.shuffle(all_pairs)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        for pair in all_pairs:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")

    print(f"\nWrote {len(all_pairs)} pairs to {out_path}")

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
