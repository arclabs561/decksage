#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pandas",
#   "numpy",
#   "gensim",
# ]
# ///
"""
Multi-task evaluation framework.

Evaluates embeddings on multiple tasks:
1. Co-occurrence similarity (cards in same decks)
2. Functional similarity (substitution pairs)
3. Substitution task (downstream)

Reports per-task metrics and overall multi-task performance.
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


def evaluate_cooccurrence_task(
    embedding: KeyedVectors,
    pairs_df: pd.DataFrame,
    test_queries: list[str],
    top_k: int = 10,
) -> dict[str, Any]:
    """
    Evaluate on co-occurrence task.
    
    For each query, find cards that co-occur with it in decks.
    Measure if embedding similarity captures co-occurrence.
    """
    from ml.utils.evaluation import (
        compute_precision_at_k,
        compute_recall_at_k,
        compute_map,
    )
    
    # Build co-occurrence ground truth
    cooccurrence_truth = {}
    for query in test_queries:
        cooccurring = set()
        for _, row in pairs_df.iterrows():
            n1, n2 = row.get("NAME_1", ""), row.get("NAME_2", "")
            if n1 == query:
                cooccurring.add(n2)
            elif n2 == query:
                cooccurring.add(n1)
        
        if len(cooccurring) >= 3:  # Need at least 3 for evaluation
            cooccurrence_truth[query] = {
                "highly_relevant": list(cooccurring)[:10],  # Top 10 by frequency
                "relevant": list(cooccurring)[10:20] if len(cooccurring) > 20 else [],
                "somewhat_relevant": [],
                "marginally_relevant": [],
            }
    
    # Evaluate
    scores = []
    recalls = []
    maps = []
    mrrs = []
    
    for query, labels in cooccurrence_truth.items():
        if query not in embedding:
            continue
        
        try:
            similar = embedding.most_similar(query, topn=top_k)
            predictions = [card for card, _ in similar]
            
            p_at_k = compute_precision_at_k(predictions, labels, k=top_k)
            r_at_k = compute_recall_at_k(predictions, labels, k=top_k)
            map_at_k = compute_map(predictions, labels, k=top_k)
            
            scores.append(p_at_k)
            recalls.append(r_at_k)
            maps.append(map_at_k)
            
            # MRR
            target = set(labels.get("highly_relevant", [])) | set(labels.get("relevant", []))
            rr = 0.0
            for rank, pred in enumerate(predictions, 1):
                if pred in target:
                    rr = 1.0 / rank
                    break
            mrrs.append(rr)
        except Exception:
            continue
    
    return {
        "task": "cooccurrence",
        "p@10": float(np.mean(scores)) if scores else 0.0,
        "r@10": float(np.mean(recalls)) if recalls else 0.0,
        "map@10": float(np.mean(maps)) if maps else 0.0,
        "mrr": float(np.mean(mrrs)) if mrrs else 0.0,
        "num_queries": len(cooccurrence_truth),
        "num_evaluated": len(scores),
    }


def evaluate_functional_similarity_task(
    embedding: KeyedVectors,
    test_set: dict[str, dict[str, Any]],
    top_k: int = 10,
) -> dict[str, Any]:
    """
    Evaluate on functional similarity task.
    
    Uses canonical test set with functional similarity labels
    (substitution pairs, similar function).
    """
    from ml.utils.evaluation import (
        compute_precision_at_k,
        compute_recall_at_k,
        compute_map,
    )
    
    scores = []
    recalls = []
    maps = []
    mrrs = []
    
    for query, labels in test_set.items():
        if query not in embedding:
            continue
        
        try:
            similar = embedding.most_similar(query, topn=top_k)
            predictions = [card for card, _ in similar]
            
            p_at_k = compute_precision_at_k(predictions, labels, k=top_k)
            r_at_k = compute_recall_at_k(predictions, labels, k=top_k)
            map_at_k = compute_map(predictions, labels, k=top_k)
            
            scores.append(p_at_k)
            recalls.append(r_at_k)
            maps.append(map_at_k)
            
            # MRR
            target = set(labels.get("highly_relevant", [])) | set(labels.get("relevant", []))
            rr = 0.0
            for rank, pred in enumerate(predictions, 1):
                if pred in target:
                    rr = 1.0 / rank
                    break
            mrrs.append(rr)
        except Exception:
            continue
    
    return {
        "task": "functional_similarity",
        "p@10": float(np.mean(scores)) if scores else 0.0,
        "r@10": float(np.mean(recalls)) if recalls else 0.0,
        "map@10": float(np.mean(maps)) if maps else 0.0,
        "mrr": float(np.mean(mrrs)) if mrrs else 0.0,
        "num_queries": len(test_set),
        "num_evaluated": len(scores),
    }


def evaluate_substitution_task(
    embedding: KeyedVectors,
    substitution_pairs: list[tuple[str, str]],
    top_k: int = 10,
) -> dict[str, Any]:
    """
    Evaluate on substitution task.
    
    For each (original, target) pair, check if target is in top-k for original.
    """
    found = 0
    ranks = []
    p_at_1 = 0
    p_at_5 = 0
    p_at_10 = 0
    
    for original, target in substitution_pairs:
        if original not in embedding:
            continue
        
        try:
            similar = embedding.most_similar(original, topn=top_k * 2)
            predictions = [card for card, _ in similar]
            
            # Find target in predictions
            for rank, pred in enumerate(predictions, 1):
                if pred == target:
                    found += 1
                    ranks.append(rank)
                    if rank <= 1:
                        p_at_1 += 1
                    if rank <= 5:
                        p_at_5 += 1
                    if rank <= 10:
                        p_at_10 += 1
                    break
        except Exception:
            continue
    
    total = len(substitution_pairs)
    
    return {
        "task": "substitution",
        "p@1": p_at_1 / total if total > 0 else 0.0,
        "p@5": p_at_5 / total if total > 0 else 0.0,
        "p@10": p_at_10 / total if total > 0 else 0.0,
        "found": found,
        "total": total,
        "avg_rank": float(np.mean(ranks)) if ranks else float("inf"),
    }


def compute_multitask_score(
    task_results: dict[str, dict[str, Any]],
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Compute weighted multi-task score."""
    if weights is None:
        weights = {
            "cooccurrence": 0.33,
            "functional_similarity": 0.33,
            "substitution": 0.34,
        }
    
    # Normalize each task's P@10 to [0, 1] (assuming max is 1.0)
    normalized_scores = {}
    for task, result in task_results.items():
        p10 = result.get("p@10", 0.0)
        normalized_scores[task] = p10 * weights.get(task, 0.0)
    
    overall_score = sum(normalized_scores.values())
    
    return {
        "overall_score": overall_score,
        "task_scores": normalized_scores,
        "weights": weights,
    }


