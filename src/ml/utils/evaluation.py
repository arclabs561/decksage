"""Shared evaluation utilities."""

from collections.abc import Callable
from math import log2
from typing import Any


try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

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


def compute_recall_at_k(
    predictions: list[str],
    labels: dict[str, list[str]],
    k: int = 10,
    weights: dict[str, float] | None = None,
) -> float:
    """
    Compute weighted recall@K.

    Args:
        predictions: Ranked list of predicted cards
        labels: Dict mapping relevance levels to card lists
        k: Number of predictions to consider
        weights: Relevance weights (defaults to RELEVANCE_WEIGHTS)

    Returns:
        Weighted recall score (0.0 to 1.0)
    """
    if weights is None:
        weights = RELEVANCE_WEIGHTS

    # Get all relevant cards with their weights
    all_relevant = {}
    for level, weight in weights.items():
        for card in labels.get(level, []):
            all_relevant[card] = max(all_relevant.get(card, 0.0), weight)

    if not all_relevant:
        return 0.0

    # Count how many relevant items were retrieved
    retrieved_relevant = 0.0
    total_relevant_weight = sum(all_relevant.values())

    for pred in predictions[:k]:
        if pred in all_relevant:
            retrieved_relevant += all_relevant[pred]

    return retrieved_relevant / total_relevant_weight if total_relevant_weight > 0 else 0.0


def compute_map(
    predictions: list[str],
    labels: dict[str, list[str]],
    k: int = 10,
    weights: dict[str, float] | None = None,
) -> float:
    """
    Compute Mean Average Precision (MAP)@K.

    MAP = (1/|R|) * sum(Precision@i for each relevant item at rank i)

    Args:
        predictions: Ranked list of predicted cards
        labels: Dict mapping relevance levels to card lists
        k: Number of predictions to consider
        weights: Relevance weights (defaults to RELEVANCE_WEIGHTS)

    Returns:
        MAP score (0.0 to 1.0)
    """
    if weights is None:
        weights = RELEVANCE_WEIGHTS

    # Get all relevant cards (binary: highly_relevant or relevant)
    relevant_set = set(labels.get("highly_relevant", [])) | set(labels.get("relevant", []))

    if not relevant_set:
        return 0.0

    # Compute average precision
    relevant_retrieved = 0
    precision_sum = 0.0

    for rank, pred in enumerate(predictions[:k], 1):
        if pred in relevant_set:
            relevant_retrieved += 1
            precision_at_rank = relevant_retrieved / rank
            precision_sum += precision_at_rank

    # MAP = average of precisions at each relevant item
    return precision_sum / len(relevant_set) if relevant_set else 0.0


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
    recalls = []
    maps = []
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

            # Compute R@k
            recall = compute_recall_at_k(pred_cards, labels, k=top_k)
            recalls.append(recall)

            # Compute MAP@k
            map_score = compute_map(pred_cards, labels, k=top_k)
            maps.append(map_score)

            # Compute nDCG@k
            def rel_gain(card: str, _labels: dict[str, Any] = labels) -> float:
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
                print(
                    f"  {query}: P@{top_k}={score:.3f}, R@{top_k}={recall:.3f}, MAP={map_score:.3f}"
                )

        except Exception as e:
            if verbose:
                print(f"  {query}: ERROR ({e})")
            skipped.append(query)

    avg_p_at_k = sum(scores) / len(scores) if scores else 0.0
    avg_r_at_k = sum(recalls) / len(recalls) if recalls else 0.0
    avg_map = sum(maps) / len(maps) if maps else 0.0
    avg_ndcg = sum(ndcgs) / len(ndcgs) if ndcgs else 0.0
    avg_mrr = sum(mrrs) / len(mrrs) if mrrs else 0.0

    results = {
        f"p@{top_k}": avg_p_at_k,
        f"r@{top_k}": avg_r_at_k,
        f"map@{top_k}": avg_map,
        f"ndcg@{top_k}": avg_ndcg,
        f"mrr@{top_k}": avg_mrr,
        "num_queries": len(test_set),
        "num_evaluated": len(scores),
        "num_skipped": len(skipped),
    }

    if verbose:
        print(f"\n  P@{top_k}: {avg_p_at_k:.4f}")
        print(f"  R@{top_k}: {avg_r_at_k:.4f}")
        print(f"  MAP@{top_k}: {avg_map:.4f}")
        print(f"  nDCG@{top_k}: {avg_ndcg:.4f}")
        print(f"  MRR@{top_k}: {avg_mrr:.4f}")
        print(f"  Evaluated: {len(scores)}/{len(test_set)}")
        if skipped:
            print(f"  Skipped: {skipped}")

    return results


