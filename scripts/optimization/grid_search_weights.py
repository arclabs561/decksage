#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "numpy>=1.24.0",
# ]
# ///
"""
Grid search for optimal fusion weights.

Tests multiple weight combinations to find optimal balance between signals.
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
from ml.utils.evaluation import compute_precision_at_k
from ml.utils.evaluation_logger import log_evaluation_run
from ml.utils.paths import PATHS


def grid_search_weights(
    test_set: dict,
    embeddings: KeyedVectors,
    adj: dict,
    card_attrs: dict | None,
    active_signals: list[str],
    step: float = 0.1,
    top_k: int = 10,
    sample_size: int | None = None,
    aggregator: str = "weighted",
) -> dict:
    """Grid search for optimal weights."""
    
    # Sample test set if requested
    if sample_size and sample_size < len(test_set):
        import random
        test_items = list(test_set.items())
        random.seed(42)
        test_set = dict(random.sample(test_items, sample_size))
    
    # Generate weight combinations
    if len(active_signals) == 2:
        # Two signals: test different ratios
        combinations = []
        for w1 in np.arange(0.0, 1.01, step):
            w2 = 1.0 - w1
            if w2 >= 0.0:
                combinations.append({active_signals[0]: w1, active_signals[1]: w2})
    elif len(active_signals) == 3:
        # Three signals: test different combinations
        combinations = []
        for w1 in np.arange(0.0, 1.01, step):
            for w2 in np.arange(0.0, 1.01 - w1, step):
                w3 = 1.0 - w1 - w2
                if w3 >= 0.0:
                    combinations.append({
                        active_signals[0]: w1,
                        active_signals[1]: w2,
                        active_signals[2]: w3,
                    })
    else:
        # More signals: use equal weights as baseline
        equal_weight = 1.0 / len(active_signals)
        combinations = [{s: equal_weight for s in active_signals}]
    
    print(f"Testing {len(combinations)} weight combinations...")
    
    best_score = -1.0
    best_weights = None
    all_results = []
    
    for i, weight_dict in enumerate(combinations):
        if (i + 1) % 10 == 0:
            print(f"  Progress: {i+1}/{len(combinations)}")
        
        # Create weights
        weights_dict = {
            "embed": weight_dict.get("embed", 0.0),
            "jaccard": weight_dict.get("jaccard", 0.0),
            "text_embed": weight_dict.get("text_embed", 0.0),
            "functional": 0.0,
            "gnn": 0.0,
        }
        weights = FusionWeights(**weights_dict).normalized()
        
        # Create fusion
        fusion = WeightedLateFusion(
            embeddings=embeddings,
            adj=adj,
            tagger=None,
            weights=weights,
            aggregator=aggregator,
            card_data=card_attrs,
        )
        
        # Evaluate
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
        
        p_at_k_mean = float(np.mean(scores)) if scores else 0.0
        
        all_results.append({
            "weights": weight_dict,
            "p_at_k": p_at_k_mean,
            "num_queries": len(scores),
        })
        
        if p_at_k_mean > best_score:
            best_score = p_at_k_mean
            best_weights = weight_dict
    
    # Sort by performance
    all_results.sort(key=lambda x: x["p_at_k"], reverse=True)
    
    return {
        "best_weights": best_weights,
        "best_score": best_score,
        "top_10": all_results[:10],
        "all_results": all_results,
    }


def main():
    parser = argparse.ArgumentParser(description="Grid search for optimal fusion weights")
    parser.add_argument("--embeddings", type=str, required=True, help="Path to embeddings")
    parser.add_argument("--pairs", type=str, required=True, help="Path to pairs CSV")
    parser.add_argument("--card-attrs", type=str, help="Path to card attributes CSV")
    parser.add_argument("--test-set", type=str, help="Path to test set")
    parser.add_argument("--top-k", type=int, default=10, help="Top K for evaluation")
    parser.add_argument("--step", type=float, default=0.1, help="Weight step size (0.1 = 10% increments)")
    parser.add_argument("--sample-size", type=int, help="Sample size for faster evaluation")
    parser.add_argument("--aggregator", type=str, default="weighted", choices=["weighted", "rrf"], help="Aggregator method")
    parser.add_argument("--output", type=str, help="Output path for results")
    
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
    active_signals = ["embed", "jaccard"]
    if args.card_attrs:
        card_attrs = load_card_attributes_csv(args.card_attrs)
        print(f"  Loaded {len(card_attrs)} card attributes")
        active_signals.append("text_embed")
    
    print(f"\nActive signals: {', '.join(active_signals)}")
    print(f"Step size: {args.step}")
    print(f"Aggregator: {args.aggregator}")
    
    # Run grid search
    results = grid_search_weights(
        test_set,
        embeddings,
        adj,
        card_attrs,
        active_signals,
        step=args.step,
        top_k=args.top_k,
        sample_size=args.sample_size,
        aggregator=args.aggregator,
    )
    
    # Print results
    print(f"\n{'='*80}")
    print("Grid Search Results")
    print(f"{'='*80}")
    print(f"Best P@{args.top_k}: {results['best_score']:.4f}")
    print(f"Best weights:")
    for signal, weight in results['best_weights'].items():
        print(f"  {signal}: {weight:.3f}")
    
    print(f"\nTop 10 configurations:")
    for i, result in enumerate(results['top_10'], 1):
        weights_str = ", ".join(f"{k}={v:.2f}" for k, v in result['weights'].items())
        print(f"  {i}. P@{args.top_k}={result['p_at_k']:.4f} ({weights_str})")
    
    # Log best configuration
    try:
        log_evaluation_run(
            evaluation_type="grid_search_optimization",
            method=f"fusion_{args.aggregator}",
            metrics={
                "p_at_k": results['best_score'],
                "best_weights": results['best_weights'],
            },
            test_set_path=test_set_path,
            num_queries=len(test_set),
            config={
                "top_k": args.top_k,
                "step": args.step,
                "aggregator": args.aggregator,
                "sample_size": args.sample_size,
            },
            notes=f"Grid search: {len(results.get('all_results', []))} combinations tested",
        )
    except Exception as e:
        print(f"\nWarning: Failed to log evaluation run: {e}")
    
    # Save results
    if args.output:
        output_path = Path(args.output)
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nSaved results to {output_path}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

