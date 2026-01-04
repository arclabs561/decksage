"""
Training Validation Utilities

Provides utilities to validate training improvements and measure MRR gains
from various enhancements (hard negative mining, parameter tuning, etc.).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any


try:
    from gensim.models import KeyedVectors

    HAS_GENSIM = True
except ImportError:
    HAS_GENSIM = False

try:
    from .logging_config import get_logger

    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


def compute_ranking_metrics(
    embeddings: KeyedVectors,
    test_pairs: list[tuple[str, str]],
    k: int = 10,
) -> dict[str, float]:
    """
    Compute ranking metrics (MRR, P@K, R@K) for embeddings.

    Args:
        embeddings: Trained embeddings (KeyedVectors)
        test_pairs: List of (query, relevant_item) pairs
        k: Top-K for precision/recall (default: 10)

    Returns:
        Dictionary with metrics: {'mrr', 'p@k', 'r@k', 'num_evaluated'}
    """
    if not HAS_GENSIM:
        raise ImportError("gensim required for ranking metrics")

    mrr_sum = 0.0
    precision_sum = 0.0
    recall_sum = 0.0
    num_evaluated = 0

    for query, relevant in test_pairs:
        if query not in embeddings or relevant not in embeddings:
            continue

        try:
            # Get most similar items
            similar_items = embeddings.most_similar(query, topn=k * 2)  # Get more for recall
            similar_items_dict = {item: score for item, score in similar_items}

            # MRR: Reciprocal rank of first relevant item
            rank = None
            for i, (item, _) in enumerate(similar_items[:k], 1):
                if item == relevant:
                    rank = i
                    break

            if rank is not None:
                mrr_sum += 1.0 / rank
                precision_sum += 1.0  # Relevant item found in top-K
            else:
                # Check if relevant is in top 2K (for recall)
                rank_in_extended = None
                for i, (item, _) in enumerate(similar_items, 1):
                    if item == relevant:
                        rank_in_extended = i
                        break

                if rank_in_extended is not None:
                    recall_sum += 1.0 / min(rank_in_extended, k)  # Partial recall

            num_evaluated += 1
        except Exception as e:
            logger.warning(f"Error evaluating pair ({query}, {relevant}): {e}")
            continue

    if num_evaluated == 0:
        return {"mrr": 0.0, "p@k": 0.0, "r@k": 0.0, "num_evaluated": 0}

    return {
        "mrr": mrr_sum / num_evaluated,
        "p@k": precision_sum / num_evaluated,
        "r@k": recall_sum / num_evaluated,
        "num_evaluated": num_evaluated,
    }


def compare_embeddings(
    baseline_path: Path,
    improved_path: Path,
    test_pairs: list[tuple[str, str]],
    k: int = 10,
) -> dict[str, Any]:
    """
    Compare two embedding models and compute improvement metrics.

    Args:
        baseline_path: Path to baseline embeddings
        improved_path: Path to improved embeddings
        test_pairs: List of (query, relevant_item) pairs
        k: Top-K for precision/recall

    Returns:
        Dictionary with comparison metrics and improvements
    """
    if not HAS_GENSIM:
        raise ImportError("gensim required for comparison")

    logger.info(f"Loading baseline: {baseline_path}")
    baseline_wv = KeyedVectors.load(str(baseline_path))
    baseline_metrics = compute_ranking_metrics(baseline_wv, test_pairs, k)

    logger.info(f"Loading improved: {improved_path}")
    improved_wv = KeyedVectors.load(str(improved_path))
    improved_metrics = compute_ranking_metrics(improved_wv, test_pairs, k)

    # Compute improvements
    mrr_improvement = improved_metrics["mrr"] - baseline_metrics["mrr"]
    mrr_improvement_pct = (
        (mrr_improvement / baseline_metrics["mrr"] * 100) if baseline_metrics["mrr"] > 0 else 0.0
    )

    p_at_k_improvement = improved_metrics["p@k"] - baseline_metrics["p@k"]
    p_at_k_improvement_pct = (
        (p_at_k_improvement / baseline_metrics["p@k"] * 100) if baseline_metrics["p@k"] > 0 else 0.0
    )

    return {
        "baseline": baseline_metrics,
        "improved": improved_metrics,
        "improvements": {
            "mrr": {
                "absolute": mrr_improvement,
                "percent": mrr_improvement_pct,
            },
            "p@k": {
                "absolute": p_at_k_improvement,
                "percent": p_at_k_improvement_pct,
            },
        },
    }


def validate_training_improvements(
    embeddings_path: Path,
    test_pairs: list[tuple[str, str]],
    expected_mrr_gain: float = 0.03,  # Expected 3% MRR improvement
    k: int = 10,
) -> dict[str, Any]:
    """
    Validate that training improvements meet expected gains.

    Args:
        embeddings_path: Path to trained embeddings
        test_pairs: List of (query, relevant_item) pairs
        expected_mrr_gain: Expected MRR improvement (default: 0.03 = 3%)
        k: Top-K for precision/recall

    Returns:
        Dictionary with validation results
    """
    if not HAS_GENSIM:
        raise ImportError("gensim required for validation")

    logger.info(f"Validating embeddings: {embeddings_path}")
    wv = KeyedVectors.load(str(embeddings_path))
    metrics = compute_ranking_metrics(wv, test_pairs, k)

    meets_expectation = metrics["mrr"] >= expected_mrr_gain

    return {
        "metrics": metrics,
        "expected_mrr_gain": expected_mrr_gain,
        "meets_expectation": meets_expectation,
        "status": "PASS" if meets_expectation else "FAIL",
    }
