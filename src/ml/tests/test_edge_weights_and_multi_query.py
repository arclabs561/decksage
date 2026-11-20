"""Regression tests: co-occurrence edge weights and multi-query fusion order."""

from __future__ import annotations

import dataclasses
from datetime import datetime


def test_multi_copy_cards_give_one_edge_weighted_by_counts():
    from ..data.incremental_graph import IncrementalCardGraph

    graph = IncrementalCardGraph()
    deck = {
        "game": "magic",
        "cards": [{"name": "Sol Ring", "count": 4}, {"name": "Mana Crypt", "count": 3}],
    }
    graph.add_deck(deck, datetime(2024, 1, 1), deck_id="d1")

    assert list(graph.edges) == [("Mana Crypt", "Sol Ring", "co_occurrence")]
    edge = graph.edges[("Mana Crypt", "Sol Ring", "co_occurrence")]
    assert edge.weight == 12
    # One deck in January, not one per pair of copies.
    assert edge.monthly_counts == {"2024-01": 1}

    graph.add_deck(deck, datetime(2024, 1, 2), deck_id="d2")
    assert edge.weight == 24
    assert edge.monthly_counts == {"2024-01": 2}
    assert all(key[0] != key[1] for key in graph.edges)


def _jaccard_only_fusion(aggregator: str):
    from ..similarity.fusion import FusionWeights, WeightedLateFusion

    zeros = {f.name: 0.0 for f in dataclasses.fields(FusionWeights)}
    zeros["jaccard"] = 1.0
    adj = {
        "q": {"a", "b", "c"},
        "a": {"q", "b", "c"},  # shares b, c with q: most similar
        "b": {"q", "a"},  # shares a
        "c": {"q"},  # shares nothing
    }
    return WeightedLateFusion(adj=adj, weights=FusionWeights(**zeros), aggregator=aggregator)


def test_similar_multi_orders_like_similar_under_every_aggregator():
    for aggregator in ("rrf", "isr", "weighted"):
        fusion = _jaccard_only_fusion(aggregator)
        single = [name for name, _ in fusion.similar("q", k=3)]
        multi = [name for name, _ in fusion.similar_multi(["q"], k=3)]
        assert single == ["a", "b", "c"], (aggregator, single)
        assert multi == single, (aggregator, multi)


def test_similar_multi_scores_decrease():
    fusion = _jaccard_only_fusion("rrf")
    scores = [score for _, score in fusion.similar_multi(["q", "a"], k=5)]
    assert scores == sorted(scores, reverse=True)
