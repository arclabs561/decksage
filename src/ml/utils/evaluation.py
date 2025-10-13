"""Shared evaluation utilities."""

from collections.abc import Callable
from math import log2
from typing import Any

from .constants import RELEVANCE_WEIGHTS


def compute_precision_at_k(
    predictions: list[str],
    labels: dict[str, list[str]],
    k: int = 10,
    weights: dict[str, float] | None = None,
) -> float:
    """
    Compute weighted precision@K.

    Args:
        predictions: Ranked list of predicted cards
        labels: Dict mapping relevance levels to card lists
        k: Number of predictions to consider
        weights: Relevance weights (defaults to RELEVANCE_WEIGHTS)

    Returns:
        Weighted precision score (0.0 to 1.0)
    """
    if weights is None:
        weights = RELEVANCE_WEIGHTS

    score = 0.0
    for pred in predictions[:k]:
        for level, weight in weights.items():
            if pred in labels.get(level, []):
                score += weight
                break

    return score / k


def evaluate_similarity(
    test_set: dict[str, Any],
    similarity_func: Callable[[str, int], list[tuple[str, float]]],
    top_k: int = 10,
    verbose: bool = False,
) -> dict[str, float]:
    """
    Standard evaluation loop.

    Args:
        test_set: Dict mapping queries to relevance labels
        similarity_func: Function that takes (query, k) and returns [(card, score), ...]
        top_k: Number of predictions to request
        verbose: Print per-query results

    Returns:
        Dict with evaluation metrics
    """
    scores = []
    ndcgs = []
    mrrs = []
    skipped = []

    for query, labels in test_set.items():
        try:
            # Get predictions
            predictions = similarity_func(query, top_k)

            if not predictions:
                skipped.append(query)
                continue

            # Extract just card names if tuples
            if isinstance(predictions[0], tuple):
                pred_cards = [card for card, _ in predictions]
            else:
                pred_cards = predictions

            # Compute P@k
            score = compute_precision_at_k(pred_cards, labels, k=top_k)
            scores.append(score)

            # Compute nDCG@k
            def rel_gain(card: str, _labels=labels) -> float:
                # Map relevance levels to weights; fall back to RELEVANCE_WEIGHTS
                if card in _labels.get("highly_relevant", []):
                    return RELEVANCE_WEIGHTS["highly_relevant"]
                if card in _labels.get("relevant", []):
                    return RELEVANCE_WEIGHTS["relevant"]
                if card in _labels.get("somewhat_relevant", []):
                    return RELEVANCE_WEIGHTS["somewhat_relevant"]
                if card in _labels.get("marginally_relevant", []):
                    return RELEVANCE_WEIGHTS.get("marginally_relevant", 0.0)
                return 0.0

            def dcg(items: list[str]) -> float:
                val = 0.0
                for i, c in enumerate(items[:top_k], 1):
                    val += rel_gain(c) / (log2(i + 1))
                return val

            # Build ideal ordering by relevance weights
            ideal = (
                labels.get("highly_relevant", [])
                + labels.get("relevant", [])
                + labels.get("somewhat_relevant", [])
                + labels.get("marginally_relevant", [])
            )
            idcg = dcg(ideal)
            ndcg = (dcg(pred_cards) / idcg) if idcg > 0 else 0.0
            ndcgs.append(ndcg)

            # Compute MRR@k (first hit in highly_relevant or relevant)
            target = set(labels.get("highly_relevant", [])) | set(labels.get("relevant", []))
            rr = 0.0
            for i, c in enumerate(pred_cards[:top_k], 1):
                if c in target:
                    rr = 1.0 / i
                    break
            mrrs.append(rr)

            if verbose:
                print(f"  {query}: {score:.3f}")

        except Exception as e:
            if verbose:
                print(f"  {query}: ERROR ({e})")
            skipped.append(query)

    avg_p_at_k = sum(scores) / len(scores) if scores else 0.0

    avg_ndcg = sum(ndcgs) / len(ndcgs) if ndcgs else 0.0
    avg_mrr = sum(mrrs) / len(mrrs) if mrrs else 0.0

    results = {
        f"p@{top_k}": avg_p_at_k,
        f"ndcg@{top_k}": avg_ndcg,
        f"mrr@{top_k}": avg_mrr,
        "num_queries": len(test_set),
        "num_evaluated": len(scores),
        "num_skipped": len(skipped),
    }

    if verbose:
        print(f"\n  P@{top_k}: {avg_p_at_k:.4f}")
        print(f"  Evaluated: {len(scores)}/{len(test_set)}")
        if skipped:
            print(f"  Skipped: {skipped}")

    return results


def jaccard_similarity(set1: set, set2: set) -> float:
    """
    Compute Jaccard similarity between two sets.

    Args:
        set1: First set
        set2: Second set

    Returns:
        Jaccard coefficient (0.0 to 1.0)
    """
    if not set1 or not set2:
        return 0.0

    intersection = len(set1 & set2)
    union = len(set1 | set2)

    return intersection / union if union > 0 else 0.0
