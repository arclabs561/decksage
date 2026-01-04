#!/usr/bin/env python3
"""
Measure individual signal performance on test set.

Scientific analysis: Measure P@10 for each similarity signal independently
to understand which signals contribute most and identify gaps.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

import numpy as np
from ..utils.logging_config import setup_script_logging

logger = setup_script_logging()


def precision_at_k(predictions: list[str], labels: set[str], k: int = 10) -> float:
    """Compute precision at k."""
    if not predictions:
        return 0.0
    
    top_k = predictions[:k]
    relevant = sum(1 for pred in top_k if pred in labels)
    return relevant / len(top_k)


def measure_signal_performance(
    test_set_path: Path,
    signal_name: str,
    similarity_fn: callable,
    top_k: int = 10,
) -> dict[str, Any]:
    """
    Measure P@10 for a single similarity signal.
    
    Args:
        test_set_path: Path to test set JSON
        signal_name: Name of signal (for reporting)
        similarity_fn: Function(query_card) -> list[(card, score)]
        top_k: Top k to evaluate
    
    Returns:
        Dict with performance metrics
    """
    # Load test set
    with open(test_set_path) as f:
        test_set = json.load(f)
    
    scores = []
    n_queries = len(test_set)
    
    logger.info(f"Measuring {signal_name} on {n_queries} queries...")
    
    for query, labels in test_set.items():
        try:
            # Get predictions
            predictions_with_scores = similarity_fn(query)
            predictions = [card for card, _ in predictions_with_scores]
            
            # Compute P@k
            p_at_k = precision_at_k(predictions, set(labels), k=top_k)
            scores.append(p_at_k)
            
        except Exception as e:
            logger.warning(f"Error processing query '{query}': {e}")
            scores.append(0.0)
    
    # Compute statistics
    mean_p = np.mean(scores)
    std_p = np.std(scores)
    std_err = std_p / np.sqrt(len(scores))
    
    # Bootstrap confidence interval
    n_bootstrap = 1000
    bootstrap_means = []
    for _ in range(n_bootstrap):
        sample = np.random.choice(scores, size=len(scores), replace=True)
        bootstrap_means.append(np.mean(sample))
    
    ci_lower = np.percentile(bootstrap_means, 2.5)
    ci_upper = np.percentile(bootstrap_means, 97.5)
    
    return {
        "signal": signal_name,
        "mean_p_at_k": float(mean_p),
        "std": float(std_p),
        "std_err": float(std_err),
        "ci_lower": float(ci_lower),
        "ci_upper": float(ci_upper),
        "n_queries": n_queries,
        "scores": scores,  # For further analysis
    }


def main():
    """Run signal performance analysis."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Measure individual signal performance"
    )
    parser.add_argument(
        "--test-set",
        type=Path,
        default=Path("experiments/test_set_canonical_magic.json"),
        help="Path to test set JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("experiments/signal_performance.json"),
        help="Output path for results",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Top k for P@k metric",
    )
    
    args = parser.parse_args()
    
    # TODO: Import actual similarity functions
    # For now, this is a template
    # Need to:
    # 1. Import embed similarity function
    # 2. Import jaccard similarity function
    # 3. Import functional similarity function
    # 4. Call measure_signal_performance for each
    
    logger.info("Signal performance measurement")
    logger.info(f"Test set: {args.test_set}")
    logger.info(f"Output: {args.output}")
    logger.info(f"Top K: {args.top_k}")
    
    # Placeholder: Actual implementation needs similarity functions
    logger.warning("This is a template. Need to implement similarity function imports.")
    
    results = {
        "test_set": str(args.test_set),
        "top_k": args.top_k,
        "signals": [],
    }
    
    # Save results
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)
    
    logger.info(f"Results saved to {args.output}")


if __name__ == "__main__":
    main()







