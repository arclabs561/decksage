#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
Add NDCG@K metric to evaluation pipeline.

NDCG (Normalized Discounted Cumulative Gain) is better than P@K for ranking quality
because it accounts for result ordering and weights higher-ranked results more heavily.
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


def dcg_at_k(relevances: list[float], k: int) -> float:
    """Compute Discounted Cumulative Gain at rank k."""
    relevances = relevances[:k]
    if not relevances:
        return 0.0
    return sum(rel / np.log2(i + 2) for i, rel in enumerate(relevances))


def ndcg_at_k(relevances: list[float], k: int) -> float:
    """Compute Normalized Discounted Cumulative Gain at rank k."""
    dcg = dcg_at_k(relevances, k)
    # Ideal DCG (sorted relevances descending)
    ideal_relevances = sorted(relevances, reverse=True)
    idcg = dcg_at_k(ideal_relevances, k)
    return dcg / idcg if idcg > 0 else 0.0


def evaluate_with_ndcg(
    test_set: dict,
    similarity_fn: callable,
    top_k: int = 10,
    relevance_weights: dict[str, float] | None = None,
) -> dict:
    """
    Evaluate similarity function with NDCG@K metric.
    
    Args:
        test_set: Dict mapping query -> relevance labels
        similarity_fn: Function(query, k) -> list[(card, score)]
        top_k: Top K for evaluation
        relevance_weights: Dict mapping relevance level -> weight
        
    Returns:
        Dict with metrics including ndcg@k
    """
    if relevance_weights is None:
        relevance_weights = {
            "highly_relevant": 1.0,
            "relevant": 0.75,
            "somewhat_relevant": 0.5,
            "marginally_relevant": 0.25,
            "irrelevant": 0.0,
        }
    
    ndcg_scores = []
    p_at_k_scores = []
    mrr_scores = []
    
    for query, labels in test_set.items():
        try:
            # Get predictions
            predictions = similarity_fn(query, top_k)
            if not predictions:
                continue
            
            # Build relevance vector for top_k results
            relevances = []
            for card, _ in predictions[:top_k]:
                relevance = 0.0
                for level, weight in relevance_weights.items():
                    if card in labels.get(level, []):
                        relevance = weight
                        break
                relevances.append(relevance)
            
            # Compute NDCG@K
            ndcg = ndcg_at_k(relevances, top_k)
            ndcg_scores.append(ndcg)
            
            # Also compute P@K for comparison
            p_at_k = sum(1 for r in relevances if r > 0) / top_k
            p_at_k_scores.append(p_at_k)
            
            # Compute MRR
            mrr = 0.0
            for rank, (card, _) in enumerate(predictions, 1):
                if card in labels.get("highly_relevant", []) or card in labels.get("relevant", []):
                    mrr = 1.0 / rank
                    break
            mrr_scores.append(mrr)
            
        except Exception as e:
            print(f"Error evaluating query '{query}': {e}")
            continue
    
    return {
        "ndcg_at_k": float(np.mean(ndcg_scores)) if ndcg_scores else 0.0,
        "p_at_k": float(np.mean(p_at_k_scores)) if p_at_k_scores else 0.0,
        "mrr": float(np.mean(mrr_scores)) if mrr_scores else 0.0,
        "num_queries": len(ndcg_scores),
        "ndcg_scores": ndcg_scores,
        "p_at_k_scores": p_at_k_scores,
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate with NDCG@K metric")
    parser.add_argument("--test-set", type=str, required=True, help="Path to test set JSON")
    parser.add_argument("--embeddings", type=str, help="Path to embeddings (for baseline)")
    parser.add_argument("--top-k", type=int, default=10, help="Top K for evaluation")
    
    args = parser.parse_args()
    
    # Load test set
    from ml.utils.data_loading import load_test_set
    
    test_set_data = load_test_set(path=Path(args.test_set))
    test_set = test_set_data.get("queries", test_set_data) if isinstance(test_set_data, dict) else test_set_data
    
    print(f"Loaded {len(test_set)} queries")
    
    # Create similarity function
    if args.embeddings:
        from gensim.models import KeyedVectors
        
        embeddings = KeyedVectors.load(args.embeddings)
        
        def similarity_fn(query: str, k: int):
            if query not in embeddings:
                return []
            similar = embeddings.most_similar(query, topn=k)
            return [(card, float(score)) for card, score in similar]
    else:
        print("Error: --embeddings required for now")
        return 1
    
    # Evaluate
    print(f"\nEvaluating with NDCG@{args.top_k}...")
    results = evaluate_with_ndcg(test_set, similarity_fn, top_k=args.top_k)
    
    print(f"\nResults:")
    print(f"  NDCG@{args.top_k}: {results['ndcg_at_k']:.4f}")
    print(f"  P@{args.top_k}: {results['p_at_k']:.4f}")
    print(f"  MRR: {results['mrr']:.4f}")
    print(f"  Queries evaluated: {results['num_queries']}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

