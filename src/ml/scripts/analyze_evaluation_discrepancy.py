#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
#     "numpy<2.0.0",
#     "gensim>=4.3.0",
# ]
# ///
"""
Analyze discrepancy between individual signal evaluation and fusion evaluation.

Issue: Individual signals show different P@10 than fusion evaluation.
Need to understand why and fix the methodology.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    import pandas as pd
    import numpy as np
    from gensim.models import KeyedVectors
    
    HAS_DEPS = True
except ImportError as e:
    HAS_DEPS = False
    print(f"Missing dependencies: {e}")


def load_test_set(test_set_path: Path) -> dict[str, dict[str, Any]]:
    """Load test set."""
    with open(test_set_path) as f:
        data = json.load(f)
        if "queries" in data:
            return data["queries"]
        return data


def analyze_query_coverage(
    test_set: dict[str, dict[str, Any]],
    wv: KeyedVectors,
    adj: dict[str, set[str]],
) -> dict[str, Any]:
    """Analyze which queries are covered by which signals."""
    coverage = {
        "total_queries": len(test_set),
        "in_embeddings": 0,
        "in_graph": 0,
        "in_both": 0,
        "in_neither": 0,
        "queries_in_embeddings": [],
        "queries_in_graph": [],
        "queries_in_both": [],
        "queries_in_neither": [],
    }
    
    for query, labels in test_set.items():
        in_embed = query in wv
        in_graph = query in adj
        
        if in_embed:
            coverage["in_embeddings"] += 1
            coverage["queries_in_embeddings"].append(query)
        if in_graph:
            coverage["in_graph"] += 1
            coverage["queries_in_graph"].append(query)
        if in_embed and in_graph:
            coverage["in_both"] += 1
            coverage["queries_in_both"].append(query)
        if not in_embed and not in_graph:
            coverage["in_neither"] += 1
            coverage["queries_in_neither"].append(query)
    
    return coverage


def compare_evaluation_methods(
    test_set: dict[str, dict[str, Any]],
    wv: KeyedVectors,
    adj: dict[str, set[str]],
    query: str,
) -> dict[str, Any]:
    """Compare evaluation methods for a single query."""
    if query not in test_set:
        return {"error": "Query not in test set"}
    
    labels = test_set[query]
    all_relevant = set()
    for level in ["highly_relevant", "relevant", "somewhat_relevant", "marginally_relevant"]:
        all_relevant.update(labels.get(level, []))
    
    results = {
        "query": query,
        "num_relevant": len(all_relevant),
        "embedding": {},
        "jaccard": {},
        "fusion": {},
    }
    
    # Embedding evaluation
    if query in wv:
        try:
            similar = wv.most_similar(query, topn=10)
            candidates = [card for card, _ in similar]
            hits = len(set(candidates) & all_relevant)
            results["embedding"] = {
                "candidates": candidates,
                "hits": hits,
                "p@10": hits / 10.0,
            }
        except KeyError:
            pass
    
    # Jaccard evaluation
    if query in adj:
        def jaccard_similarity(set1: set[str], set2: set[str]) -> float:
            intersection = len(set1 & set2)
            union = len(set1 | set2)
            return intersection / union if union > 0 else 0.0
        
        query_neighbors = adj[query]
        similarities = []
        for candidate in adj.keys():
            if candidate == query:
                continue
            candidate_neighbors = adj[candidate]
            sim = jaccard_similarity(query_neighbors, candidate_neighbors)
            similarities.append((candidate, sim))
        
        similarities.sort(key=lambda x: x[1], reverse=True)
        candidates = [card for card, _ in similarities[:10]]
        hits = len(set(candidates) & all_relevant)
        results["jaccard"] = {
            "candidates": candidates,
            "hits": hits,
            "p@10": hits / 10.0,
        }
    
    # Fusion evaluation (simple weighted)
    if query in wv and query in adj:
        # Get embedding scores
        embed_scores = {}
        try:
            similar = wv.most_similar(query, topn=20)
            for card, sim in similar:
                embed_scores[card] = float(sim)
        except KeyError:
            pass
        
        # Get Jaccard scores
        jaccard_scores = {}
        query_neighbors = adj[query]
        for candidate in adj.keys():
            if candidate == query:
                continue
            candidate_neighbors = adj[candidate]
            sim = jaccard_similarity(query_neighbors, candidate_neighbors)
            jaccard_scores[candidate] = sim
        
        # Combine (equal weights for now)
        all_candidates = set(embed_scores.keys()) | set(jaccard_scores.keys())
        combined_scores = {}
        for candidate in all_candidates:
            score = 0.5 * embed_scores.get(candidate, 0.0) + 0.5 * jaccard_scores.get(candidate, 0.0)
            combined_scores[candidate] = score
        
        candidates = sorted(combined_scores.items(), key=lambda x: x[1], reverse=True)[:10]
        candidate_cards = [card for card, _ in candidates]
        hits = len(set(candidate_cards) & all_relevant)
        results["fusion"] = {
            "candidates": candidate_cards,
            "hits": hits,
            "p@10": hits / 10.0,
        }
    
    return results


def main() -> int:
    """Analyze evaluation discrepancy."""
    parser = argparse.ArgumentParser(description="Analyze evaluation discrepancy")
    parser.add_argument(
        "--test-set",
        type=str,
        default="experiments/test_set_canonical_magic.json",
        help="Test set path",
    )
    parser.add_argument(
        "--pairs-csv",
        type=str,
        default="data/processed/pairs_large.csv",
        help="Pairs CSV",
    )
    parser.add_argument(
        "--embeddings",
        type=str,
        default="data/embeddings/node2vec_default.wv",
        help="Embeddings file",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="experiments/evaluation_discrepancy_analysis.json",
        help="Output JSON",
    )
    parser.add_argument(
        "--sample-queries",
        type=int,
        default=5,
        help="Number of sample queries to analyze in detail",
    )
    
    args = parser.parse_args()
    
    if not HAS_DEPS:
        print("❌ Missing dependencies")
        return 1
    
    print("=" * 70)
    print("Evaluation Discrepancy Analysis")
    print("=" * 70)
    print()
    
    # Load data
    test_set_path = Path(args.test_set)
    test_set = load_test_set(test_set_path)
    print(f"📊 Loaded test set: {len(test_set)} queries")
    
    embed_path = Path(args.embeddings)
    wv = KeyedVectors.load(str(embed_path))
    print(f"📊 Loaded embeddings: {len(wv):,} cards")
    
    pairs_csv = Path(args.pairs_csv)
    df = pd.read_csv(pairs_csv)
    adj: dict[str, set[str]] = {}
    for _, row in df.iterrows():
        card1, card2 = row["NAME_1"], row["NAME_2"]
        if card1 not in adj:
            adj[card1] = set()
        if card2 not in adj:
            adj[card2] = set()
        adj[card1].add(card2)
        adj[card2].add(card1)
    print(f"📊 Loaded graph: {len(adj):,} cards")
    print()
    
    # Analyze coverage
    print("📊 Query Coverage Analysis:")
    coverage = analyze_query_coverage(test_set, wv, adj)
    print(f"  Total queries: {coverage['total_queries']}")
    print(f"  In embeddings: {coverage['in_embeddings']}")
    print(f"  In graph: {coverage['in_graph']}")
    print(f"  In both: {coverage['in_both']}")
    print(f"  In neither: {coverage['in_neither']}")
    print()
    
    # Sample query analysis
    print(f"📊 Detailed Analysis (sample of {args.sample_queries} queries):")
    sample_queries = list(test_set.keys())[:args.sample_queries]
    detailed_results = []
    
    for query in sample_queries:
        result = compare_evaluation_methods(test_set, wv, adj, query)
        detailed_results.append(result)
        
        print(f"\n  Query: {query}")
        if "embedding" in result and result["embedding"]:
            print(f"    Embedding: P@10={result['embedding']['p@10']:.4f}, hits={result['embedding']['hits']}")
        if "jaccard" in result and result["jaccard"]:
            print(f"    Jaccard: P@10={result['jaccard']['p@10']:.4f}, hits={result['jaccard']['hits']}")
        if "fusion" in result and result["fusion"]:
            print(f"    Fusion: P@10={result['fusion']['p@10']:.4f}, hits={result['fusion']['hits']}")
    
    # Save results
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w") as f:
        json.dump({
            "coverage": coverage,
            "sample_queries": detailed_results,
        }, f, indent=2)
    
    print()
    print(f"✅ Results saved to {output_path}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

