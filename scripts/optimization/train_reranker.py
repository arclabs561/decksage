#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "numpy>=1.24.0",
#     "pandas>=2.0.0",
# ]
# ///
"""
Train learned reranker on test set with comprehensive features.

Extracts features using extract_ltr_features and trains a LightGBM/XGBoost
model to learn optimal feature combination.
"""

import argparse
import json
import sys
from pathlib import Path


# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ml.utils.path_setup import setup_project_paths


setup_project_paths()

import numpy as np
import pandas as pd
from gensim.models import KeyedVectors

from ml.reranking.feature_extraction import extract_ltr_features
from ml.reranking.learned_reranker import LearnedReranker
from ml.similarity.fusion import FusionWeights, WeightedLateFusion
from ml.similarity.similarity_methods import load_graph
from ml.utils.data_loading import load_card_attributes, load_test_set
from ml.utils.paths import PATHS


def extract_training_data(
    test_set: dict,
    embeddings: KeyedVectors,
    adj: dict,
    card_attrs: dict | None,
    top_k: int = 100,
    sample_size: int | None = None,
) -> pd.DataFrame:
    """
    Extract training data with comprehensive features.

    Args:
        test_set: Test set dictionary
        embeddings: Embedding model
        adj: Adjacency dictionary
        card_attrs: Card attributes dictionary
        top_k: Number of candidates to consider per query
        sample_size: Optional sample size for test set

    Returns:
        DataFrame with query, candidate, features, and relevance
    """
    # Sample test set if requested
    if sample_size and sample_size < len(test_set):
        import random

        random.seed(42)
        test_items = list(test_set.items())
        test_set = dict(random.sample(test_items, sample_size))

    # Create fusion instance for feature extraction
    weights = FusionWeights().normalized()  # Use default weights
    fusion = WeightedLateFusion(
        embeddings=embeddings,
        adj=adj,
        weights=weights,
        aggregator="rrf",  # Use RRF for retrieval
        card_data=card_attrs,
    )

    rows = []

    for query, labels in test_set.items():
        # Get all relevant cards
        if isinstance(labels, dict):
            all_relevant = set()
            for level in [
                "highly_relevant",
                "relevant",
                "somewhat_relevant",
                "marginally_relevant",
            ]:
                all_relevant.update(labels.get(level, []))
        else:
            all_relevant = set(labels if isinstance(labels, list) else [])

        if not all_relevant:
            continue

        # Get candidates
        try:
            candidates = fusion._get_candidates(query)
            if not candidates:
                continue

            # Limit to top_k candidates
            if len(candidates) > top_k:
                # Get top candidates by manual fusion
                top_candidates = fusion.similar(query, k=top_k)
                # Extract card names from (card, score) tuples
                candidates = {c[0] if isinstance(c, (tuple, list)) else c for c in top_candidates}

            # Extract features for all candidates
            for candidate in candidates:
                # Relevance label
                relevance = 1.0 if candidate in all_relevant else 0.0

                # Extract comprehensive features
                features = extract_ltr_features(query, candidate, fusion, card_attrs)

                # Add query, candidate, and relevance
                row = {
                    "query": query,
                    "candidate": candidate,
                    "relevance": relevance,
                    **features,
                }
                rows.append(row)

        except Exception as e:
            print(f"  Warning: Error processing query '{query}': {e}")
            continue

    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description="Train learned reranker")
    parser.add_argument(
        "--test-set",
        type=str,
        default=str(PATHS.test_magic),
        help="Path to test set JSON file",
    )
    parser.add_argument(
        "--embeddings",
        type=str,
        default=str(PATHS.embeddings / "magic_128d_test_pecanpy.wv"),
        help="Path to embeddings file",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="models/reranker.pkl",
        help="Path to save trained model",
    )
    parser.add_argument(
        "--method",
        type=str,
        choices=["lightgbm", "xgboost"],
        default="lightgbm",
        help="Model method",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=100,
        help="Number of candidates to consider per query",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="Optional sample size for test set",
    )
    parser.add_argument(
        "--n-estimators",
        type=int,
        default=200,
        help="Number of estimators",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=6,
        help="Max depth",
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=0.05,
        help="Learning rate",
    )

    args = parser.parse_args()

    # Load data
    print("Loading data...")
    test_set = load_test_set(path=Path(args.test_set))
    if isinstance(test_set, dict) and "queries" in test_set:
        test_set = test_set["queries"]

    embeddings = KeyedVectors.load(str(args.embeddings))
    graph_result = load_graph()
    # load_graph returns (adj, weights) tuple
    if isinstance(graph_result, tuple):
        adj, _ = graph_result
    else:
        adj = graph_result
    card_attrs = load_card_attributes()

    print(f"  Test set: {len(test_set)} queries")
    print(f"  Embeddings: {len(embeddings)} vectors")
    print(f"  Graph: {len(adj)} nodes")
    print(f"  Card attributes: {len(card_attrs)} cards")

    # Extract training data
    print("\nExtracting training data with comprehensive features...")
    df = extract_training_data(test_set, embeddings, adj, card_attrs, args.top_k, args.sample_size)
    print(f"  Extracted {len(df)} training examples")
    print(f"  Features: {len(df.columns) - 3} (excluding query, candidate, relevance)")
    print(f"  Positive examples: {df['relevance'].sum()} ({df['relevance'].mean() * 100:.1f}%)")

    if len(df) == 0:
        print("  Error: No training data extracted")
        return

    # Train model
    print(f"\nTraining {args.method} reranker...")
    reranker = LearnedReranker()
    reranker.train(
        df,
        method=args.method,
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        learning_rate=args.learning_rate,
    )

    # Get feature importance
    importance = reranker.get_feature_importance()
    if importance:
        print("\nTop 10 most important features:")
        sorted_importance = sorted(importance.items(), key=lambda x: x[1], reverse=True)
        for feature, imp in sorted_importance[:10]:
            print(f"  {feature}: {imp:.4f}")

    # Save model
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    reranker.save(output_path)
    print(f"\nSaved reranker to {output_path}")

    # Save feature importance
    if importance:
        importance_path = output_path.with_suffix(".importance.json")
        # Convert numpy types to native Python types for JSON serialization
        importance_serializable = {
            k: float(v)
            if hasattr(v, "item")
            else int(v)
            if isinstance(v, (np.integer, np.int32, np.int64))
            else v
            for k, v in importance.items()
        }
        with open(importance_path, "w") as f:
            json.dump(importance_serializable, f, indent=2)
        print(f"Saved feature importance to {importance_path}")


if __name__ == "__main__":
    main()
