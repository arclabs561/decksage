#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pandas",
#   "numpy",
# ]
# ///
"""
Investigate why embeddings perform similarly to Jaccard.

Hypotheses:
1. Embeddings are just learning co-occurrence (same as Jaccard)
2. Test set only captures co-occurrence patterns
3. Embeddings need different hyperparameters
4. Evaluation is biased toward co-occurrence
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    import pandas as pd
    import numpy as np
    from gensim.models import KeyedVectors
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False


def compute_jaccard_similarity(
    pairs_df: pd.DataFrame,
    card1: str,
    card2: str,
) -> float:
    """Compute Jaccard similarity between two cards."""
    # Get neighbors of each card
    neighbors1 = set()
    neighbors2 = set()
    
    for _, row in pairs_df.iterrows():
        name1 = row.get("NAME_1", "")
        name2 = row.get("NAME_2", "")
        
        if name1 == card1:
            neighbors1.add(name2)
        elif name2 == card1:
            neighbors1.add(name1)
        
        if name1 == card2:
            neighbors2.add(name2)
        elif name2 == card2:
            neighbors2.add(name1)
    
    if not neighbors1 or not neighbors2:
        return 0.0
    
    intersection = len(neighbors1 & neighbors2)
    union = len(neighbors1 | neighbors2)
    
    return intersection / union if union > 0 else 0.0


def analyze_embedding_vs_jaccard(
    embedding: KeyedVectors,
    pairs_df: pd.DataFrame,
    test_set: dict[str, dict[str, Any]],
    top_k: int = 10,
) -> dict[str, Any]:
    """Compare embedding similarity to Jaccard similarity."""
    results = {
        "queries_analyzed": 0,
        "embedding_jaccard_correlation": [],
        "overlap_analysis": [],
        "rank_differences": [],
    }
    
    for query, labels in test_set.items():
        if query not in embedding:
            continue
        
        # Get embedding predictions
        try:
            embedding_similar = embedding.most_similar(query, topn=top_k * 2)
            embedding_cards = [card for card, _ in embedding_similar]
        except KeyError:
            continue
        
        # Get Jaccard predictions
        jaccard_scores = []
        all_cards = set()
        for _, row in pairs_df.iterrows():
            all_cards.add(row.get("NAME_1", ""))
            all_cards.add(row.get("NAME_2", ""))
        
        for card in all_cards:
            if card != query:
                jaccard = compute_jaccard_similarity(pairs_df, query, card)
                jaccard_scores.append((card, jaccard))
        
        jaccard_scores.sort(key=lambda x: x[1], reverse=True)
        jaccard_cards = [card for card, _ in jaccard_scores[:top_k]]
        
        # Compare top-k overlap
        embedding_set = set(embedding_cards[:top_k])
        jaccard_set = set(jaccard_cards[:top_k])
        overlap = len(embedding_set & jaccard_set)
        
        results["overlap_analysis"].append({
            "query": query,
            "overlap": overlap,
            "overlap_pct": overlap / top_k if top_k > 0 else 0.0,
            "embedding_only": list(embedding_set - jaccard_set),
            "jaccard_only": list(jaccard_set - embedding_set),
        })
        
        # Compare ranks for common items
        common = embedding_set & jaccard_set
        for card in common:
            embedding_rank = embedding_cards.index(card) + 1
            jaccard_rank = jaccard_cards.index(card) + 1
            rank_diff = embedding_rank - jaccard_rank
            
            results["rank_differences"].append({
                "query": query,
                "card": card,
                "embedding_rank": embedding_rank,
                "jaccard_rank": jaccard_rank,
                "rank_diff": rank_diff,
            })
        
        # Compute correlation between embedding scores and Jaccard scores
        # for cards in both top-k lists
        common_cards = embedding_set | jaccard_set
        embedding_scores_dict = {card: score for card, score in embedding_similar}
        jaccard_scores_dict = {card: score for card, score in jaccard_scores}
        
        common_scores = []
        for card in common_cards:
            if card in embedding_scores_dict and card in jaccard_scores_dict:
                common_scores.append((
                    embedding_scores_dict[card],
                    jaccard_scores_dict[card],
                ))
        
        if len(common_scores) >= 3:
            emb_scores, jac_scores = zip(*common_scores)
            correlation = np.corrcoef(emb_scores, jac_scores)[0, 1]
            results["embedding_jaccard_correlation"].append({
                "query": query,
                "correlation": float(correlation),
                "n_common": len(common_scores),
            })
        
        results["queries_analyzed"] += 1
    
    # Aggregate statistics
    if results["overlap_analysis"]:
        avg_overlap = np.mean([r["overlap_pct"] for r in results["overlap_analysis"]])
        results["avg_overlap_pct"] = float(avg_overlap)
    
    if results["embedding_jaccard_correlation"]:
        avg_correlation = np.mean([r["correlation"] for r in results["embedding_jaccard_correlation"]])
        results["avg_correlation"] = float(avg_correlation)
    
    if results["rank_differences"]:
        avg_rank_diff = np.mean([r["rank_diff"] for r in results["rank_differences"]])
        results["avg_rank_diff"] = float(avg_rank_diff)
    
    return results


def main() -> int:
    """Investigate embedding vs Jaccard."""
    parser = argparse.ArgumentParser(description="Investigate embedding vs Jaccard")
    parser.add_argument("--embedding", type=Path, required=True, help="Path to .wv file")
    parser.add_argument("--pairs", type=Path, required=True, help="Path to pairs.csv")
    parser.add_argument("--test-set", type=Path, required=True, help="Path to test set JSON")
    parser.add_argument("--output", type=Path, required=True, help="Output JSON file")
    
    args = parser.parse_args()
    
    if not HAS_DEPS:
        print("Error: pandas, numpy, gensim required")
        return 1
    
    print(f"Loading embedding from {args.embedding}...")
    embedding = KeyedVectors.load(str(args.embedding))
    print(f"  Vocab size: {len(embedding)}")
    
    print(f"Loading pairs from {args.pairs}...")
    pairs_df = pd.read_csv(args.pairs)
    print(f"  Pairs: {len(pairs_df)}")
    
    print(f"Loading test set from {args.test_set}...")
    with open(args.test_set) as f:
        test_data = json.load(f)
    
    queries = test_data.get("queries", test_data)
    print(f"  Queries: {len(queries)}")
    
    print("\nAnalyzing embedding vs Jaccard...")
    results = analyze_embedding_vs_jaccard(embedding, pairs_df, queries)
    
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✅ Results saved to {args.output}")
    print(f"\nSummary:")
    print(f"  Queries analyzed: {results['queries_analyzed']}")
    if "avg_overlap_pct" in results:
        print(f"  Avg overlap (top-10): {results['avg_overlap_pct']:.2%}")
    if "avg_correlation" in results:
        print(f"  Avg correlation: {results['avg_correlation']:.4f}")
    if "avg_rank_diff" in results:
        print(f"  Avg rank difference: {results['avg_rank_diff']:.2f}")
    
    # Interpretation
    if "avg_overlap_pct" in results:
        overlap = results["avg_overlap_pct"]
        if overlap > 0.8:
            print("\n⚠️  HIGH OVERLAP: Embeddings are very similar to Jaccard")
            print("   Hypothesis: Embeddings are just learning co-occurrence")
        elif overlap > 0.5:
            print("\n⚠️  MODERATE OVERLAP: Embeddings partially overlap with Jaccard")
            print("   Hypothesis: Embeddings learn some patterns beyond co-occurrence")
        else:
            print("\n✓  LOW OVERLAP: Embeddings differ from Jaccard")
            print("   Hypothesis: Embeddings learn different patterns")
    
    return 0


if __name__ == "__main__":
    exit(main())

