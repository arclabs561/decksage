#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "numpy>=1.24.0",
#     "gensim>=4.3.0",
#     "scikit-learn>=1.3.0",
#     "pandas>=2.0.0",
# ]
# ///
"""
Sweep fusion alpha per game to find optimal structural/attribute blend.

Fuses structural embeddings (PecanPy v5) with attribute embeddings at
different alpha values and evaluates each with per-mode nDCG on the
annotated test set. No retraining needed -- just PCA fusion at different
weights.

The v5 pipeline uses alpha=0.7 (70% structural, 30% attribute). This
sweep tests alpha in {0.3, 0.5, 0.7, 0.9} per game.

Usage:
    uv run scripts/training/sweep_fusion_alpha.py --game magic
    uv run scripts/training/sweep_fusion_alpha.py --all-games
    uv run scripts/training/sweep_fusion_alpha.py --game magic --alphas 0.3,0.5,0.7,0.9
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from gensim.models import KeyedVectors
from sklearn.decomposition import PCA

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
DATA_DIR = PROJECT_ROOT / "data"

# Structural (PecanPy) embeddings -- trained on co-occurrence graph
STRUCTURAL_EMBEDDINGS = {
    "magic": "magic_v7_spectral_mu35",
    "pokemon": "pokemon_v7_fused",
    "yugioh": "yugioh_v7_spectral_mu3",
}

# Card attribute CSVs (one-hot/multi-hot features)
CARD_ATTRS = {
    "magic": "card_attributes_magic_enriched.csv",
    "pokemon": "card_attributes_pokemon_enriched.csv",
    "yugioh": "card_attributes_yugioh_enriched.csv",
}

DEFAULT_ALPHAS = [0.3, 0.5, 0.7, 0.9]


def load_wv(name: str) -> KeyedVectors | None:
    """Load a .wv file by name."""
    path = DATA_DIR / "embeddings" / f"{name}.wv"
    if path.exists():
        return KeyedVectors.load(str(path))
    return None


def load_card_features(game: str) -> dict[str, np.ndarray] | None:
    """Load card attribute features using the same encoding as fuse_embeddings.py."""
    csv_name = CARD_ATTRS.get(game)
    if not csv_name:
        return None
    csv_path = DATA_DIR / "processed" / csv_name
    if not csv_path.exists():
        return None

    # Import the feature encoder from fuse_embeddings.py
    fuse_script = PROJECT_ROOT / "scripts" / "training" / "fuse_embeddings.py"
    if fuse_script.exists():
        import importlib.util

        spec = importlib.util.spec_from_file_location("fuse_emb", fuse_script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        features, dim = mod.load_card_features(csv_path)
        return features
    return None


def fuse(
    structural: KeyedVectors,
    attr_features: dict[str, np.ndarray],
    alpha: float,
    target_dim: int = 128,
    seed: int = 42,
) -> KeyedVectors:
    """Fuse structural embeddings with card attribute features at given alpha.

    alpha=1.0 means 100% structural, alpha=0.0 means 100% attribute.
    """
    # Find common vocab
    common = [k for k in structural.key_to_index if k in attr_features]
    if not common:
        raise ValueError("No common vocab between structural embeddings and card features")

    # Stack vectors
    s_vecs = np.array([structural[k] for k in common])
    a_vecs = np.array([attr_features[k] for k in common])

    # Normalize each stream
    s_norms = np.linalg.norm(s_vecs, axis=1, keepdims=True)
    a_norms = np.linalg.norm(a_vecs, axis=1, keepdims=True)
    s_vecs = s_vecs / np.maximum(s_norms, 1e-10)
    a_vecs = a_vecs / np.maximum(a_norms, 1e-10)

    # Weighted concatenation
    concat = np.hstack([s_vecs * alpha, a_vecs * (1 - alpha)])

    # PCA to target dim
    pca = PCA(n_components=target_dim, random_state=seed)
    fused = pca.fit_transform(concat)

    # Build KeyedVectors
    kv = KeyedVectors(vector_size=target_dim)
    kv.add_vectors(common, fused)
    return kv


def eval_ndcg(wv: KeyedVectors, game: str, k: int = 10) -> dict:
    """Evaluate per-mode nDCG on the annotated test set."""
    test_path = DATA_DIR / "test_sets" / f"annotated_{game}_v2.json"
    if not test_path.exists():
        return {"error": "no test set"}

    with open(test_path) as f:
        data = json.load(f)

    queries = data.get("queries", {})
    MODE_SCORE_FIELD = {
        "substitute": "functional_score",
        "synergy": "synergy_score",
        "meta": "meta_relevance",
    }

    def _dcg(rels, k_):
        r = np.array(rels[:k_], dtype=float)
        if r.size == 0:
            return 0.0
        return float(np.sum(r / np.log2(np.arange(2, r.size + 2))))

    def _ndcg(rels, ideal, k_):
        idcg = _dcg(sorted(ideal, reverse=True), k_)
        return _dcg(rels, k_) / idcg if idcg > 0 else 0.0

    results = {}
    for mode, field in MODE_SCORE_FIELD.items():
        scores = []
        for qname, qdata in queries.items():
            annotations = qdata.get("annotations", [])
            if not annotations or qname not in wv:
                continue
            gt = {}
            for ann in annotations:
                c = ann.get("candidate", "")
                s = ann.get(field)
                if s is not None and c:
                    gt[c] = float(s)
            if not gt or max(list(gt.values())[:k]) == 0:
                continue
            try:
                neighbors = wv.most_similar(qname, topn=k)
            except KeyError:
                continue
            rels = [gt.get(c, 0.0) for c, _ in neighbors]
            ideal = sorted(gt.values(), reverse=True)
            scores.append(_ndcg(rels, ideal, k))

        results[mode] = {
            "ndcg": float(np.mean(scores)) if scores else 0.0,
            "n": len(scores),
        }

    # Overall
    all_scores = []
    for qname, qdata in queries.items():
        annotations = qdata.get("annotations", [])
        if not annotations or qname not in wv:
            continue
        gt = {
            ann.get("candidate", ""): float(ann.get("similarity_score", 0))
            for ann in annotations
            if ann.get("similarity_score") is not None and ann.get("candidate")
        }
        if not gt:
            continue
        try:
            neighbors = wv.most_similar(qname, topn=k)
        except KeyError:
            continue
        rels = [gt.get(c, 0.0) for c, _ in neighbors]
        ideal = sorted(gt.values(), reverse=True)
        if max(ideal[:k]) > 0:
            all_scores.append(_ndcg(rels, ideal, k))

    results["overall"] = {
        "ndcg": float(np.mean(all_scores)) if all_scores else 0.0,
        "n": len(all_scores),
    }

    return results


def sweep_game(game: str, alphas: list[float]) -> list[dict]:
    """Sweep fusion alpha for one game."""
    structural = load_wv(STRUCTURAL_EMBEDDINGS.get(game, ""))
    if structural is None:
        print(f"  Structural embeddings not found for {game}")
        return []

    attr_features = load_card_features(game)
    if attr_features is None:
        print(f"  Card attribute features not found for {game}")
        print(f"  Evaluating structural-only (alpha=1.0)")
        result = eval_ndcg(structural, game)
        return [{"alpha": 1.0, "vocab": len(structural), **result}]

    first_key = next(iter(attr_features))
    attr_dim = attr_features[first_key].shape[0]
    common = len(set(structural.key_to_index) & set(attr_features.keys()))
    print(f"  Structural: {len(structural)} cards, {structural.vector_size}D")
    print(f"  Attributes: {len(attr_features)} cards, {attr_dim}D features")
    print(f"  Common vocab: {common}")

    # Also eval current v5_fused for comparison
    current_fused = load_wv(f"{game}_v5_fused")
    if current_fused:
        metrics = eval_ndcg(current_fused, game)
        ov = metrics.get("overall", {}).get("ndcg", 0)
        print(f"  CURRENT v5_fused: overall={ov:.4f}")

    results = []
    for alpha in alphas:
        t0 = time.monotonic()
        fused = fuse(structural, attr_features, alpha)
        fuse_time = time.monotonic() - t0

        t0 = time.monotonic()
        metrics = eval_ndcg(fused, game)
        eval_time = time.monotonic() - t0

        entry = {
            "alpha": alpha,
            "vocab": len(fused),
            "fuse_ms": round(fuse_time * 1000),
            "eval_ms": round(eval_time * 1000),
            **metrics,
        }
        results.append(entry)

        overall = metrics.get("overall", {}).get("ndcg", 0)
        sub = metrics.get("substitute", {}).get("ndcg", 0)
        syn = metrics.get("synergy", {}).get("ndcg", 0)
        meta = metrics.get("meta", {}).get("ndcg", 0)
        print(
            f"  alpha={alpha:.1f}: overall={overall:.4f} sub={sub:.4f} syn={syn:.4f} meta={meta:.4f} ({fuse_time + eval_time:.1f}s)"
        )

    return results


def main():
    parser = argparse.ArgumentParser(description="Sweep fusion alpha per game")
    parser.add_argument("--game", default="magic", choices=["magic", "pokemon", "yugioh"])
    parser.add_argument("--all-games", action="store_true")
    parser.add_argument("--alphas", default=None, help="Comma-separated alpha values")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    alphas = DEFAULT_ALPHAS
    if args.alphas:
        alphas = [float(a) for a in args.alphas.split(",")]

    games = ["magic", "pokemon", "yugioh"] if args.all_games else [args.game]
    all_results = {}

    for game in games:
        print(f"\n{'=' * 60}")
        print(f"{game.upper()} fusion alpha sweep")
        results = sweep_game(game, alphas)
        all_results[game] = results

        if results:
            best = max(results, key=lambda r: r.get("overall", {}).get("ndcg", 0))
            print(f"\n  Best alpha: {best['alpha']} (overall nDCG={best['overall']['ndcg']:.4f})")

    if args.json:
        print(json.dumps(all_results, indent=2))

    # Save results
    out_path = DATA_DIR / "embeddings" / "fusion_alpha_sweep.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
