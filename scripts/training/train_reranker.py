#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = [
#     "numpy>=1.26.0",
#     "gensim>=4.3.0",
#     "scikit-learn>=1.4.0",
# ]
# ///
"""
Train a reranker on top of embeddings using annotation pairs.

Takes embedding cosine similarities as features, learns to predict
the actual substitutability/similarity score from annotations.
This bridges the gap between embedding space and human judgment.

Uses a dedicated annotation split: 80% train, 20% eval (held out
from the embedding eval). This is NOT the same eval set used for
embedding nDCG -- it's a separate annotation-supervised reranker.

Usage:
    uv run scripts/training/train_reranker.py --game magic
    uv run scripts/training/train_reranker.py --game magic --embeddings v5_fused,metapath2vec_sweep_80ep,cleora_1iter
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

import numpy as np
from gensim.models import KeyedVectors
from sklearn.linear_model import Ridge
from sklearn.metrics import ndcg_score
from sklearn.model_selection import train_test_split

if not sys.stdout.isatty():
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def load_pairs(game: str) -> list[dict]:
    """Load annotated pairs with similarity scores."""
    path = DATA_DIR / "test_sets" / f"annotated_{game}_v2.json"
    if not path.exists():
        return []

    with open(path) as f:
        data = json.load(f)

    pairs = []
    for qname, qdata in data.get("queries", {}).items():
        for ann in qdata.get("annotations", []):
            candidate = ann.get("candidate", "")
            sim = ann.get("similarity_score")
            func = ann.get("functional_score")
            sub = ann.get("substitutability")
            if candidate and sim is not None:
                pairs.append({
                    "query": qname,
                    "candidate": candidate,
                    "similarity": float(sim),
                    "functional": float(func) if func is not None else None,
                    "substitutability": float(sub) if sub is not None else None,
                })
    return pairs


def compute_features(
    query: str, candidate: str, embeddings: dict[str, KeyedVectors]
) -> list[float]:
    """Compute feature vector from multiple embedding sources."""
    features = []
    for name, kv in embeddings.items():
        if query in kv and candidate in kv:
            sim = float(kv.similarity(query, candidate))
            features.append(sim)
        else:
            features.append(0.0)  # missing = neutral
    return features


def main() -> int:
    parser = argparse.ArgumentParser(description="Train embedding reranker")
    parser.add_argument("--game", default="magic")
    parser.add_argument(
        "--embeddings", type=str,
        default="v5_fused,metapath2vec_sweep_80ep,cleora_1iter,text_e5",
        help="Comma-separated embedding names to use as features",
    )
    parser.add_argument("--target", default="similarity",
                        choices=["similarity", "functional", "substitutability"],
                        help="Which annotation score to predict")
    args = parser.parse_args()

    emb_names = [e.strip() for e in args.embeddings.split(",")]

    print(f"{'=' * 60}")
    print(f"Reranker [{args.game}] target={args.target}")
    print(f"  features: {emb_names}")
    print(f"{'=' * 60}")

    # Load embeddings
    print(f"\n[1/4] Loading embeddings...")
    embeddings = {}
    for name in emb_names:
        path = DATA_DIR / "embeddings" / f"{args.game}_{name}.wv"
        if path.exists():
            kv = KeyedVectors.load(str(path))
            embeddings[name] = kv
            print(f"  {name}: {len(kv)} cards")
        else:
            print(f"  {name}: NOT FOUND, skipping")

    if not embeddings:
        print("No embeddings loaded")
        return 1

    # Load annotation pairs
    print(f"\n[2/4] Loading annotation pairs...")
    pairs = load_pairs(args.game)
    print(f"  {len(pairs)} pairs")

    # Build feature matrix
    print(f"\n[3/4] Building features...")
    X = []
    y = []
    valid_pairs = []
    for p in pairs:
        target = p.get(args.target)
        if target is None:
            continue
        features = compute_features(p["query"], p["candidate"], embeddings)
        if any(f != 0.0 for f in features):  # at least one embedding covers this pair
            X.append(features)
            y.append(target)
            valid_pairs.append(p)

    X = np.array(X)
    y = np.array(y)
    print(f"  {len(X)} valid pairs, {X.shape[1]} features")

    if len(X) < 100:
        print("Too few valid pairs for training")
        return 1

    # Train/eval split (80/20)
    X_train, X_test, y_train, y_test, pairs_train, pairs_test = train_test_split(
        X, y, valid_pairs, test_size=0.2, random_state=42
    )
    print(f"  Train: {len(X_train)}, Test: {len(X_test)}")

    # Train reranker (Ridge regression -- simple, interpretable)
    print(f"\n[4/4] Training reranker...")
    model = Ridge(alpha=1.0)
    model.fit(X_train, y_train)

    # Evaluate
    y_pred_train = model.predict(X_train)
    y_pred_test = model.predict(X_test)

    # Per-feature importance (Ridge coefficients)
    print(f"\n  Feature weights:")
    for name, coef in zip(embeddings.keys(), model.coef_):
        print(f"    {name}: {coef:.4f}")
    print(f"    intercept: {model.intercept_:.4f}")

    # Correlation
    from scipy.stats import spearmanr
    train_corr, _ = spearmanr(y_train, y_pred_train)
    test_corr, _ = spearmanr(y_test, y_pred_test)
    print(f"\n  Spearman correlation:")
    print(f"    Train: {train_corr:.4f}")
    print(f"    Test:  {test_corr:.4f}")

    # RMSE
    train_rmse = np.sqrt(np.mean((y_train - y_pred_train) ** 2))
    test_rmse = np.sqrt(np.mean((y_test - y_pred_test) ** 2))
    print(f"\n  RMSE:")
    print(f"    Train: {train_rmse:.4f}")
    print(f"    Test:  {test_rmse:.4f}")

    # Compare individual features vs combined
    print(f"\n  Individual feature correlations (test set):")
    for i, name in enumerate(embeddings.keys()):
        feat_corr, _ = spearmanr(y_test, X_test[:, i])
        print(f"    {name}: {feat_corr:.4f}")

    # Save model weights
    logs_dir = DATA_DIR / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "game": args.game,
        "target": args.target,
        "features": list(embeddings.keys()),
        "weights": {name: float(c) for name, c in zip(embeddings.keys(), model.coef_)},
        "intercept": float(model.intercept_),
        "train_corr": float(train_corr),
        "test_corr": float(test_corr),
        "train_rmse": float(train_rmse),
        "test_rmse": float(test_rmse),
        "n_train": len(X_train),
        "n_test": len(X_test),
    }
    out = logs_dir / f"{args.game}_reranker_run.json"
    with open(out, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n  Summary: {out}")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
