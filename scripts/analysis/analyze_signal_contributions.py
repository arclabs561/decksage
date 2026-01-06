#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "numpy>=1.24.0",
# ]
# ///
"""
Analyze individual signal contributions to understand why fusion < embedding.

Tests each signal individually and in combinations to identify:
- Which signals are most effective
- Why fusion underperforms embedding-only
- Optimal signal combinations
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
from ml.utils.paths import PATHS


def evaluate_signal_combination(
    test_set: dict,
    embeddings: KeyedVectors,
    adj: dict,
    card_attrs: dict | None,
    weights: FusionWeights,
    aggregator: str = "weighted",
    top_k: int = 10,
    sample_size: int | None = None,
) -> dict:
    """Evaluate a specific signal combination."""
    
    # Create fusion instance
    fusion = WeightedLateFusion(
        embeddings=embeddings,
        adj=adj,
        tagger=None,
        weights=weights,
        aggregator=aggregator,
        card_data=card_attrs,
    )
    
    # Sample test set if requested
    if sample_size and sample_size < len(test_set):
        import random
        test_items = list(test_set.items())
        random.seed(42)
        test_set = dict(random.sample(test_items, sample_size))
    
    # Evaluate
    scores = []
    evaluated = 0
    
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
            evaluated += 1
            
        except Exception:
            continue
    
    return {
        "p_at_k": float(np.mean(scores)) if scores else 0.0,
        "std": float(np.std(scores)) if scores else 0.0,
        "num_queries": evaluated,
        "weights": {
            "embed": weights.embed,
            "jaccard": weights.jaccard,
            "text_embed": weights.text_embed,
            "functional": weights.functional,
            "gnn": weights.gnn,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Analyze signal contributions")
    parser.add_argument("--embeddings", type=str, required=True, help="Path to embeddings")
    parser.add_argument("--pairs", type=str, required=True, help="Path to pairs CSV")
    parser.add_argument("--card-attrs", type=str, help="Path to card attributes CSV")
    parser.add_argument("--test-set", type=str, help="Path to test set")
    parser.add_argument("--top-k", type=int, default=10, help="Top K for evaluation")
    parser.add_argument("--sample-size", type=int, help="Sample size for faster evaluation")
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
    if args.card_attrs:
        card_attrs = load_card_attributes_csv(args.card_attrs)
        print(f"  Loaded {len(card_attrs)} card attributes")
    
    # Test individual signals
    print(f"\n{'='*80}")
    print("Testing Individual Signals")
    print(f"{'='*80}")
    
    results = {}
    
    # 1. Embedding only
    print("\n1. Embedding only...")
    weights_embed = FusionWeights(embed=1.0, jaccard=0.0, text_embed=0.0).normalized()
    results["embedding_only"] = evaluate_signal_combination(
        test_set, embeddings, adj, card_attrs, weights_embed, "weighted", args.top_k, args.sample_size
    )
    print(f"   P@{args.top_k}: {results['embedding_only']['p_at_k']:.4f}")
    
    # 2. Jaccard only
    print("\n2. Jaccard only...")
    weights_jaccard = FusionWeights(embed=0.0, jaccard=1.0, text_embed=0.0).normalized()
    results["jaccard_only"] = evaluate_signal_combination(
        test_set, embeddings, adj, card_attrs, weights_jaccard, "weighted", args.top_k, args.sample_size
    )
    print(f"   P@{args.top_k}: {results['jaccard_only']['p_at_k']:.4f}")
    
    # 3. Text embed only (if available)
    if card_attrs:
        print("\n3. Text embed only...")
        weights_text = FusionWeights(embed=0.0, jaccard=0.0, text_embed=1.0).normalized()
        results["text_embed_only"] = evaluate_signal_combination(
            test_set, embeddings, adj, card_attrs, weights_text, "weighted", args.top_k, args.sample_size
        )
        print(f"   P@{args.top_k}: {results['text_embed_only']['p_at_k']:.4f}")
    
    # Test combinations
    print(f"\n{'='*80}")
    print("Testing Signal Combinations")
    print(f"{'='*80}")
    
    # 4. Embedding + Jaccard
    print("\n4. Embedding + Jaccard (50/50)...")
    weights_embed_jaccard = FusionWeights(embed=0.5, jaccard=0.5, text_embed=0.0).normalized()
    results["embed_jaccard"] = evaluate_signal_combination(
        test_set, embeddings, adj, card_attrs, weights_embed_jaccard, "weighted", args.top_k, args.sample_size
    )
    print(f"   P@{args.top_k}: {results['embed_jaccard']['p_at_k']:.4f}")
    
    # 5. Embedding + Text
    if card_attrs:
        print("\n5. Embedding + Text (50/50)...")
        weights_embed_text = FusionWeights(embed=0.5, jaccard=0.0, text_embed=0.5).normalized()
        results["embed_text"] = evaluate_signal_combination(
            test_set, embeddings, adj, card_attrs, weights_embed_text, "weighted", args.top_k, args.sample_size
        )
        print(f"   P@{args.top_k}: {results['embed_text']['p_at_k']:.4f}")
    
    # 6. Jaccard + Text
    if card_attrs:
        print("\n6. Jaccard + Text (50/50)...")
        weights_jaccard_text = FusionWeights(embed=0.0, jaccard=0.5, text_embed=0.5).normalized()
        results["jaccard_text"] = evaluate_signal_combination(
            test_set, embeddings, adj, card_attrs, weights_jaccard_text, "weighted", args.top_k, args.sample_size
        )
        print(f"   P@{args.top_k}: {results['jaccard_text']['p_at_k']:.4f}")
    
    # 7. All three (equal)
    if card_attrs:
        print("\n7. All three (equal weights)...")
        weights_all = FusionWeights(embed=0.333, jaccard=0.333, text_embed=0.333).normalized()
        results["all_equal"] = evaluate_signal_combination(
            test_set, embeddings, adj, card_attrs, weights_all, "weighted", args.top_k, args.sample_size
        )
        print(f"   P@{args.top_k}: {results['all_equal']['p_at_k']:.4f}")
    
    # 8. All three with RRF
    if card_attrs:
        print("\n8. All three (equal weights, RRF aggregator)...")
        results["all_equal_rrf"] = evaluate_signal_combination(
            test_set, embeddings, adj, card_attrs, weights_all, "rrf", args.top_k, args.sample_size
        )
        print(f"   P@{args.top_k}: {results['all_equal_rrf']['p_at_k']:.4f}")
    
    # Print summary
    print(f"\n{'='*80}")
    print("Signal Contribution Analysis Summary")
    print(f"{'='*80}")
    print(f"{'Configuration':<30} {'P@{args.top_k}':<12} {'Std':<12} {'Queries':<10}")
    print(f"{'-'*80}")
    
    for name, result in sorted(results.items(), key=lambda x: x[1]["p_at_k"], reverse=True):
        print(
            f"{name:<30} "
            f"{result['p_at_k']:<12.4f} "
            f"{result['std']:<12.4f} "
            f"{result['num_queries']:<10}"
        )
    
    # Find best
    best = max(results.items(), key=lambda x: x[1]["p_at_k"])
    print(f"\nBest configuration: {best[0]} (P@{args.top_k} = {best[1]['p_at_k']:.4f})")
    
    # Save results
    if args.output:
        output_path = Path(args.output)
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nSaved results to {output_path}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

