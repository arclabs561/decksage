#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "numpy>=1.24.0",
# ]
# ///
"""
Evaluate similarity system with NDCG@K metric.

NDCG (Normalized Discounted Cumulative Gain) is superior to P@K for ranking quality
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
from gensim.models import KeyedVectors

from ml.similarity.fusion import FusionWeights, WeightedLateFusion
from ml.similarity.similarity_methods import load_card_attributes_csv, load_graph
from ml.utils.data_loading import load_test_set
from ml.utils.evaluation_logger import log_evaluation_run
from ml.utils.paths import PATHS


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


def evaluate_method(
    test_set: dict,
    similarity_fn: callable,
    top_k: int = 10,
    method_name: str = "unknown",
) -> dict:
    """Evaluate similarity function with multiple metrics."""
    
    relevance_weights = {
        "highly_relevant": 1.0,
        "relevant": 0.75,
        "somewhat_relevant": 0.5,
        "marginally_relevant": 0.25,
        "irrelevant": 0.0,
    }
    
    ndcg_scores = []
    p_at_k_scores = []
    recall_at_k_scores = []
    mrr_scores = []
    diversity_scores = []
    per_query_results = {}
    
    for query, labels in test_set.items():
        try:
            # Get predictions
            predictions = similarity_fn(query, top_k)
            if not predictions:
                per_query_results[query] = {"ndcg": 0.0, "p_at_k": 0.0, "mrr": 0.0}
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
            
            # Compute P@K
            p_at_k = sum(1 for r in relevances if r > 0) / top_k
            p_at_k_scores.append(p_at_k)
            
            # Compute Recall@K
            all_relevant = set()
            for level in ["highly_relevant", "relevant", "somewhat_relevant", "marginally_relevant"]:
                all_relevant.update(labels.get(level, []))
            
            retrieved_relevant = set(card for card, _ in predictions[:top_k] if card in all_relevant)
            recall_at_k = len(retrieved_relevant) / len(all_relevant) if all_relevant else 0.0
            recall_at_k_scores.append(recall_at_k)
            
            # Compute Diversity (intra-list diversity: average pairwise distance)
            # Use simple metric: unique cards / total cards (higher = more diverse)
            unique_cards = len(set(card for card, _ in predictions[:top_k]))
            diversity = unique_cards / top_k if top_k > 0 else 0.0
            diversity_scores.append(diversity)
            
            # Compute MRR
            mrr = 0.0
            for rank, (card, _) in enumerate(predictions, 1):
                if card in labels.get("highly_relevant", []) or card in labels.get("relevant", []):
                    mrr = 1.0 / rank
                    break
            mrr_scores.append(mrr)
            
            per_query_results[query] = {
                "ndcg": ndcg,
                "p_at_k": p_at_k,
                "recall_at_k": recall_at_k,
                "diversity": diversity,
                "mrr": mrr,
            }
            
        except Exception as e:
            print(f"Error evaluating query '{query}': {e}")
            per_query_results[query] = {"ndcg": 0.0, "p_at_k": 0.0, "mrr": 0.0}
            continue
    
    return {
        "method": method_name,
        "ndcg_at_k": float(np.mean(ndcg_scores)) if ndcg_scores else 0.0,
        "p_at_k": float(np.mean(p_at_k_scores)) if p_at_k_scores else 0.0,
        "recall_at_k": float(np.mean(recall_at_k_scores)) if recall_at_k_scores else 0.0,
        "diversity": float(np.mean(diversity_scores)) if diversity_scores else 0.0,
        "mrr": float(np.mean(mrr_scores)) if mrr_scores else 0.0,
        "num_queries": len(ndcg_scores),
        "std_ndcg": float(np.std(ndcg_scores)) if ndcg_scores else 0.0,
        "std_p_at_k": float(np.std(p_at_k_scores)) if p_at_k_scores else 0.0,
        "std_recall_at_k": float(np.std(recall_at_k_scores)) if recall_at_k_scores else 0.0,
        "std_diversity": float(np.std(diversity_scores)) if diversity_scores else 0.0,
        "per_query": per_query_results,
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate with NDCG@K metric")
    parser.add_argument("--embeddings", type=str, required=True, help="Path to embeddings")
    parser.add_argument("--pairs", type=str, help="Path to pairs CSV")
    parser.add_argument("--test-set", type=str, help="Path to test set (default: unified magic)")
    parser.add_argument("--card-attrs", type=str, help="Path to card attributes CSV")
    parser.add_argument("--mode", type=str, default="embedding", choices=["embedding", "jaccard", "fusion", "rrf"], help="Similarity method")
    parser.add_argument("--aggregator", type=str, choices=["rrf", "weighted"], help="Aggregator for fusion mode (default: rrf)")
    parser.add_argument("--top-k", type=int, default=10, help="Top K for evaluation")
    parser.add_argument("--output", type=str, help="Output path for results")
    parser.add_argument("--notes", type=str, help="Optional notes about this evaluation run")
    
    args = parser.parse_args()
    
    # Load test set
    if args.test_set:
        test_set_path = Path(args.test_set)
    else:
        test_set_path = PATHS.test_magic
    
    print(f"Loading test set from {test_set_path}...")
    test_set_data = load_test_set(path=test_set_path)
    test_set = test_set_data.get("queries", test_set_data) if isinstance(test_set_data, dict) else test_set_data
    print(f"  Loaded {len(test_set)} queries")
    
    # Load models
    print(f"\nLoading embeddings from {args.embeddings}...")
    embeddings = KeyedVectors.load(args.embeddings)
    print(f"  Loaded {len(embeddings)} embeddings")
    
    # Create similarity function
    if args.mode == "embedding":
        def similarity_fn(query: str, k: int):
            if query not in embeddings:
                return []
            similar = embeddings.most_similar(query, topn=k)
            return [(card, float(score)) for card, score in similar]
    
    elif args.mode == "jaccard":
        if not args.pairs:
            print("Error: --pairs required for jaccard mode")
            return 1
        adj, _ = load_graph(args.pairs, filter_lands=True)
        from ml.similarity.similarity_methods import jaccard_similarity
        
        def similarity_fn(query: str, k: int):
            if query not in adj:
                return []
            similar = jaccard_similarity(query, adj, top_k=k, filter_lands=True)
            return similar
    
    elif args.mode in ["fusion", "rrf"]:
        if not args.pairs:
            print("Error: --pairs required for fusion mode")
            return 1
        
        adj, _ = load_graph(args.pairs, filter_lands=True)
        card_attrs = None
        if args.card_attrs:
            card_attrs = load_card_attributes_csv(args.card_attrs)
            print(f"  Loaded {len(card_attrs)} card attributes")
        
        # Create fusion instance
        aggregator = args.aggregator or ("rrf" if args.mode == "rrf" else "weighted")
        fusion = WeightedLateFusion(
            embeddings=embeddings,
            adj=adj,
            tagger=None,  # Functional tagger optional
            weights=FusionWeights(),  # Will auto-adjust for available signals
            aggregator=aggregator,
            text_embedder=None,  # Would need to load if available
            card_data=card_attrs,
        )
        
        def similarity_fn(query: str, k: int):
            similar = fusion.similar(query, k)
            return similar
    
    else:
        print(f"Error: Unknown mode {args.mode}")
        return 1
    
    # Evaluate
    print(f"\nEvaluating with {args.mode} method (NDCG@{args.top_k})...")
    results = evaluate_method(test_set, similarity_fn, top_k=args.top_k, method_name=args.mode)
    
    print(f"\n{'='*60}")
    print("Evaluation Results")
    print(f"{'='*60}")
    print(f"Method: {results['method']}")
    print(f"NDCG@{args.top_k}: {results['ndcg_at_k']:.4f} ± {results['std_ndcg']:.4f}")
    print(f"P@{args.top_k}: {results['p_at_k']:.4f} ± {results['std_p_at_k']:.4f}")
    print(f"Recall@{args.top_k}: {results['recall_at_k']:.4f} ± {results['std_recall_at_k']:.4f}")
    print(f"Diversity: {results['diversity']:.4f} ± {results['std_diversity']:.4f}")
    print(f"MRR: {results['mrr']:.4f}")
    print(f"Queries evaluated: {results['num_queries']}")
    
    # Log evaluation run
    try:
        run_id = log_evaluation_run(
            evaluation_type="ndcg_evaluation",
            method=args.mode,
            metrics=results,
            test_set_path=test_set_path,
            num_queries=results['num_queries'],
            config={
                "top_k": args.top_k,
                "aggregator": args.aggregator if args.mode in ["fusion", "rrf"] else None,
                "embeddings_path": str(args.embeddings),
            },
            notes=args.notes,
        )
        print(f"\nLogged evaluation run: {run_id}")
    except Exception as e:
        print(f"\nWarning: Failed to log evaluation run: {e}")
    
    # Save results
    if args.output:
        output_path = Path(args.output)
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"Saved results to {output_path}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