def main() -> int:
    """Evaluate on multiple tasks."""
    parser = argparse.ArgumentParser(description="Multi-task evaluation")
    parser.add_argument("--embedding", type=Path, required=True, help="Embedding file (.wv)")
    parser.add_argument("--pairs", type=Path, required=True, help="Pairs CSV for co-occurrence task")
    parser.add_argument("--test-set", type=Path, help="Test set JSON for functional similarity")
    parser.add_argument("--substitution-pairs", type=Path, help="Substitution pairs JSON")
    parser.add_argument("--output", type=Path, required=True, help="Output JSON")
    parser.add_argument("--weights", type=str, help="Task weights as JSON: {\"cooccurrence\": 0.33, ...}")
    
    args = parser.parse_args()
    
    if not HAS_DEPS:
        print("Error: pandas, numpy, gensim required")
        return 1
    
    print(f"Loading embedding from {args.embedding}...")
    embedding = KeyedVectors.load(str(args.embedding))
    print(f"  Vocab size: {len(embedding)}")
    
    print(f"Loading pairs from {args.pairs}...")
    pairs_df = pd.read_csv(args.pairs, nrows=50000)  # Sample for speed
    print(f"  Pairs: {len(pairs_df)}")
    
    results = {
        "embedding": str(args.embedding),
        "tasks": {},
    }
    
    # Task 1: Co-occurrence
    print("\n📊 Evaluating co-occurrence task...")
    test_queries = list(embedding.key_to_index.keys())[:50]  # Sample queries
    cooccurrence_result = evaluate_cooccurrence_task(embedding, pairs_df, test_queries)
    results["tasks"]["cooccurrence"] = cooccurrence_result
    print(f"  P@10: {cooccurrence_result['p@10']:.4f}")
    print(f"  R@10: {cooccurrence_result['r@10']:.4f}")
    print(f"  MAP@10: {cooccurrence_result['map@10']:.4f}")
    
    # Task 2: Functional similarity
    if args.test_set and args.test_set.exists():
        print("\n📊 Evaluating functional similarity task...")
        with open(args.test_set) as f:
            test_data = json.load(f)
        functional_test = test_data.get("queries", test_data)
        functional_result = evaluate_functional_similarity_task(embedding, functional_test)
        results["tasks"]["functional_similarity"] = functional_result
        print(f"  P@10: {functional_result['p@10']:.4f}")
        print(f"  R@10: {functional_result['r@10']:.4f}")
        print(f"  MAP@10: {functional_result['map@10']:.4f}")
    
    # Task 3: Substitution
    if args.substitution_pairs and args.substitution_pairs.exists():
        print("\n📊 Evaluating substitution task...")
        with open(args.substitution_pairs) as f:
            substitution_data = json.load(f)
        if isinstance(substitution_data, list):
            substitution_pairs = [tuple(pair) for pair in substitution_data]
        else:
            substitution_pairs = []
        substitution_result = evaluate_substitution_task(embedding, substitution_pairs)
        results["tasks"]["substitution"] = substitution_result
        print(f"  P@10: {substitution_result['p@10']:.4f}")
        print(f"  Found: {substitution_result['found']}/{substitution_result['total']}")
    
    # Multi-task score
    weights = None
    if args.weights:
        weights = json.loads(args.weights)
    
    multitask_score = compute_multitask_score(results["tasks"], weights)
    results["multitask"] = multitask_score
    
    print(f"\n📊 Multi-task Performance:")
    print(f"  Overall score: {multitask_score['overall_score']:.4f}")
    for task, score in multitask_score["task_scores"].items():
        print(f"  {task}: {score:.4f} (weight: {multitask_score['weights'].get(task, 0):.2f})")
    
    # Save
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✅ Multi-task evaluation saved to {args.output}")
    
    return 0


if __name__ == "__main__":
    exit(main())

