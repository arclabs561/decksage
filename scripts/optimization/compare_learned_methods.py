#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
Compare different learned fusion weight methods.

Compares:
- XGBoost
- LightGBM
- Linear regression
- Grid search (baseline)
- Equal weights (baseline)
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

from ml.similarity.fusion import FusionWeights, WeightedLateFusion
from ml.similarity.similarity_methods import load_card_attributes_csv, load_graph
from ml.utils.data_loading import load_test_set
from ml.utils.evaluation import compute_precision_at_k
from ml.utils.paths import PATHS

import numpy as np
from gensim.models import KeyedVectors


def evaluate_weights(
    test_set: dict,
    embeddings: KeyedVectors,
    adj: dict,
    card_attrs: dict | None,
    weights: dict,
    aggregator: str = "rrf",
    top_k: int = 10,
) -> dict:
    """Evaluate weights on test set."""
    
    fusion_weights = FusionWeights(
        embed=weights.get("embed", 0.0),
        jaccard=weights.get("jaccard", 0.0),
        text_embed=weights.get("text_embed", 0.0),
    ).normalized()
    
    fusion = WeightedLateFusion(
        embeddings=embeddings,
        adj=adj,
        weights=fusion_weights,
        aggregator=aggregator,
        card_data=card_attrs,
    )
    
    scores = []
    for query, labels in test_set.items():
        try:
            predictions = fusion.similar(query, top_k)
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
        except Exception:
            continue
    
    return {
        "p_at_k": float(np.mean(scores)) if scores else 0.0,
        "std": float(np.std(scores)) if scores else 0.0,
        "num_queries": len(scores),
    }


def main():
    parser = argparse.ArgumentParser(description="Compare learned fusion weight methods")
    parser.add_argument("--embeddings", type=str, required=True, help="Path to embeddings")
    parser.add_argument("--pairs", type=str, required=True, help="Path to pairs CSV")
    parser.add_argument("--card-attrs", type=str, help="Path to card attributes CSV")
    parser.add_argument("--test-set", type=str, help="Path to test set")
    parser.add_argument("--top-k", type=int, default=10, help="Top K for evaluation")
    parser.add_argument("--grid-search-results", type=str, help="Path to grid search results JSON")
    parser.add_argument("--output", type=str, help="Output path for comparison")
    
    args = parser.parse_args()
    
    # Load data
    if args.test_set:
        test_set_path = Path(args.test_set)
    else:
        test_set_path = PATHS.test_magic
    
    print(f"Loading test set from {test_set_path}...")
    test_set_data = load_test_set(path=test_set_path)
    test_set = test_set_data.get("queries", test_set_data) if isinstance(test_set_data, dict) else test_set_data
    print(f"  Loaded {len(test_set)} queries")
    
    print(f"\nLoading embeddings from {args.embeddings}...")
    embeddings = KeyedVectors.load(args.embeddings)
    print(f"  Loaded {len(embeddings)} embeddings")
    
    adj, _ = load_graph(args.pairs, filter_lands=True)
    print(f"  Loaded graph: {len(adj)} cards")
    
    card_attrs = None
    if args.card_attrs:
        card_attrs = load_card_attributes_csv(args.card_attrs)
        print(f"  Loaded {len(card_attrs)} card attributes")
    
    # Load learned weights results
    results_dir = Path("experiments")
    learned_files = list(results_dir.glob("learned_weights_*.json"))
    
    comparison = {}
    
    # Baseline: Equal weights
    print(f"\nEvaluating equal weights baseline...")
    equal_weights = {"embed": 0.333, "jaccard": 0.333, "text_embed": 0.333}
    equal_result = evaluate_weights(test_set, embeddings, adj, card_attrs, equal_weights, "rrf", args.top_k)
    comparison["equal_weights"] = {
        "weights": equal_weights,
        "result": equal_result,
    }
    print(f"  P@{args.top_k}: {equal_result['p_at_k']:.4f}")
    
    # Grid search baseline
    if args.grid_search_results and Path(args.grid_search_results).exists():
        print(f"\nEvaluating grid search weights...")
        with open(args.grid_search_results) as f:
            grid_data = json.load(f)
        grid_weights = grid_data["best_weights"]
        grid_result = evaluate_weights(test_set, embeddings, adj, card_attrs, grid_weights, "rrf", args.top_k)
        comparison["grid_search"] = {
            "weights": grid_weights,
            "result": grid_result,
        }
        print(f"  P@{args.top_k}: {grid_result['p_at_k']:.4f}")
    
    # Learned weights
    for learned_file in learned_files:
        print(f"\nEvaluating {learned_file.stem}...")
        try:
            with open(learned_file) as f:
                learned_data = json.load(f)
            
            method = learned_data["method"]
            weights = learned_data["learned_weights"]
            
            # Re-evaluate on full test set
            result = evaluate_weights(test_set, embeddings, adj, card_attrs, weights, "rrf", args.top_k)
            comparison[method] = {
                "weights": weights,
                "result": result,
            }
            print(f"  P@{args.top_k}: {result['p_at_k']:.4f}")
        except Exception as e:
            print(f"  Error: {e}")
    
    # Print comparison
    print(f"\n{'='*80}")
    print("Method Comparison")
    print(f"{'='*80}")
    print(f"{'Method':<20} {'P@{args.top_k}':<12} {'Std':<12} {'Queries':<10} {'Weights'}")
    print(f"{'-'*80}")
    
    baseline_p = comparison["equal_weights"]["result"]["p_at_k"]
    
    for method, data in sorted(comparison.items(), key=lambda x: x[1]["result"]["p_at_k"], reverse=True):
        result = data["result"]
        weights = data["weights"]
        weights_str = ", ".join(f"{k}={v:.2f}" for k, v in weights.items() if v > 0)
        improvement = result["p_at_k"] - baseline_p
        improvement_pct = (improvement / baseline_p * 100) if baseline_p > 0 else 0.0
        
        print(
            f"{method:<20} "
            f"{result['p_at_k']:<12.4f} "
            f"{result['std']:<12.4f} "
            f"{result['num_queries']:<10} "
            f"{weights_str}"
        )
        if improvement != 0:
            print(f"  {'':20} ({improvement:+.4f}, {improvement_pct:+.1f}% vs baseline)")
    
    # Find best
    best = max(comparison.items(), key=lambda x: x[1]["result"]["p_at_k"])
    print(f"\nBest method: {best[0]} (P@{args.top_k} = {best[1]['result']['p_at_k']:.4f})")
    
    # Save results
    if args.output:
        output_path = Path(args.output)
        with open(output_path, "w") as f:
            json.dump(comparison, f, indent=2)
        print(f"\nSaved comparison to {output_path}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

