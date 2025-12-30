#!/usr/bin/env python3
"""
Analyze failure cases in similarity predictions.

Scientific analysis: Categorize and understand why predictions fail
to identify specific, fixable issues.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def categorize_failure(
    query: str,
    predictions: list[str],
    labels: set[str],
    top_k: int = 10,
) -> str:
    """
    Categorize why a query failed.
    
    Returns:
        Failure category string
    """
    top_k_preds = set(predictions[:top_k])
    relevant_in_top_k = top_k_preds & labels
    
    if len(relevant_in_top_k) == 0:
        # No relevant cards in top k
        if len(labels) == 0:
            return "no_labels"
        return "no_relevant_in_top_k"
    
    # Some relevant, but not all
    if len(relevant_in_top_k) < len(labels):
        return "partial_relevant"
    
    # All relevant, but wrong order
    return "ranking_issue"


def analyze_failures(
    test_set_path: Path,
    predictions_path: Path | None = None,
    similarity_fn: callable | None = None,
    top_k: int = 10,
) -> dict[str, Any]:
    """
    Analyze failure cases in test set.
    
    Args:
        test_set_path: Path to test set JSON
        predictions_path: Optional path to saved predictions
        similarity_fn: Optional function to generate predictions
        top_k: Top k to analyze
    
    Returns:
        Dict with failure analysis
    """
    # Load test set
    with open(test_set_path) as f:
        test_set = json.load(f)
    
    # Load or generate predictions
    if predictions_path and predictions_path.exists():
        with open(predictions_path) as f:
            all_predictions = json.load(f)
    elif similarity_fn:
        all_predictions = {}
        for query in test_set.keys():
            try:
                preds = similarity_fn(query)
                all_predictions[query] = [card for card, _ in preds]
            except Exception as e:
                logger.warning(f"Error generating predictions for '{query}': {e}")
                all_predictions[query] = []
    else:
        logger.error("Need either predictions_path or similarity_fn")
        return {}
    
    # Analyze each query
    failure_categories = defaultdict(list)
    failure_examples = defaultdict(list)
    
    for query, labels in test_set.items():
        predictions = all_predictions.get(query, [])
        category = categorize_failure(query, predictions, set(labels), top_k)
        failure_categories[category].append(query)
        
        # Store example
        if len(failure_examples[category]) < 5:
            failure_examples[category].append({
                "query": query,
                "labels": list(labels),
                "top_predictions": predictions[:top_k],
                "relevant_in_top_k": list(set(predictions[:top_k]) & set(labels)),
            })
    
    # Summary statistics
    total_queries = len(test_set)
    failure_counts = {cat: len(queries) for cat, queries in failure_categories.items()}
    failure_rates = {cat: count / total_queries for cat, count in failure_counts.items()}
    
    return {
        "total_queries": total_queries,
        "failure_categories": dict(failure_categories),
        "failure_counts": failure_counts,
        "failure_rates": failure_rates,
        "examples": dict(failure_examples),
    }


def main():
    """Run failure analysis."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Analyze prediction failures")
    parser.add_argument(
        "--test-set",
        type=Path,
        default=Path("experiments/test_set_canonical_magic.json"),
        help="Path to test set JSON",
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        help="Path to saved predictions JSON (optional)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("experiments/failure_analysis.json"),
        help="Output path for results",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Top k for analysis",
    )
    
    args = parser.parse_args()
    
    logger.info("Failure case analysis")
    logger.info(f"Test set: {args.test_set}")
    logger.info(f"Output: {args.output}")
    
    # TODO: Import actual similarity function
    # For now, need predictions file or similarity function
    
    if args.predictions and args.predictions.exists():
        results = analyze_failures(
            args.test_set,
            predictions_path=args.predictions,
            top_k=args.top_k,
        )
    else:
        logger.warning("Need predictions file or similarity function")
        results = {}
    
    # Save results
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)
    
    logger.info(f"Results saved to {args.output}")
    
    # Print summary
    if results:
        print("\nFailure Analysis Summary:")
        print(f"Total queries: {results['total_queries']}")
        for category, rate in results['failure_rates'].items():
            print(f"  {category}: {rate:.1%} ({results['failure_counts'][category]} queries)")


if __name__ == "__main__":
    main()







