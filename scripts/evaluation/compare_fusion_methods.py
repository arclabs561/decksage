#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "numpy>=1.24.0",
# ]
# ///
"""
Compare different fusion methods: weighted, RRF, and embedding-only baseline.

Runs evaluation on all methods and creates comparison report.
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


def evaluate_method(
    test_set: dict,
    similarity_fn: callable,
    method_name: str,
    top_k: int = 10,
) -> dict:
    """Evaluate a similarity method with comprehensive metrics."""
    
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
    diversity_scores = []
    mrr_scores = []
    
    for query, labels in test_set.items():
        try:
            predictions = similarity_fn(query, top_k)
            if not predictions:
                continue
            
            # Build relevance vector
            relevances = []
            all_relevant = set()
            for level in ["highly_relevant", "relevant", "somewhat_relevant", "marginally_relevant"]:
                all_relevant.update(labels.get(level, []))
            
            for card, _ in predictions[:top_k]:
                relevance = 0.0
                for level, weight in relevance_weights.items():
                    if card in labels.get(level, []):
                        relevance = weight
                        break
                relevances.append(relevance)
            
            # NDCG@K
            def dcg_at_k(rels: list[float], k: int) -> float:
                rels = rels[:k]
                if not rels:
                    return 0.0
                return sum(rel / np.log2(i + 2) for i, rel in enumerate(rels))
            
            dcg = dcg_at_k(relevances, top_k)
            ideal_relevances = sorted(relevances, reverse=True)
            idcg = dcg_at_k(ideal_relevances, top_k)
            ndcg = dcg / idcg if idcg > 0 else 0.0
            ndcg_scores.append(ndcg)
            
            # P@K
            p_at_k = sum(1 for r in relevances if r > 0) / top_k
            p_at_k_scores.append(p_at_k)
            
            # Recall@K
            retrieved_relevant = set(card for card, _ in predictions[:top_k] if card in all_relevant)
            recall_at_k = len(retrieved_relevant) / len(all_relevant) if all_relevant else 0.0
            recall_at_k_scores.append(recall_at_k)
            
            # Diversity (unique cards / total)
            unique_cards = len(set(card for card, _ in predictions[:top_k]))
            diversity = unique_cards / top_k if top_k > 0 else 0.0
            diversity_scores.append(diversity)
            
            # MRR
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
        "method": method_name,
        "ndcg_at_k": float(np.mean(ndcg_scores)) if ndcg_scores else 0.0,
        "p_at_k": float(np.mean(p_at_k_scores)) if p_at_k_scores else 0.0,
        "recall_at_k": float(np.mean(recall_at_k_scores)) if recall_at_k_scores else 0.0,
        "diversity": float(np.mean(diversity_scores)) if diversity_scores else 0.0,
        "mrr": float(np.mean(mrr_scores)) if mrr_scores else 0.0,
        "num_queries": len(ndcg_scores),
        "std_ndcg": float(np.std(ndcg_scores)) if ndcg_scores else 0.0,
        "std_p_at_k": float(np.std(p_at_k_scores)) if p_at_k_scores else 0.0,
    }


def main():
    parser = argparse.ArgumentParser(description="Compare fusion methods")
    parser.add_argument("--embeddings", type=str, required=True, help="Path to embeddings")
    parser.add_argument("--pairs", type=str, required=True, help="Path to pairs CSV")
    parser.add_argument("--card-attrs", type=str, help="Path to card attributes CSV")
    parser.add_argument("--test-set", type=str, help="Path to test set")
    parser.add_argument("--top-k", type=int, default=10, help="Top K for evaluation")
    parser.add_argument("--output", type=str, help="Output path for comparison results")
    
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
    
    adj, _ = load_graph(args.pairs, filter_lands=True)
    print(f"  Loaded graph: {len(adj)} cards")
    
    card_attrs = None
    if args.card_attrs:
        card_attrs = load_card_attributes_csv(args.card_attrs)
        print(f"  Loaded {len(card_attrs)} card attributes")
    
    # Evaluate methods
    results = {}
    
    # 1. Embedding-only baseline
    print(f"\nEvaluating embedding-only baseline...")
    def embedding_fn(query: str, k: int):
        if query not in embeddings:
            return []
        similar = embeddings.most_similar(query, topn=k)
        return [(card, float(score)) for card, score in similar]
    
    results["embedding"] = evaluate_method(test_set, embedding_fn, "embedding", args.top_k)
    
    # 2. Weighted fusion
    print(f"\nEvaluating weighted fusion...")
    fusion_weighted = WeightedLateFusion(
        embeddings=embeddings,
        adj=adj,
        weights=FusionWeights(),
        aggregator="weighted",
        card_data=card_attrs,
    )
    
    def weighted_fn(query: str, k: int):
        return fusion_weighted.similar(query, k)
    
    results["fusion_weighted"] = evaluate_method(test_set, weighted_fn, "fusion_weighted", args.top_k)
    
    # 3. RRF fusion
    print(f"\nEvaluating RRF fusion...")
    fusion_rrf = WeightedLateFusion(
        embeddings=embeddings,
        adj=adj,
        weights=FusionWeights(),
        aggregator="rrf",
        card_data=card_attrs,
    )
    
    def rrf_fn(query: str, k: int):
        return fusion_rrf.similar(query, k)
    
    results["fusion_rrf"] = evaluate_method(test_set, rrf_fn, "fusion_rrf", args.top_k)
    
    # Print comparison
    print(f"\n{'='*80}")
    print("Method Comparison")
    print(f"{'='*80}")
    print(f"{'Method':<20} {'NDCG@10':<12} {'P@10':<12} {'Recall@10':<12} {'Diversity':<12} {'MRR':<12}")
    print(f"{'-'*80}")
    
    for method_name, result in results.items():
        print(
            f"{method_name:<20} "
            f"{result['ndcg_at_k']:<12.4f} "
            f"{result['p_at_k']:<12.4f} "
            f"{result['recall_at_k']:<12.4f} "
            f"{result['diversity']:<12.4f} "
            f"{result['mrr']:<12.4f}"
        )
    
    # Find best method
    best_ndcg = max(r['ndcg_at_k'] for r in results.values())
    best_method = next(m for m, r in results.items() if r['ndcg_at_k'] == best_ndcg)
    
    print(f"\nBest method (by NDCG@10): {best_method} ({best_ndcg:.4f})")
    
    # Log each method's evaluation
    try:
        for method, result in results.items():
            log_evaluation_run(
                evaluation_type="fusion_comparison",
                method=method,
                metrics={
                    "ndcg_at_k": result.get("ndcg_at_k", 0.0),
                    "p_at_k": result.get("p_at_k", 0.0),
                    "recall_at_k": result.get("recall_at_k", 0.0),
                    "diversity": result.get("diversity", 0.0),
                    "mrr": result.get("mrr", 0.0),
                },
                test_set_path=test_set_path,
                num_queries=result.get("num_queries", 0),
                config={
                    "top_k": args.top_k,
                    "aggregator": "rrf" if "rrf" in method else ("weighted" if "weighted" in method else None),
                },
                notes=f"Fusion comparison: {method}",
            )
        print(f"\nLogged {len(results)} evaluation runs")
    except Exception as e:
        print(f"\nWarning: Failed to log evaluation runs: {e}")
    
    # Save results
    if args.output:
        output_path = Path(args.output)
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"Saved results to {output_path}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

