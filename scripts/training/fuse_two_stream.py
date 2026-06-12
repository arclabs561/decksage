#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["gensim>=4.3.0", "numpy<2.0.0", "scikit-learn"]
# ///
"""
Fuse two embedding streams into a single 128D embedding.

Stream A: structural co-occurrence (PecanPy/ProNE on graph)
Stream B: functional similarity (Word2Vec on deck lists, ns_exponent=-0.5)

Supports two fusion methods:
  - concat: weighted concatenation + PCA (default). Cards in only one stream
    are backfilled with zero vectors for the missing stream.
  - average: L2-normalize each stream, then weighted average for shared cards.
    Single-stream cards use their own vector directly.

Usage:
    uv run scripts/training/fuse_two_stream.py \
        --stream-a data/embeddings/magic_cleaned_v4.wv \
        --stream-b data/embeddings/magic_ns-0.5_128d.wv \
        --output data/embeddings/magic_two_stream_v1.wv \
        --method average --alpha 0.5
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

import numpy as np
from gensim.models import KeyedVectors
from sklearn.decomposition import PCA
from sklearn.preprocessing import normalize


QUALITY_PAIRS = [
    # (card_a, card_b, label, min_threshold)
    ("Lightning Bolt", "Fireball", "co-occurrence", 0.50),
    ("Lightning Bolt", "Chain Lightning", "functional", 0.30),
    ("Sol Ring", "Arcane Signet", "co-occurrence", 0.50),
    ("Swords to Plowshares", "Path to Exile", "functional", 0.30),
    ("Counterspell", "Mana Leak", "functional", 0.20),
    ("Dark Ritual", "Cabal Ritual", "functional", 0.40),
    # Negative control
    ("Lightning Bolt", "Island", "negative", None),
]

NEGATIVE_THRESHOLD = 0.20

RELEVANCE_GRADES = {
    "highly_relevant": 3,
    "relevant": 2,
    "somewhat_relevant": 1,
    "marginally_relevant": 0.5,
    "irrelevant": 0,
}


def evaluate_quality(kv: KeyedVectors, label: str) -> dict[str, float]:
    """Evaluate quality pairs and return {pair_label: similarity}."""
    results = {}
    n_pass = 0
    n_total = 0
    print(f"\n  Quality pairs ({label}):")
    for card_a, card_b, kind, threshold in QUALITY_PAIRS:
        if card_a not in kv or card_b not in kv:
            tag = "MISSING"
            sim = float("nan")
        else:
            sim = float(kv.similarity(card_a, card_b))
            n_total += 1
            if kind == "negative":
                passed = sim < NEGATIVE_THRESHOLD
            elif threshold is not None:
                passed = sim >= threshold
            else:
                passed = True
            tag = "PASS" if passed else "FAIL"
            if passed:
                n_pass += 1
        pair_key = f"{card_a} <-> {card_b}"
        results[pair_key] = sim
        thresh_str = (
            f" (>={threshold:.2f})"
            if threshold
            else f" (<{NEGATIVE_THRESHOLD:.2f})"
            if kind == "negative"
            else ""
        )
        print(f"    {tag:7s} {sim:+.4f}  {card_a} <-> {card_b}{thresh_str}")
    print(f"    Score: {n_pass}/{n_total}")
    return results


def evaluate_ndcg(kv: KeyedVectors, test_set_path: Path, label: str) -> tuple[float, float, int]:
    """Evaluate nDCG@5 and nDCG@10 on annotated test set. Returns (ndcg5, ndcg10, n_queries)."""
    if not test_set_path.exists():
        print(f"\n  nDCG ({label}): SKIPPED (no test set)")
        return 0.0, 0.0, 0

    data = json.load(open(test_set_path))
    queries = data.get("queries", data)

    def dcg(scores, k):
        return sum(s / math.log2(i + 2) for i, s in enumerate(scores[:k]))

    def ndcg(rels, k):
        d = dcg(rels, k)
        ideal = dcg(sorted(rels, reverse=True), k)
        return d / ideal if ideal > 0 else 0.0

    scores5, scores10 = [], []
    n_miss = 0
    for q, labels in queries.items():
        if q not in kv:
            n_miss += 1
            continue
        try:
            neighbors = kv.most_similar(q, topn=20)
        except Exception:
            n_miss += 1
            continue
        rels = []
        for card, _ in neighbors:
            grade = 0.0
            for level, w in RELEVANCE_GRADES.items():
                if card in labels.get(level, []):
                    grade = w
                    break
            rels.append(grade)
        scores5.append(ndcg(rels, 5))
        scores10.append(ndcg(rels, 10))

    n = len(scores5)
    m5 = sum(scores5) / n if n else 0
    m10 = sum(scores10) / n if n else 0
    total = n + n_miss
    print(f"  nDCG ({label}): @5={m5:.3f}  @10={m10:.3f}  ({n}/{total} queries)")
    return m5, m10, n


def fuse_concat_pca(
    kv_a: KeyedVectors,
    kv_b: KeyedVectors,
    shared: list[str],
    only_a: list[str],
    only_b: list[str],
    alpha: float,
    dim: int,
    backfill: bool,
) -> tuple[list[str], np.ndarray]:
    """Fuse via weighted concatenation + PCA."""
    dim_a = kv_a.vector_size
    dim_b = kv_b.vector_size

    mat_a = np.array([kv_a[k] for k in shared], dtype=np.float32)
    mat_b = np.array([kv_b[k] for k in shared], dtype=np.float32)
    mat_a_norm = normalize(mat_a, norm="l2")
    mat_b_norm = normalize(mat_b, norm="l2")

    combined = np.hstack([alpha * mat_a_norm, (1 - alpha) * mat_b_norm])
    print(f"\nConcatenated shape (shared): {combined.shape} (alpha={alpha})")

    target_dim = min(dim, combined.shape[1], combined.shape[0])
    pca = None
    if combined.shape[1] > target_dim:
        print(f"PCA: {combined.shape[1]} -> {target_dim}")
        pca = PCA(n_components=target_dim, random_state=42)
        combined = pca.fit_transform(combined)
        explained = sum(pca.explained_variance_ratio_)
        print(f"  Explained variance: {explained:.3f}")

    all_keys = list(shared)
    all_vecs = list(combined)

    if backfill and pca is not None:
        if only_a:
            mat_oa = normalize(np.array([kv_a[k] for k in only_a], dtype=np.float32), norm="l2")
            zero_b = np.zeros((len(only_a), dim_b), dtype=np.float32)
            proj = pca.transform(np.hstack([alpha * mat_oa, (1 - alpha) * zero_b]))
            all_keys.extend(only_a)
            all_vecs.extend(proj)
            print(f"  Backfilled {len(only_a)} from A only")

        if only_b:
            mat_ob = normalize(np.array([kv_b[k] for k in only_b], dtype=np.float32), norm="l2")
            zero_a = np.zeros((len(only_b), dim_a), dtype=np.float32)
            proj = pca.transform(np.hstack([alpha * zero_a, (1 - alpha) * mat_ob]))
            all_keys.extend(only_b)
            all_vecs.extend(proj)
            print(f"  Backfilled {len(only_b)} from B only")

    return all_keys, np.array(all_vecs, dtype=np.float32)


def fuse_weighted_average(
    kv_a: KeyedVectors,
    kv_b: KeyedVectors,
    shared: list[str],
    only_a: list[str],
    only_b: list[str],
    alpha: float,
) -> tuple[list[str], np.ndarray]:
    """Fuse via weighted average of L2-normalized vectors.

    Requires both streams to have the same dimensionality.
    """
    assert kv_a.vector_size == kv_b.vector_size, (
        f"Dimension mismatch: A={kv_a.vector_size}, B={kv_b.vector_size}"
    )

    all_keys = []
    all_vecs = []

    # Shared: weighted average of normalized vectors
    if shared:
        mat_a = normalize(np.array([kv_a[k] for k in shared], dtype=np.float32), norm="l2")
        mat_b = normalize(np.array([kv_b[k] for k in shared], dtype=np.float32), norm="l2")
        avg = alpha * mat_a + (1 - alpha) * mat_b
        all_keys.extend(shared)
        all_vecs.extend(avg)

    # A-only: use A vectors directly (normalized)
    if only_a:
        mat_oa = normalize(np.array([kv_a[k] for k in only_a], dtype=np.float32), norm="l2")
        all_keys.extend(only_a)
        all_vecs.extend(mat_oa)
        print(f"  Included {len(only_a)} cards from A only")

    # B-only: use B vectors directly (normalized)
    if only_b:
        mat_ob = normalize(np.array([kv_b[k] for k in only_b], dtype=np.float32), norm="l2")
        all_keys.extend(only_b)
        all_vecs.extend(mat_ob)
        print(f"  Included {len(only_b)} cards from B only")

    print(
        f"\nWeighted average: {len(shared)} shared (alpha={alpha}), "
        f"{len(only_a)} A-only, {len(only_b)} B-only -> {len(all_keys)} total"
    )

    return all_keys, np.array(all_vecs, dtype=np.float32)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fuse two embedding streams")
    parser.add_argument("--stream-a", type=Path, required=True, help="Structural embedding .wv")
    parser.add_argument("--stream-b", type=Path, required=True, help="Functional embedding .wv")
    parser.add_argument("--output", type=Path, required=True, help="Output .wv file")
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.5,
        help="Weight for stream A (1-alpha for stream B, default: 0.5)",
    )
    parser.add_argument("--dim", type=int, default=128, help="Output dimension (concat method)")
    parser.add_argument(
        "--method",
        choices=["concat", "average"],
        default="concat",
        help="Fusion method: concat+PCA or weighted average (default: concat)",
    )
    parser.add_argument(
        "--no-backfill",
        action="store_true",
        help="Only include cards in both streams (concat method only)",
    )
    parser.add_argument(
        "--test-set",
        type=Path,
        default=Path("data/test_set_annotated_magic.json"),
        help="Annotated test set for nDCG evaluation",
    )
    args = parser.parse_args()

    # Load streams
    print(f"Loading stream A (structural): {args.stream_a}")
    kv_a = KeyedVectors.load(str(args.stream_a))
    print(f"  {len(kv_a)} cards, dim={kv_a.vector_size}")

    print(f"Loading stream B (functional): {args.stream_b}")
    kv_b = KeyedVectors.load(str(args.stream_b))
    print(f"  {len(kv_b)} cards, dim={kv_b.vector_size}")

    # Vocab sets (filter Card_XXXX noise)
    numeric_id = re.compile(r"^Card_\d+$")
    vocab_a = {k for k in kv_a.key_to_index if not numeric_id.match(k)}
    vocab_b = {k for k in kv_b.key_to_index if not numeric_id.match(k)}
    shared = sorted(vocab_a & vocab_b)
    only_a = sorted(vocab_a - vocab_b)
    only_b = sorted(vocab_b - vocab_a)

    n_filt = (len(kv_a) - len(vocab_a)) + (len(kv_b) - len(vocab_b))
    if n_filt:
        print(f"  Filtered {n_filt} Card_XXXX IDs")

    print(f"\nVocab: {len(shared)} shared, {len(only_a)} A-only, {len(only_b)} B-only")

    if len(shared) < 100:
        print("Error: too few shared cards", file=sys.stderr)
        return 1

    # Fuse
    if args.method == "concat":
        all_keys, all_vecs = fuse_concat_pca(
            kv_a,
            kv_b,
            shared,
            only_a,
            only_b,
            args.alpha,
            args.dim,
            not args.no_backfill,
        )
    else:
        all_keys, all_vecs = fuse_weighted_average(
            kv_a,
            kv_b,
            shared,
            only_a,
            only_b,
            args.alpha,
        )

    # Save
    args.output.parent.mkdir(parents=True, exist_ok=True)
    kv_out = KeyedVectors(vector_size=all_vecs.shape[1])
    kv_out.add_vectors(all_keys, all_vecs)
    kv_out.save(str(args.output))
    print(f"\nSaved {len(all_keys)} embeddings (dim={all_vecs.shape[1]}) to {args.output}")

    # Quality evaluation
    print("\n" + "=" * 60)
    print(f"Quality pair evaluation (method={args.method}, alpha={args.alpha})")
    print("=" * 60)

    results_a = evaluate_quality(kv_a, "Stream A (structural)")
    results_b = evaluate_quality(kv_b, "Stream B (functional)")
    results_fused = evaluate_quality(kv_out, "Fused (two-stream)")

    # Summary table
    print("\n" + "=" * 70)
    print(f"{'Pair':<45} {'Struct':>7} {'Func':>7} {'Fused':>7}")
    print("-" * 70)
    for pair_key in results_a:
        sa = results_a[pair_key]
        sb = results_b[pair_key]
        sf = results_fused[pair_key]
        sa_s = f"{sa:+.3f}" if not np.isnan(sa) else "   N/A"
        sb_s = f"{sb:+.3f}" if not np.isnan(sb) else "   N/A"
        sf_s = f"{sf:+.3f}" if not np.isnan(sf) else "   N/A"
        print(f"  {pair_key:<43} {sa_s:>7} {sb_s:>7} {sf_s:>7}")
    print("=" * 70)

    # nDCG evaluation
    print("\n" + "=" * 60)
    print("nDCG evaluation")
    print("=" * 60)
    evaluate_ndcg(kv_a, args.test_set, "Stream A (structural)")
    evaluate_ndcg(kv_b, args.test_set, "Stream B (functional)")
    evaluate_ndcg(kv_out, args.test_set, "Fused (two-stream)")

    # Random-pair baseline
    combined_norm = normalize(all_vecs, norm="l2")
    rng = np.random.default_rng(42)
    n_sample = min(10_000, len(all_keys) * (len(all_keys) - 1) // 2)
    sims = []
    for _ in range(n_sample):
        i, j = rng.choice(len(all_keys), 2, replace=False)
        sims.append(np.dot(combined_norm[i], combined_norm[j]))
    sims_arr = np.array(sims)
    print(f"\nRandom-pair cosine sim: mean={sims_arr.mean():.4f}, std={sims_arr.std():.4f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
