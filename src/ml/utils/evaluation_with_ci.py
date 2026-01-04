#!/usr/bin/env python3
"""
Evaluation utilities with confidence intervals.

Scientific improvement: Add statistical rigor to evaluation metrics.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np


def precision_at_k_with_ci(
    predictions: list[str],
    labels: set[str],
    k: int = 10,
    n_bootstrap: int = 1000,
    confidence: float = 0.95,
) -> dict[str, float]:
    """
    Compute precision at k with bootstrap confidence interval.

    Args:
        predictions: List of predicted cards
        labels: Set of relevant card labels
        k: Top k to evaluate
        n_bootstrap: Number of bootstrap samples
        confidence: Confidence level (0.95 for 95% CI)

    Returns:
        Dict with mean, ci_lower, ci_upper
    """
    if not predictions:
        return {
            "mean": 0.0,
            "ci_lower": 0.0,
            "ci_upper": 0.0,
        }

    top_k = predictions[:k]
    relevant = sum(1 for pred in top_k if pred in labels)
    p_at_k = relevant / len(top_k)

    # Bootstrap CI (single query, so CI is just the point estimate)
    # For multiple queries, use bootstrap across queries
    return {
        "mean": p_at_k,
        "ci_lower": p_at_k,  # Single query has no variance
        "ci_upper": p_at_k,
    }


def evaluate_with_confidence(
    test_set: dict[str, list[str]],
    similarity_func: Callable[[str, int], list[tuple[str, float]]],
    top_k: int = 10,
    n_bootstrap: int = 1000,
    confidence: float = 0.95,
    verbose: bool = False,
) -> dict[str, float | list[float]]:
    """
    Evaluate similarity function on test set with confidence intervals.

    Args:
        test_set: Dict mapping query -> list of relevant labels
        similarity_func: Function(query, top_k) -> list[(card, score)]
        top_k: Top k to evaluate
        n_bootstrap: Number of bootstrap samples
        confidence: Confidence level
        verbose: Print per-query results

    Returns:
        Dict with metrics and confidence intervals
    """
    # Compute scores per query
    scores = []
    mrrs = []
    skipped = []
    skipped_reasons = {}

    for query, labels in test_set.items():
        try:
            predictions_with_scores = similarity_func(query, top_k)

            if not predictions_with_scores:
                skipped.append(query)
                skipped_reasons[query] = "no_predictions"
                if verbose:
                    print(f"  {query}: SKIPPED (no predictions)")
                continue

            predictions = [card for card, _ in predictions_with_scores]

            # P@k for this query
            top_k_preds = predictions[:top_k]
            relevant = sum(1 for pred in top_k_preds if pred in labels)
            p_at_k = relevant / len(top_k_preds) if top_k_preds else 0.0

            scores.append(p_at_k)

            # MRR for this query (first hit in labels)
            query_mrr = 0.0
            for rank, pred in enumerate(predictions, 1):
                if pred in labels:
                    query_mrr = 1.0 / rank
                    break
            mrrs.append(query_mrr)

            if verbose:
                print(
                    f"  {query}: P@{top_k}={p_at_k:.3f} ({relevant}/{len(top_k_preds)} relevant), MRR={query_mrr:.3f}"
                )
        except Exception as e:
            # Log error but continue
            skipped.append(query)
            skipped_reasons[query] = f"error: {e!s}"
            scores.append(0.0)
            mrrs.append(0.0)
            if verbose:
                print(f"  {query}: ERROR ({e})")

    if not scores:
        return {
            "p@10": 0.0,
            "p@10_ci_lower": 0.0,
            "p@10_ci_upper": 0.0,
            "p@10_std": 0.0,
            "mrr@10": 0.0,
            "mrr@10_ci_lower": 0.0,
            "mrr@10_ci_upper": 0.0,
            "num_queries": len(test_set),
            "num_evaluated": 0,
            "num_skipped": len(skipped),
        }

    # Bootstrap confidence intervals for both P@10 and MRR
    def bootstrap_ci(
        values: list[float], metric_name: str = "metric"
    ) -> tuple[float, float, float]:
        """Compute bootstrap CI for a list of values"""
        if not values:
            return 0.0, 0.0, 0.0

        # Optimize: use vectorized operations when possible
        values_array = np.array(values)
        n = len(values)

        if verbose:
            print(
                f"    Computing bootstrap CI for {metric_name} (n={n}, n_bootstrap={n_bootstrap})..."
            )

        # Vectorized bootstrap: sample all at once
        # Generate all bootstrap samples in one go (memory efficient for large n_bootstrap)
        bootstrap_means = []
        chunk_size = min(1000, n_bootstrap)  # Process in chunks to avoid memory issues

        for chunk_start in range(0, n_bootstrap, chunk_size):
            chunk_end = min(chunk_start + chunk_size, n_bootstrap)
            # Generate chunk_size samples at once
            samples = np.random.choice(
                values_array, size=(chunk_end - chunk_start, n), replace=True
            )
            bootstrap_means.extend(np.mean(samples, axis=1).tolist())

        alpha = 1 - confidence
        mean_val = float(np.mean(values_array))
        ci_lower = float(np.percentile(bootstrap_means, 100 * alpha / 2))
        ci_upper = float(np.percentile(bootstrap_means, 100 * (1 - alpha / 2)))
        return mean_val, ci_lower, ci_upper

    p_mean, p_ci_lower, p_ci_upper = bootstrap_ci(scores, "P@10")
    mrr_mean, mrr_ci_lower, mrr_ci_upper = bootstrap_ci(mrrs, "MRR")

    # Return format compatible with both evaluation.py and calling code
    # Include both formats for compatibility
    result = {
        # New format (p@10, mrr@10)
        "p@10": p_mean,
        "p@10_ci_lower": p_ci_lower,
        "p@10_ci_upper": p_ci_upper,
        "p@10_std": float(np.std(scores)) if scores else 0.0,
        "mrr@10": mrr_mean,
        "mrr@10_ci_lower": mrr_ci_lower,
        "mrr@10_ci_upper": mrr_ci_upper,
        # Legacy format (mean, ci_lower, ci_upper) for ab_testing.py compatibility
        "mean": p_mean,
        "ci_lower": p_ci_lower,
        "ci_upper": p_ci_upper,
        "std": float(np.std(scores)) if scores else 0.0,
        # Metadata
        "num_queries": len(test_set),
        "num_evaluated": len(scores),
        "num_skipped": len(skipped),
        "scores": scores,  # For further analysis
    }

    if skipped and verbose:
        print(f"\n  Skipped {len(skipped)} queries:")
        for q in list(skipped)[:10]:
            print(f"    {q}: {skipped_reasons.get(q, 'unknown')}")
        if len(skipped) > 10:
            print(f"    ... and {len(skipped) - 10} more")

    return result


def format_metric_with_ci(
    mean: float,
    ci_lower: float,
    ci_upper: float,
    precision: int = 4,
) -> str:
    """
    Format metric with confidence interval for display.

    Example: "0.0882 (95% CI: 0.0751, 0.1013)"
    """
    return f"{mean:.{precision}f} (95% CI: {ci_lower:.{precision}f}, {ci_upper:.{precision}f})"


__all__ = [
    "evaluate_with_confidence",
    "format_metric_with_ci",
    "precision_at_k_with_ci",
]
