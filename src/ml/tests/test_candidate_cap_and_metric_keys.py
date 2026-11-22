"""Regression tests: neighbour cap uses canonical weight keys; CI metric keys name top_k."""

from __future__ import annotations


def _star(query: str, heavy: set[str]):
    """A query card with 299 neighbours; `heavy` ones have weight 1000."""
    names = [f"c{i:03d}" for i in range(0, 300) if f"c{i:03d}" != query]
    adj = {query: set(names), **{n: {query} for n in names}}
    weights = {}
    for n in names:
        key = (query, n) if query <= n else (n, query)
        weights[key] = 1000 if n in heavy else 1
    return adj, weights


def test_candidate_cap_keeps_heavy_neighbours_that_sort_before_the_query():
    from ..similarity.fusion import WeightedLateFusion

    heavy = {"c010", "c020", "c290"}
    adj, weights = _star("c150", heavy)
    fusion = WeightedLateFusion(adj=adj, graph_weights=weights, candidate_topn=100)

    candidates = fusion._get_candidates("c150")

    # c010 and c020 sort before the query; their weights live under
    # ("c010", "c150"), not ("c150", "c010").
    assert heavy <= set(candidates)


def test_confidence_metric_keys_name_the_cutoff_used():
    from ..utils.evaluation_with_ci import evaluate_with_confidence

    test_set = {"q": ["a", "b"]}

    def rank(query, k):
        return [("a", 1.0), ("x", 0.9), ("b", 0.8), ("y", 0.7)][:k]

    at3 = evaluate_with_confidence(test_set, rank, top_k=3, n_bootstrap=5)
    assert "p@3" in at3 and "mrr@3" in at3 and "p@3_ci_lower" in at3
    assert "p@10" not in at3

    at10 = evaluate_with_confidence(test_set, rank, n_bootstrap=5)
    assert "p@10" in at10 and "mrr@10" in at10

    empty = evaluate_with_confidence({}, rank, top_k=5, n_bootstrap=5)
    assert "p@5" in empty and "p@10" not in empty