def evaluate_with_confidence(
    test_set: dict[str, Any],
    similarity_func: Callable[[str, int], list[tuple[str, float]]],
    top_k: int = 10,
    n_bootstrap: int = 1000,
    confidence: float = 0.95,
    verbose: bool = False,
) -> dict[str, Any]:
    """
    Evaluate similarity function with bootstrap confidence intervals.

    Args:
        test_set: Dict mapping queries to relevance labels
        similarity_func: Function that takes (query, k) and returns [(card, score), ...]
        top_k: Number of predictions to request
        n_bootstrap: Number of bootstrap samples
        confidence: Confidence level (0.95 for 95% CI)
        verbose: Print per-query results

    Returns:
        Dict with metrics and confidence intervals
    """
    if not HAS_NUMPY:
        # Fall back to standard evaluation if numpy not available
        result = evaluate_similarity(test_set, similarity_func, top_k, verbose)
        # Add CI placeholders
        result[f"p@{top_k}_ci_lower"] = result[f"p@{top_k}"]
        result[f"p@{top_k}_ci_upper"] = result[f"p@{top_k}"]
        result[f"ndcg@{top_k}_ci_lower"] = result[f"ndcg@{top_k}"]
        result[f"ndcg@{top_k}_ci_upper"] = result[f"ndcg@{top_k}"]
        result[f"mrr@{top_k}_ci_lower"] = result[f"mrr@{top_k}"]
        result[f"mrr@{top_k}_ci_upper"] = result[f"mrr@{top_k}"]
        return result

    # Compute scores per query
    scores = []
    recalls = []
    maps = []
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

            # Compute R@k
            recall = compute_recall_at_k(pred_cards, labels, k=top_k)
            recalls.append(recall)

            # Compute MAP@k
            map_score = compute_map(pred_cards, labels, k=top_k)
            maps.append(map_score)

            # Compute nDCG@k
            def rel_gain(card: str, _labels: dict[str, Any] = labels) -> float:
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

            # Build ideal ordering
            ideal = (
                labels.get("highly_relevant", [])
                + labels.get("relevant", [])
                + labels.get("somewhat_relevant", [])
                + labels.get("marginally_relevant", [])
            )
            idcg = dcg(ideal)
            ndcg = (dcg(pred_cards) / idcg) if idcg > 0 else 0.0
            ndcgs.append(ndcg)

            # Compute MRR@k
            target = set(labels.get("highly_relevant", [])) | set(labels.get("relevant", []))
            rr = 0.0
            for i, c in enumerate(pred_cards[:top_k], 1):
                if c in target:
                    rr = 1.0 / i
                    break
            mrrs.append(rr)

            if verbose:
                print(
                    f"  {query}: P@{top_k}={score:.3f}, R@{top_k}={recall:.3f}, MAP={map_score:.3f}"
                )

        except Exception as e:
            if verbose:
                print(f"  {query}: ERROR ({e})")
            skipped.append(query)

    if not scores:
        return {
            f"p@{top_k}": 0.0,
            f"p@{top_k}_ci_lower": 0.0,
            f"p@{top_k}_ci_upper": 0.0,
            f"r@{top_k}": 0.0,
            f"r@{top_k}_ci_lower": 0.0,
            f"r@{top_k}_ci_upper": 0.0,
            f"map@{top_k}": 0.0,
            f"map@{top_k}_ci_lower": 0.0,
            f"map@{top_k}_ci_upper": 0.0,
            f"ndcg@{top_k}": 0.0,
            f"ndcg@{top_k}_ci_lower": 0.0,
            f"ndcg@{top_k}_ci_upper": 0.0,
            f"mrr@{top_k}": 0.0,
            f"mrr@{top_k}_ci_lower": 0.0,
            f"mrr@{top_k}_ci_upper": 0.0,
            "num_queries": len(test_set),
            "num_evaluated": 0,
            "num_skipped": len(skipped),
        }

    # Bootstrap confidence intervals
    def bootstrap_ci(values: list[float]) -> tuple[float, float]:
        """Compute bootstrap CI for a list of values"""
        bootstrap_means = []
        for _ in range(n_bootstrap):
            sample = np.random.choice(values, size=len(values), replace=True)
            bootstrap_means.append(np.mean(sample))

        alpha = 1 - confidence
        ci_lower = float(np.percentile(bootstrap_means, 100 * alpha / 2))
        ci_upper = float(np.percentile(bootstrap_means, 100 * (1 - alpha / 2)))
        return ci_lower, ci_upper

    p_ci_lower, p_ci_upper = bootstrap_ci(scores)
    r_ci_lower, r_ci_upper = bootstrap_ci(recalls) if recalls else (0.0, 0.0)
    map_ci_lower, map_ci_upper = bootstrap_ci(maps) if maps else (0.0, 0.0)
    ndcg_ci_lower, ndcg_ci_upper = bootstrap_ci(ndcgs) if ndcgs else (0.0, 0.0)
    mrr_ci_lower, mrr_ci_upper = bootstrap_ci(mrrs) if mrrs else (0.0, 0.0)

    results = {
        f"p@{top_k}": float(np.mean(scores)),
        f"p@{top_k}_ci_lower": p_ci_lower,
        f"p@{top_k}_ci_upper": p_ci_upper,
        f"p@{top_k}_std": float(np.std(scores)),
        f"r@{top_k}": float(np.mean(recalls)) if recalls else 0.0,
        f"r@{top_k}_ci_lower": r_ci_lower,
        f"r@{top_k}_ci_upper": r_ci_upper,
        f"r@{top_k}_std": float(np.std(recalls)) if recalls else 0.0,
        f"map@{top_k}": float(np.mean(maps)) if maps else 0.0,
        f"map@{top_k}_ci_lower": map_ci_lower,
        f"map@{top_k}_ci_upper": map_ci_upper,
        f"map@{top_k}_std": float(np.std(maps)) if maps else 0.0,
        f"ndcg@{top_k}": float(np.mean(ndcgs)) if ndcgs else 0.0,
        f"ndcg@{top_k}_ci_lower": ndcg_ci_lower,
        f"ndcg@{top_k}_ci_upper": ndcg_ci_upper,
        f"mrr@{top_k}": float(np.mean(mrrs)) if mrrs else 0.0,
        f"mrr@{top_k}_ci_lower": mrr_ci_lower,
        f"mrr@{top_k}_ci_upper": mrr_ci_upper,
        "num_queries": len(test_set),
        "num_evaluated": len(scores),
        "num_skipped": len(skipped),
    }

    if verbose:
        print(
            f"\n  P@{top_k}: {results[f'p@{top_k}']:.4f} (95% CI: {p_ci_lower:.4f}, {p_ci_upper:.4f})"
        )
        print(
            f"  R@{top_k}: {results[f'r@{top_k}']:.4f} (95% CI: {r_ci_lower:.4f}, {r_ci_upper:.4f})"
        )
        print(
            f"  MAP@{top_k}: {results[f'map@{top_k}']:.4f} (95% CI: {map_ci_lower:.4f}, {map_ci_upper:.4f})"
        )
        print(
            f"  nDCG@{top_k}: {results[f'ndcg@{top_k}']:.4f} (95% CI: {ndcg_ci_lower:.4f}, {ndcg_ci_upper:.4f})"
        )
        print(
            f"  MRR@{top_k}: {results[f'mrr@{top_k}']:.4f} (95% CI: {mrr_ci_lower:.4f}, {mrr_ci_upper:.4f})"
        )
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
