#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["gensim>=4.3.0", "numpy<2.0.0", "pandas", "scikit-learn"]
# ///
"""
Fuse structural embeddings (PecanPy/node2vec) with card attribute features.

Creates a combined embedding via weighted concatenation + PCA projection.
The resulting .wv file can be evaluated with compare_all.py.

Usage:
    PYTHONPATH=src .venv/bin/python scripts/training/fuse_embeddings.py \
        --embeddings data/embeddings/pokemon_blended.wv \
        --card-attrs data/processed/card_attributes_pokemon.csv \
        --output data/embeddings/pokemon_fused.wv \
        --alpha 0.7 --dim 128
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from gensim.models import KeyedVectors
from sklearn.decomposition import PCA
from sklearn.preprocessing import normalize


def load_card_features(path: Path) -> tuple[dict[str, np.ndarray], int]:
    """Load card attributes and encode as feature vectors.

    Returns dict mapping card name -> feature vector, and feature dimension.
    """
    df = pd.read_csv(path)
    if "name" not in df.columns:
        print(f"Error: {path} has no 'name' column", file=sys.stderr)
        sys.exit(1)

    feature_cols = []

    # Encode 'type' as one-hot (top 15 type words)
    if "type" in df.columns:
        type_words: list[str] = []
        for val in df["type"].dropna():
            type_words.extend(str(val).split())
        from collections import Counter
        top_types = [w for w, _ in Counter(type_words).most_common(15)]
        for t in top_types:
            col = f"type_{t}"
            df[col] = df["type"].fillna("").apply(lambda x, t=t: 1.0 if t in str(x) else 0.0)
            feature_cols.append(col)

    # Encode 'colors' as multi-hot
    if "colors" in df.columns:
        color_vals = set()
        for val in df["colors"].dropna():
            for c in str(val).split(","):
                c = c.strip()
                if c:
                    color_vals.add(c)
        top_colors = sorted(color_vals)[:15]
        for c in top_colors:
            col = f"color_{c}"
            df[col] = df["colors"].fillna("").apply(lambda x, c=c: 1.0 if c in str(x) else 0.0)
            feature_cols.append(col)

    # Encode 'rarity' as one-hot
    if "rarity" in df.columns:
        top_rarities = df["rarity"].dropna().value_counts().head(6).index.tolist()
        for r in top_rarities:
            col = f"rarity_{r}"
            df[col] = (df["rarity"] == r).astype(float)
            feature_cols.append(col)

    # Numeric columns
    for num_col in ["cmc", "power", "toughness"]:
        if num_col in df.columns:
            vals = pd.to_numeric(df[num_col], errors="coerce").fillna(0.0)
            # Normalize to [0, 1]
            max_val = vals.max()
            if max_val > 0:
                vals = vals / max_val
            df[f"num_{num_col}"] = vals
            feature_cols.append(f"num_{num_col}")

    # Encode 'keywords' as multi-hot (top 30)
    if "keywords" in df.columns:
        kw_counter: dict[str, int] = {}
        for val in df["keywords"].dropna():
            for kw in str(val).split(","):
                kw = kw.strip().lower()
                if kw and len(kw) > 2:
                    kw_counter[kw] = kw_counter.get(kw, 0) + 1
        top_kws = sorted(kw_counter, key=kw_counter.get, reverse=True)[:30]
        for kw in top_kws:
            col = f"kw_{kw}"
            df[col] = df["keywords"].fillna("").apply(
                lambda x, kw=kw: 1.0 if kw in str(x).lower() else 0.0
            )
            feature_cols.append(col)

    if not feature_cols:
        print("Error: no usable feature columns found", file=sys.stderr)
        sys.exit(1)

    # Build feature matrix
    feat_matrix = df[feature_cols].values.astype(np.float32)
    names = df["name"].tolist()
    name_to_feat = {}
    for i, name in enumerate(names):
        name_to_feat[name] = feat_matrix[i]

    return name_to_feat, len(feature_cols)


def main():
    parser = argparse.ArgumentParser(description="Fuse structural embeddings with card attributes")
    parser.add_argument("--embeddings", type=Path, required=True, help="Input .wv file (PecanPy, etc)")
    parser.add_argument("--card-attrs", type=Path, required=True, help="Card attributes CSV")
    parser.add_argument("--output", type=Path, required=True, help="Output .wv file")
    parser.add_argument("--alpha", type=float, default=0.7,
                        help="Weight for structural embeddings (1-alpha for attributes, default: 0.7)")
    parser.add_argument("--dim", type=int, default=128,
                        help="Output embedding dimension after PCA (default: 128)")
    args = parser.parse_args()

    # Load structural embeddings
    print(f"Loading structural embeddings from {args.embeddings}...")
    kv = KeyedVectors.load(str(args.embeddings))
    vocab = list(kv.key_to_index.keys())
    struct_dim = kv.vector_size
    print(f"  {len(vocab)} cards, dim={struct_dim}")

    # Load card features
    print(f"Loading card attributes from {args.card_attrs}...")
    name_to_feat, feat_dim = load_card_features(args.card_attrs)
    print(f"  {len(name_to_feat)} cards, feature_dim={feat_dim}")

    # Match cards in both sources
    matched = [name for name in vocab if name in name_to_feat]
    print(f"  Matched: {len(matched)}/{len(vocab)} ({100*len(matched)/len(vocab):.1f}%)")

    if len(matched) < 10:
        print("Error: too few matched cards", file=sys.stderr)
        return 1

    # Build matrices
    struct_matrix = np.array([kv[name] for name in matched], dtype=np.float32)
    feat_matrix = np.array([name_to_feat[name] for name in matched], dtype=np.float32)

    # L2 normalize each source
    struct_norm = normalize(struct_matrix, norm='l2')
    feat_norm = normalize(feat_matrix, norm='l2')

    # Weighted concatenation
    combined = np.hstack([
        args.alpha * struct_norm,
        (1 - args.alpha) * feat_norm,
    ])
    print(f"  Combined shape: {combined.shape} (alpha={args.alpha})")

    # PCA to target dimension
    target_dim = min(args.dim, combined.shape[1], combined.shape[0])
    if combined.shape[1] > target_dim:
        print(f"  PCA: {combined.shape[1]} -> {target_dim}")
        pca = PCA(n_components=target_dim)
        combined = pca.fit_transform(combined)
        explained = sum(pca.explained_variance_ratio_)
        print(f"  Explained variance: {explained:.3f}")

    # Save as KeyedVectors
    out_kv = KeyedVectors(vector_size=combined.shape[1])
    out_kv.add_vectors(matched, combined)
    out_kv.save(str(args.output))
    print(f"\nSaved {len(matched)} fused embeddings (dim={combined.shape[1]}) to {args.output}")

    # Quality check
    rng = np.random.default_rng(42)
    n_pairs = min(10000, len(matched) * (len(matched) - 1) // 2)
    sims = []
    combined_norm = normalize(combined, norm='l2')
    for _ in range(n_pairs):
        i, j = rng.choice(len(matched), 2, replace=False)
        sims.append(np.dot(combined_norm[i], combined_norm[j]))
    sims_arr = np.array(sims)
    print(f"  Random-pair cosine sim: mean={sims_arr.mean():.4f}, std={sims_arr.std():.4f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
