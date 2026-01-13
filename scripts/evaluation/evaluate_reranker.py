#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "numpy>=1.24.0",
#     "pandas>=2.0.0",
# ]
# ///
"""
Evaluate learned reranker vs manual fusion.

Compares performance of:
1. Manual fusion (weighted/RRF)
2. Learned reranking
3. Two-stage pipeline (retrieve → rerank)
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
from gensim.models import KeyedVectors

from ml.reranking.hybrid_search import HybridSearchWithReranking
from ml.reranking.learned_reranker import LearnedReranker
from ml.similarity.fusion import FusionWeights, WeightedLateFusion
from ml.similarity.similarity_methods import load_graph
from ml.utils.data_loading import load_card_attributes, load_test_set
from ml.utils.evaluation import compute_precision_at_k
from ml.utils.paths import PATHS


def evaluate_method(
    test_set: dict,
    similarity_fn,
    method_name: str,
    top_k: int = 10,
) -> dict:
    """
    Evaluate a similarity method on test set.

    Args:
        test_set: Test set dictionary
        similarity_fn: Function that takes (query, k) and returns list of (card, score) tuples
        method_name: Name of method for logging
        top_k: Top k results to evaluate

    Returns:
        Dictionary with evaluation metrics
    """
    scores = []
    total = len(test_set)

    for i, (query, labels) in enumerate(test_set.items(), 1):
        if i % 10 == 0 or i == 1:
            print(f"  Progress: {i}/{total} queries ({i / total * 100:.1f}%)")
        try:
            predictions = similarity_fn(query, top_k)
            if not predictions:
                continue

            pred_cards = [card for card, _ in predictions]

            if isinstance(labels, dict):
                labels_dict = labels
            else:
                labels_dict = {
                    "highly_relevant": labels if isinstance(labels, list) else [],
                    "relevant": [],
                    "somewhat_relevant": [],
                    "marginally_relevant": [],
                    "irrelevant": [],
                }

            p_at_k = compute_precision_at_k(pred_cards, labels_dict, k=top_k)
            scores.append(p_at_k)

        except Exception as e:
            print(f"  Warning: Error evaluating query '{query}': {e}")
            continue

    p_at_k_mean = float(np.mean(scores)) if scores else 0.0
    p_at_k_std = float(np.std(scores)) if scores else 0.0

    return {
        "method": method_name,
        "p_at_k": p_at_k_mean,
        "p_at_k_std": p_at_k_std,
        "num_queries": len(scores),
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate learned reranker")
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
        "--reranker-model",
        type=str,
        default="models/reranker.pkl",
        help="Path to trained reranker model",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Top k results to evaluate",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="Limit number of queries to evaluate (for faster testing)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="experiments/reranker_evaluation.json",
        help="Path to save evaluation results",
    )
    parser.add_argument(
        "--aggregator",
        type=str,
        choices=["rrf", "weighted", "isr"],
        default="rrf",
        help="Aggregator for manual fusion",
    )

    args = parser.parse_args()

    # Load data
    print("Loading data...")
    test_set = load_test_set(path=Path(args.test_set))
    if isinstance(test_set, dict) and "queries" in test_set:
        test_set = test_set["queries"]

    # Sample queries if requested
    if args.sample_size and args.sample_size < len(test_set):
        import random

        random.seed(42)  # Reproducible sampling
        queries = list(test_set.keys())
        sampled_queries = random.sample(queries, args.sample_size)
        test_set = {q: test_set[q] for q in sampled_queries}
        print(f"  Sampled {len(test_set)} queries from {len(queries)} total")

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

    # Create manual fusion instance
    weights = FusionWeights().normalized()
    fusion = WeightedLateFusion(
        embeddings=embeddings,
        adj=adj,
        weights=weights,
        aggregator=args.aggregator,
        card_data=card_attrs,
    )

    results = {}

    # 1. Manual fusion baseline
    print(f"\nEvaluating manual fusion ({args.aggregator})...")

    def manual_fn(query: str, k: int):
        return fusion.similar(query, k)

    results["manual_fusion"] = evaluate_method(
        test_set, manual_fn, f"manual_{args.aggregator}", args.top_k
    )
    print(f"  P@{args.top_k}: {results['manual_fusion']['p_at_k']:.4f}")

    # 2. Learned reranking (if model exists)
    reranker_path = Path(args.reranker_model)
    if reranker_path.exists():
        print("\nEvaluating learned reranking...")

        try:
            reranker = LearnedReranker()
            reranker.load(reranker_path)

            # Use smaller retrieve size for faster evaluation
            retrieve_size = min(20, args.top_k * 2)  # Retrieve 2x more than final, max 20
            print(f"  Using retrieve_size={retrieve_size}, final_size={args.top_k}")
            hybrid_search = HybridSearchWithReranking(
                retriever=fusion,
                reranker=reranker,
                top_k_retrieve=retrieve_size,
                top_k_final=args.top_k,
                use_reranking=True,
            )

            def reranked_fn(query: str, k: int):
                return hybrid_search.search(query)

            results["learned_reranking"] = evaluate_method(
                test_set, reranked_fn, "learned_reranking", args.top_k
            )
            print(f"  P@{args.top_k}: {results['learned_reranking']['p_at_k']:.4f}")

            # Compare
            improvement = (
                results["learned_reranking"]["p_at_k"] - results["manual_fusion"]["p_at_k"]
            )
            print(
                f"\n  Improvement: {improvement:+.4f} ({improvement / results['manual_fusion']['p_at_k'] * 100:+.2f}%)"
            )

        except Exception as e:
            print(f"  Error loading/evaluating reranker: {e}")
            print("  Skipping learned reranking evaluation")
    else:
        print(f"\nReranker model not found at {reranker_path}")
        print("  Train a reranker first: python scripts/optimization/train_reranker.py")

    # Print summary
    print(f"\n{'=' * 80}")
    print("Evaluation Summary")
    print(f"{'=' * 80}")
    print(f"{'Method':<30} {'P@{args.top_k}':<15} {'Std':<15} {'Queries':<10}")
    print(f"{'-' * 80}")

    for result in results.values():
        print(
            f"{result['method']:<30} "
            f"{result['p_at_k']:<15.4f} "
            f"{result['p_at_k_std']:<15.4f} "
            f"{result['num_queries']:<10}"
        )

    # Save results
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved results to {output_path}")


if __name__ == "__main__":
    main()
