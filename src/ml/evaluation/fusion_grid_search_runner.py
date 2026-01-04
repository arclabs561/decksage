#!/usr/bin/env python3
"""
Runner script: evaluate fusion weights on canonical test set (Magic by default).

Usage:
 uv run python src/ml/fusion_grid_search_runner.py \
 --embeddings data/embeddings/magic_39k_decks_pecanpy.wv \
 --pairs data/processed/pairs_large.csv \
 --game magic --step 0.1 --top-k 10
"""

from __future__ import annotations

import argparse
import json

from .fusion import FusionWeights, WeightedLateFusion
from .fusion_grid_search import grid_search_weights
from .utils.paths import PATHS


def load_test_set(game: str) -> dict:
    """Load test set (uses canonical implementation)."""
    from ml.utils.data_loading import load_test_set as canonical_load

    data = canonical_load(game=game)
    # Canonical file may have metadata wrapper
    if isinstance(data, dict) and "queries" in data:
        return data["queries"]
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Fusion grid search runner")
    parser.add_argument("--embeddings", type=str, required=True)
    parser.add_argument("--pairs", type=str, required=True)
    parser.add_argument("--game", type=str, default="magic", choices=["magic", "pokemon", "yugioh"])
    parser.add_argument("--step", type=float, default=0.1)
    parser.add_argument("--top-k", type=int, default=10)

    args = parser.parse_args()

    # Lazy imports to keep test discovery lean
    from gensim.models import KeyedVectors

    from .card_functional_tagger import FunctionalTagger
    from .similarity_methods import load_graph

    print("\nLoading models...")
    wv = KeyedVectors.load(args.embeddings)
    adj, _weights = load_graph(args.pairs, filter_lands=True)
    tagger = None
    if args.game == "magic":
        try:
            tagger = FunctionalTagger()
        except Exception as e:
            print(f" Warning: FunctionalTagger unavailable: {e}")

    test_set = load_test_set(args.game)
    print(f" Test queries: {len(test_set)}")

    def builder(weights: FusionWeights) -> WeightedLateFusion:
        # Limit candidate pool for performance during grid search
        return WeightedLateFusion(wv, adj, tagger, weights, candidate_topn=100)

    print("\nRunning grid search...")
    result = grid_search_weights(builder, test_set, step=args.step, top_k=args.top_k)

    print("\nBest weights:")
    print(
        f" embed={result.best_weights.embed:.2f}, jaccard={result.best_weights.jaccard:.2f}, functional={result.best_weights.functional:.2f}"
    )
    print(f" P@{args.top_k}: {result.best_score:.4f}")

    # Save summary
    out_dir = PATHS.experiments
    out_dir.mkdir(exist_ok=True, parents=True)
    out = out_dir / "fusion_grid_search_latest.json"
    with open(out, "w") as f:
        json.dump(
            {
                "embeddings": args.embeddings,
                "pairs": args.pairs,
                "game": args.game,
                "step": args.step,
                "top_k": args.top_k,
                "best_weights": {
                    "embed": result.best_weights.embed,
                    "jaccard": result.best_weights.jaccard,
                    "functional": result.best_weights.functional,
                },
                "best_score": result.best_score,
            },
            f,
            indent=2,
        )
    print(f"\nSaved: {out}")

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
