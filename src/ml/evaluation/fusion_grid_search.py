#!/usr/bin/env python3
"""
Grid search over fusion weights on a provided test set.

Designed for programmatic use in tests and small experiments.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from .fusion import FusionWeights, WeightedLateFusion
from .utils.evaluation import evaluate_similarity


@dataclass
class GridSearchResult:
    best_weights: FusionWeights
    best_score: float
    results: dict[tuple[float, float, float], float]


def grid_search_weights(
    fusion_builder: Callable[[FusionWeights], WeightedLateFusion],
    test_set: dict,
    step: float = 0.1,
    top_k: int = 10,
) -> GridSearchResult:
    """
    Search weights on the simplex with given step size.

    Args:
        fusion_builder: function that takes FusionWeights and returns a ready fusion model
        test_set: canonical mapping query -> graded relevance dict
        step: step size in [0,1]; e.g., 0.1 ⇒ ~66 combos
        top_k: evaluation cutoff
    Returns:
        GridSearchResult with best weights and scores map
    """

    def frange(start: float, stop: float, inc: float) -> Iterable[float]:
        x = start
        while x <= stop + 1e-9:
            yield round(x, 6)
            x += inc

    scores: dict[tuple[float, float, float], float] = {}
    best_w = FusionWeights()
    best_score = -1.0

    for w_e in frange(0.0, 1.0, step):
        for w_j in frange(0.0, 1.0 - w_e, step):
            w_f = max(0.0, 1.0 - (w_e + w_j))
            weights = FusionWeights(embed=w_e, jaccard=w_j, functional=w_f).normalized()
            fusion = fusion_builder(weights)

            def sim_func(q: str, k: int) -> list[tuple[str, float]]:
                return fusion.similar(q, k)

            res = evaluate_similarity(test_set, sim_func, top_k=top_k, verbose=False)
            p_at_k = float(res.get(f"p@{top_k}", 0.0))

            key = (weights.embed, weights.jaccard, weights.functional)
            scores[key] = p_at_k

            if p_at_k > best_score:
                best_score = p_at_k
                best_w = weights

    return GridSearchResult(best_weights=best_w, best_score=best_score, results=scores)


__all__ = ["GridSearchResult", "grid_search_weights"]
