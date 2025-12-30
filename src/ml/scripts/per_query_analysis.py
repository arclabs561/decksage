#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Per-query analysis tool for identifying failure modes.

Analyzes which queries are hardest, why models fail, and patterns in errors.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    from gensim.models import KeyedVectors
    HAS_GENSIM = True
except ImportError:
    HAS_GENSIM = False


def analyze_per_query(
    embedding: KeyedVectors,
    test_set: dict[str, dict[str, Any]],
    top_k: int = 10,
) -> dict[str, Any]:
    """Analyze performance per query."""
    from ml.utils.evaluation import (
        compute_precision_at_k,
        compute_recall_at_k,
        compute_map,
    )
    
    results = {}
    
    for query, labels in test_set.items():
        if query not in embedding:
            results[query] = {
                "status": "not_in_vocab",
                "p@10": 0.0,
                "r@10": 0.0,
                "map@10": 0.0,
            }
            continue
        
        try:
            similar = embedding.most_similar(query, topn=top_k)
            predictions = [card for card, _ in similar]
            
            p_at_k = compute_precision_at_k(predictions, labels, k=top_k)
            r_at_k = compute_recall_at_k(predictions, labels, k=top_k)
            map_at_k = compute_map(predictions, labels, k=top_k)
            
            # Count relevant items retrieved
            all_relevant = set(labels.get("highly_relevant", [])) | set(labels.get("relevant", []))
            retrieved_relevant = sum(1 for p in predictions if p in all_relevant)
            
            # Find rank of first relevant
            first_rank = None
            for rank, pred in enumerate(predictions, 1):
                if pred in all_relevant:
                    first_rank = rank
                    break
            
            results[query] = {
                "status": "evaluated",
                "p@10": p_at_k,
                "r@10": r_at_k,
                "map@10": map_at_k,
                "num_relevant": len(all_relevant),
                "retrieved_relevant": retrieved_relevant,
                "first_rank": first_rank,
                "predictions": predictions[:5],  # Top 5 for inspection
            }
        except Exception as e:
            results[query] = {
                "status": "error",
                "error": str(e),
                "p@10": 0.0,
                "r@10": 0.0,
                "map@10": 0.0,
            }
    
    return results


def identify_failure_modes(per_query_results: dict[str, Any]) -> dict[str, Any]:
    """Identify patterns in failures."""
    failures = {
        "zero_relevant_retrieved": [],
        "low_precision": [],
        "low_recall": [],
        "high_rank_first_hit": [],
        "not_in_vocab": [],
    }
    
    for query, result in per_query_results.items():
        if result.get("status") == "not_in_vocab":
            failures["not_in_vocab"].append(query)
        elif result.get("status") == "evaluated":
            if result.get("retrieved_relevant", 0) == 0:
                failures["zero_relevant_retrieved"].append({
                    "query": query,
                    "num_relevant": result.get("num_relevant", 0),
                })
            elif result.get("p@10", 0) < 0.1:
                failures["low_precision"].append({
                    "query": query,
                    "p@10": result.get("p@10", 0),
                    "num_relevant": result.get("num_relevant", 0),
                })
            elif result.get("r@10", 0) < 0.1:
                failures["low_recall"].append({
                    "query": query,
                    "r@10": result.get("r@10", 0),
                    "num_relevant": result.get("num_relevant", 0),
                })
            elif result.get("first_rank", 0) and result.get("first_rank", 0) > 5:
                failures["high_rank_first_hit"].append({
                    "query": query,
                    "first_rank": result.get("first_rank", 0),
                })
    
    return failures


def main() -> int:
    """Run per-query analysis."""
    parser = argparse.ArgumentParser(description="Per-query analysis")
    parser.add_argument("--embedding", type=Path, required=True, help="Path to .wv file")
    parser.add_argument("--test-set", type=Path, required=True, help="Path to test set JSON")
    parser.add_argument("--output", type=Path, required=True, help="Output JSON file")
    
    args = parser.parse_args()
    
    if not HAS_GENSIM:
        print("Error: gensim required")
        return 1
    
    print(f"Loading embedding from {args.embedding}...")
    embedding = KeyedVectors.load(str(args.embedding))
    print(f"  Vocab size: {len(embedding)}")
    
    print(f"Loading test set from {args.test_set}...")
    with open(args.test_set) as f:
        test_data = json.load(f)
    
    queries = test_data.get("queries", test_data)
    print(f"  Queries: {len(queries)}")
    
    print("\nAnalyzing per-query performance...")
    per_query = analyze_per_query(embedding, queries)
    
    print("\nIdentifying failure modes...")
    failures = identify_failure_modes(per_query)
    
    # Summary statistics
    evaluated = [r for r in per_query.values() if r.get("status") == "evaluated"]
    if evaluated:
        avg_p = sum(r.get("p@10", 0) for r in evaluated) / len(evaluated)
        avg_r = sum(r.get("r@10", 0) for r in evaluated) / len(evaluated)
        avg_map = sum(r.get("map@10", 0) for r in evaluated) / len(evaluated)
    else:
        avg_p = avg_r = avg_map = 0.0
    
    output = {
        "summary": {
            "total_queries": len(queries),
            "evaluated": len(evaluated),
            "not_in_vocab": len(failures["not_in_vocab"]),
            "avg_p@10": avg_p,
            "avg_r@10": avg_r,
            "avg_map@10": avg_map,
        },
        "failure_modes": failures,
        "per_query": per_query,
    }
    
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"\n✅ Results saved to {args.output}")
    print(f"\nSummary:")
    print(f"  Evaluated: {len(evaluated)}/{len(queries)}")
    print(f"  Avg P@10: {avg_p:.4f}")
    print(f"  Avg R@10: {avg_r:.4f}")
    print(f"  Avg MAP@10: {avg_map:.4f}")
    print(f"\nFailure modes:")
    print(f"  Zero relevant retrieved: {len(failures['zero_relevant_retrieved'])}")
    print(f"  Low precision (<0.1): {len(failures['low_precision'])}")
    print(f"  Low recall (<0.1): {len(failures['low_recall'])}")
    print(f"  High rank first hit (>5): {len(failures['high_rank_first_hit'])}")
    
    return 0


if __name__ == "__main__":
    exit(main())

