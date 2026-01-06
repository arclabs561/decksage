#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "numpy>=1.24.0",
# ]
# ///
"""
Investigate why fusion performs worse than embedding-only.

Hypotheses:
1. Candidate set too small (candidate_topn)
2. Weight normalization issues
3. Signal quality differences
4. Aggregation method issues
5. Score normalization problems
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ml.utils.path_setup import setup_project_paths

setup_project_paths()

from gensim.models import KeyedVectors

from ml.similarity.fusion import FusionWeights, WeightedLateFusion
from ml.similarity.similarity_methods import load_card_attributes_csv, load_graph
from ml.utils.data_loading import load_test_set
from ml.utils.evaluation import compute_precision_at_k
from ml.utils.paths import PATHS


def test_candidate_topn(
    test_set: dict,
    embeddings: KeyedVectors,
    adj: dict,
    card_attrs: dict | None,
    candidate_topn_values: list[int],
    top_k: int = 10,
    sample_size: int = 50,
) -> dict:
    """Test different candidate_topn values."""
    
    import random
    random.seed(42)
    test_items = list(test_set.items())
    test_sample = dict(random.sample(test_items, min(sample_size, len(test_set))))
    
    results = {}
    
    for candidate_topn in candidate_topn_values:
        print(f"\nTesting candidate_topn={candidate_topn}...")
        
        weights = FusionWeights(embed=0.5, jaccard=0.5, text_embed=0.0).normalized()
        fusion = WeightedLateFusion(
            embeddings=embeddings,
            adj=adj,
            weights=weights,
            candidate_topn=candidate_topn,
            card_data=card_attrs,
        )
        
        scores = []
        for query, labels in test_sample.items():
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
        
        import numpy as np
        results[candidate_topn] = {
            "p_at_k": float(np.mean(scores)) if scores else 0.0,
            "num_queries": len(scores),
        }
        print(f"  P@{top_k}: {results[candidate_topn]['p_at_k']:.4f}")
    
    return results


def compare_overlap(
    test_set: dict,
    embeddings: KeyedVectors,
    adj: dict,
    top_k: int = 10,
    sample_size: int = 20,
) -> dict:
    """Compare overlap between embedding-only and fusion results."""
    
    import random
    random.seed(42)
    test_items = list(test_set.items())
    test_sample = dict(random.sample(test_items, min(sample_size, len(test_set))))
    
    weights = FusionWeights(embed=0.5, jaccard=0.5, text_embed=0.0).normalized()
    fusion = WeightedLateFusion(
        embeddings=embeddings,
        adj=adj,
        weights=weights,
    )
    
    overlaps = []
    embedding_only_results = []
    fusion_results = []
    
    for query, _ in test_sample.items():
        try:
            # Embedding-only
            if query in embeddings:
                embed_similar = embeddings.most_similar(query, topn=top_k)
                embed_cards = [card for card, _ in embed_similar]
            else:
                continue
            
            # Fusion
            fusion_similar = fusion.similar(query, top_k)
            fusion_cards = [card for card, _ in fusion_similar]
            
            # Compute overlap
            overlap = len(set(embed_cards) & set(fusion_cards)) / top_k
            overlaps.append(overlap)
            
            embedding_only_results.append(embed_cards)
            fusion_results.append(fusion_cards)
            
        except Exception:
            continue
    
    import numpy as np
    return {
        "mean_overlap": float(np.mean(overlaps)) if overlaps else 0.0,
        "overlaps": overlaps,
        "sample_queries": list(test_sample.keys())[:5],
    }


def main():
    parser = argparse.ArgumentParser(description="Investigate fusion performance")
    parser.add_argument("--embeddings", type=str, required=True, help="Path to embeddings")
    parser.add_argument("--pairs", type=str, required=True, help="Path to pairs CSV")
    parser.add_argument("--card-attrs", type=str, help="Path to card attributes CSV")
    parser.add_argument("--test-set", type=str, help="Path to test set")
    parser.add_argument("--top-k", type=int, default=10, help="Top K for evaluation")
    parser.add_argument("--sample-size", type=int, default=50, help="Sample size for testing")
    
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
    
    # Test 1: Candidate topn impact
    print(f"\n{'='*80}")
    print("Test 1: Candidate TopN Impact")
    print(f"{'='*80}")
    candidate_results = test_candidate_topn(
        test_set, embeddings, adj, card_attrs, [50, 100, 200, 500], args.top_k, args.sample_size
    )
    
    # Test 2: Overlap analysis
    print(f"\n{'='*80}")
    print("Test 2: Overlap Analysis (Embedding vs Fusion)")
    print(f"{'='*80}")
    overlap_results = compare_overlap(test_set, embeddings, adj, args.top_k, args.sample_size)
    print(f"Mean overlap: {overlap_results['mean_overlap']:.4f}")
    print(f"  (Higher overlap = more similar results)")
    
    # Summary
    print(f"\n{'='*80}")
    print("Summary")
    print(f"{'='*80}")
    print("Candidate TopN Results:")
    for topn, result in sorted(candidate_results.items()):
        print(f"  candidate_topn={topn}: P@{args.top_k}={result['p_at_k']:.4f}")
    
    print(f"\nOverlap Analysis:")
    print(f"  Mean overlap: {overlap_results['mean_overlap']:.4f}")
    if overlap_results['mean_overlap'] < 0.5:
        print("  → Low overlap suggests fusion is finding different cards")
    else:
        print("  → High overlap suggests fusion is similar to embedding-only")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

