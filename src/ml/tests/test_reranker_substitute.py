"""Tests for text-similarity-boosted substitute reranking.

Verifies that the reranker:
1. Returns score_breakdown in metadata (per-source signal transparency)
2. Boosts text_e5 signal for substitute use_case
3. Produces rank-blended score normalization (not all-100% or always-0%)
4. Returns functionally similar cards, not just co-occurrence neighbors
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest


def _make_state_with_reranker(cards, sources, weights, intercept=0.0):
    """Build a minimal ApiState with reranker configured."""
    from ..api.models import ApiState, RerankerConfig

    state = ApiState()
    state.embeddings = _make_mock_kv(cards)
    state.card_metadata = {name: {"type": "Test"} for name in cards}
    state.reranker = RerankerConfig(
        features=list(weights.keys()),
        weights=weights,
        intercept=intercept,
    )
    state.reranker_embeddings = {name: _make_mock_kv(kv_cards) for name, kv_cards in sources.items()}
    return state


def _make_mock_kv(cards: dict[str, list[float]]) -> MagicMock:
    """Create a mock KeyedVectors with controllable most_similar."""
    kv = MagicMock()
    kv.key_to_index = {name: i for i, name in enumerate(cards)}
    kv.index_to_key = list(cards.keys())

    def _contains(self_or_name, name=None):
        # Handle both MagicMock.__contains__(self, name) and direct call
        key = name if name is not None else self_or_name
        return key in cards

    kv.__contains__ = _contains

    def _most_similar(query, topn=10):
        if query not in cards:
            raise KeyError(query)
        q_vec = np.array(cards[query])
        results = []
        for name, vec in cards.items():
            if name == query:
                continue
            cos = float(np.dot(q_vec, vec) / (np.linalg.norm(q_vec) * np.linalg.norm(vec) + 1e-9))
            results.append((name, cos))
        results.sort(key=lambda x: -x[1])
        return results[:topn]

    kv.most_similar = _most_similar
    return kv


class TestScoreBreakdown:
    """Score breakdown must be present and well-formed."""

    def test_breakdown_present_in_reranker_results(self):
        """Reranker results include score_breakdown dict in metadata."""
        from ..api.api import _similar_reranker
        from ..api.models import ApiState, RerankerConfig

        cards = {
            "QueryCard": [1, 0, 0],
            "ResultA": [0.9, 0.1, 0],
            "ResultB": [0.5, 0.5, 0],
        }
        state = ApiState()
        state.embeddings = _make_mock_kv(cards)
        # Provide card_metadata so _enrich_similar_card creates non-None metadata
        state.card_metadata = {name: {"type": "Test"} for name in cards}
        state.reranker = RerankerConfig(
            features=["src1", "src2"],
            weights={"src1": 0.5, "src2": 0.5},
            intercept=0.0,
        )
        state.reranker_embeddings = {
            "src1": _make_mock_kv(cards),
            "src2": _make_mock_kv({
                "QueryCard": [1, 0, 0],
                "ResultA": [0.8, 0.2, 0],
            }),
        }

        results = _similar_reranker(state, "QueryCard", 2, game="magic")
        assert len(results) >= 1
        bd = results[0].metadata.get("score_breakdown")
        assert bd is not None, "score_breakdown missing from metadata"
        assert isinstance(bd, dict)
        assert len(bd) > 0

    def test_breakdown_values_are_raw_cosine(self):
        """Breakdown values should be raw per-source cosine similarities, not normalized."""
        from ..api.api import _similar_reranker

        cards = {"Q": [1.0, 0.0], "A": [0.9, 0.1]}
        state = _make_state_with_reranker(
            cards, {"s1": cards}, {"s1": 1.0},
        )

        results = _similar_reranker(state, "Q", 1, game="magic")
        bd = results[0].metadata["score_breakdown"]
        # Raw cosine should be close to 1 for near-identical vectors
        assert bd["s1"] > 0.9


class TestSubstituteWeighting:
    """Substitute use_case must boost text signals."""

    def test_substitute_boosts_text_e5(self):
        """In substitute mode, text_e5 weight is at least 0.5."""
        from ..api.api import _similar_reranker

        all_cards = {"Bolt": [1, 0, 0], "CooccurCard": [0.9, 0.1, 0], "TextCard": [0.3, 0.7, 0]}
        state = _make_state_with_reranker(
            all_cards,
            sources={
                # v5_fused: CooccurCard is closer
                "v5_fused": {"Bolt": [1, 0, 0], "CooccurCard": [0.95, 0.05, 0], "TextCard": [0.1, 0.1, 0.8]},
                # text_e5: TextCard is closer
                "text_e5": {"Bolt": [1, 0, 0], "TextCard": [0.95, 0.05, 0], "CooccurCard": [0.1, 0.1, 0.8]},
            },
            weights={"v5_fused": 0.8, "text_e5": 0.2},  # co-occurrence dominant by default
        )

        # Without substitute: co-occurrence should dominate
        results_default = _similar_reranker(state, "Bolt", 2, game="magic", use_case="synergy")
        # With substitute: text should dominate
        results_sub = _similar_reranker(state, "Bolt", 2, game="magic", use_case="substitute")

        # The top result should differ between modes
        default_top = results_default[0].card
        sub_top = results_sub[0].card
        assert sub_top == "TextCard", f"Substitute mode should prefer TextCard, got {sub_top}"
        assert default_top == "CooccurCard", f"Default mode should prefer CooccurCard, got {default_top}"


class TestScoreNormalization:
    """Score normalization must produce a visible gradient."""

    def test_scores_not_all_bunched(self):
        """With 5+ results, scores should span at least 50% of the [0,1] range."""
        from ..api.api import _similar_reranker

        np.random.seed(42)
        cards = {"Query": list(np.random.randn(8).tolist())}
        for i in range(10):
            cards[f"Card{i}"] = list(np.random.randn(8).tolist())

        state = _make_state_with_reranker(cards, {"s1": cards}, {"s1": 1.0})
        results = _similar_reranker(state, "Query", 5, game="magic")
        scores = [r.similarity for r in results]
        score_range = max(scores) - min(scores)
        assert score_range >= 0.5, f"Score range {score_range:.2f} too narrow (all bunched)"

    def test_bottom_result_not_zero(self):
        """The bottom result should not always be 0% (min-max trap)."""
        from ..api.api import _similar_reranker

        cards = {"Q": [1.0, 0.0, 0.0]}
        for i in range(5):
            cards[f"C{i}"] = [0.9 - i * 0.05, 0.1 + i * 0.05, 0.0]

        state = _make_state_with_reranker(cards, {"s1": cards}, {"s1": 1.0})
        results = _similar_reranker(state, "Q", 5, game="magic")
        bottom_score = results[-1].similarity
        assert bottom_score > 0.05, f"Bottom score {bottom_score:.3f} too close to 0"
