#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["gensim>=4.3.0", "numpy<2.0.0", "scikit-learn>=1.3.0"]
# ///
"""
PCA-whiten gensim KeyedVectors embeddings.

Applies PCA whitening (zero-mean + unit variance per component) to fix
overcomplete embedding spaces where random-pair cosine similarity is far
from zero. Optionally reduces dimensionality.

Usage:
    uv run scripts/training/whiten_embeddings.py \
        --input data/embeddings/magic_cleaned_v4.wv \
        --output data/embeddings/magic_whitened_v4.wv

    # With dimension reduction:
    uv run scripts/training/whiten_embeddings.py \
        --input data/embeddings/magic_cleaned_v4.wv \
        --output data/embeddings/magic_whitened_64d.wv \
        --dim 64

    # Evaluate quality pairs without saving:
    uv run scripts/training/whiten_embeddings.py \
        --input data/embeddings/magic_cleaned_v4.wv \
        --output data/embeddings/magic_whitened_v4.wv \
        --quality-pairs "Lightning Bolt,Fireball;Sol Ring,Arcane Signet"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from gensim.models import KeyedVectors
from sklearn.decomposition import PCA


def random_pair_cosine_stats(
    kv: KeyedVectors, n_samples: int = 10_000, seed: int = 42
) -> dict[str, float]:
    """Compute cosine similarity stats over random pairs."""
    rng = np.random.default_rng(seed)
    n = len(kv)
    indices = rng.integers(0, n, size=(n_samples, 2))
    # Skip self-pairs
    mask = indices[:, 0] != indices[:, 1]
    indices = indices[mask]

    vecs = kv.vectors
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-10)
    normed = vecs / norms

    a = normed[indices[:, 0]]
    b = normed[indices[:, 1]]
    sims = np.sum(a * b, axis=1)

    return {
        "mean": float(np.mean(sims)),
        "std": float(np.std(sims)),
        "min": float(np.min(sims)),
        "max": float(np.max(sims)),
        "median": float(np.median(sims)),
    }


def evaluate_quality_pairs(kv: KeyedVectors, pairs: list[tuple[str, str]]) -> list[dict]:
    """Evaluate cosine similarity for specific card pairs."""
    results = []
    for a, b in pairs:
        if a in kv and b in kv:
            sim = float(kv.similarity(a, b))
            results.append({"a": a, "b": b, "sim": sim, "status": "ok"})
        else:
            missing = []
            if a not in kv:
                missing.append(a)
            if b not in kv:
                missing.append(b)
            results.append({"a": a, "b": b, "sim": None, "status": f"missing: {missing}"})
    return results


def whiten_keyed_vectors(kv: KeyedVectors, dim: int | None = None) -> KeyedVectors:
    """Apply PCA whitening to KeyedVectors, optionally reducing dimensions."""
    original_dim = kv.vector_size
    target_dim = dim if dim is not None else original_dim

    if target_dim > original_dim:
        print(
            f"  WARNING: requested dim {target_dim} > original {original_dim}, "
            f"clamping to {original_dim}"
        )
        target_dim = original_dim

    pca = PCA(n_components=target_dim, whiten=True, random_state=42)
    whitened_vectors = pca.fit_transform(kv.vectors)

    variance_explained = float(np.sum(pca.explained_variance_ratio_))
    print(
        f"  Variance explained: {variance_explained:.4f} ({target_dim}/{original_dim} components)"
    )

    new_kv = KeyedVectors(vector_size=target_dim)
    new_kv.add_vectors(list(kv.index_to_key), whitened_vectors)

    return new_kv


def parse_quality_pairs(s: str) -> list[tuple[str, str]]:
    """Parse 'A,B;C,D' into [(A,B), (C,D)]."""
    pairs = []
    for pair_str in s.split(";"):
        pair_str = pair_str.strip()
        if not pair_str:
            continue
        parts = pair_str.split(",", 1)
        if len(parts) != 2:
            print(f"  WARNING: skipping malformed pair: {pair_str!r}")
            continue
        pairs.append((parts[0].strip(), parts[1].strip()))
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser(description="PCA-whiten gensim KeyedVectors embeddings")
    parser.add_argument("--input", required=True, type=Path, help="Input .wv file")
    parser.add_argument("--output", required=True, type=Path, help="Output .wv file")
    parser.add_argument(
        "--dim",
        type=int,
        default=None,
        help="Target dimensionality (default: keep original)",
    )
    parser.add_argument(
        "--quality-pairs",
        type=str,
        default=None,
        help='Semicolon-separated pairs: "A,B;C,D"',
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"ERROR: input file not found: {args.input}")
        return 1

    # Load
    print(f"Loading {args.input} ...")
    kv = KeyedVectors.load(str(args.input))
    print(f"  {len(kv)} vectors, {kv.vector_size}D")

    # Parse quality pairs
    quality_pairs: list[tuple[str, str]] = []
    if args.quality_pairs:
        quality_pairs = parse_quality_pairs(args.quality_pairs)

    # Before stats
    print("\n--- BEFORE whitening ---")
    before_stats = random_pair_cosine_stats(kv)
    print(
        f"  Random-pair cosine: mean={before_stats['mean']:.4f}  std={before_stats['std']:.4f}  "
        f"min={before_stats['min']:.4f}  max={before_stats['max']:.4f}"
    )

    if quality_pairs:
        print("  Quality pairs:")
        before_qp = evaluate_quality_pairs(kv, quality_pairs)
        for r in before_qp:
            if r["sim"] is not None:
                print(f"    {r['a']} <-> {r['b']}: {r['sim']:.4f}")
            else:
                print(f"    {r['a']} <-> {r['b']}: {r['status']}")

    # Whiten
    dim_label = f"{args.dim}D" if args.dim else f"{kv.vector_size}D (full)"
    print(f"\nWhitening to {dim_label} ...")
    whitened_kv = whiten_keyed_vectors(kv, dim=args.dim)

    # After stats
    print("\n--- AFTER whitening ---")
    after_stats = random_pair_cosine_stats(whitened_kv)
    print(
        f"  Random-pair cosine: mean={after_stats['mean']:.4f}  std={after_stats['std']:.4f}  "
        f"min={after_stats['min']:.4f}  max={after_stats['max']:.4f}"
    )

    if quality_pairs:
        print("  Quality pairs:")
        after_qp = evaluate_quality_pairs(whitened_kv, quality_pairs)
        for r in after_qp:
            if r["sim"] is not None:
                print(f"    {r['a']} <-> {r['b']}: {r['sim']:.4f}")
            else:
                print(f"    {r['a']} <-> {r['b']}: {r['status']}")

    # Summary
    print("\n--- DELTA ---")
    print(
        f"  Random-pair mean: {before_stats['mean']:.4f} -> {after_stats['mean']:.4f}  "
        f"(delta {after_stats['mean'] - before_stats['mean']:+.4f})"
    )

    # Save
    args.output.parent.mkdir(parents=True, exist_ok=True)
    whitened_kv.save(str(args.output))
    print(f"\nSaved to {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
