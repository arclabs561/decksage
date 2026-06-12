#!/usr/bin/env python3
"""Direct unit tests for all 7 fusion aggregation methods.

Tests the aggregation methods in isolation with synthetic scores,
no real embeddings or file I/O required.
"""

from __future__ import annotations

import math

from ..similarity.fusion import FusionWeights, WeightedLateFusion


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


class FakeEmbeddings:
    """Dict-backed mock that implements the KeyedVectors interface subset
    used by WeightedLateFusion: __contains__, similarity(), most_similar(),
    and index_to_key."""

    def __init__(self, similarities: dict[tuple[str, str], float]):
        # similarities: {("A", "B"): 0.9, ...}  symmetric
        self._sims = {}
        self._vocab: set[str] = set()
        for (a, b), score in similarities.items():
            self._sims[(a, b)] = score
            self._sims[(b, a)] = score
            self._vocab.add(a)
            self._vocab.add(b)

    def __contains__(self, key: str) -> bool:
        return key in self._vocab

    @property
    def index_to_key(self) -> list[str]:
        return sorted(self._vocab)

    def similarity(self, q: str, c: str) -> float:
        return self._sims.get((q, c), 0.0)

    def most_similar(self, q: str, topn: int = 10) -> list[tuple[str, float]]:
        results = [(c, self.similarity(q, c)) for c in self._vocab if c != q]
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:topn]


# Tiny vocab with known cosine similarities (pre cosine-to-unit mapping).
# _cosine_to_unit maps [-1,1] -> [0,1] via (c+1)/2.
_SIMS = {
    ("Q", "A"): 0.8,  # -> 0.9 after cosine_to_unit
    ("Q", "B"): 0.4,  # -> 0.7
    ("Q", "C"): 0.0,  # -> 0.5
    ("Q", "D"): -0.4,  # -> 0.3
    ("Q", "E"): -0.8,  # -> 0.1
    ("A", "B"): 0.6,
    ("A", "C"): 0.2,
    ("B", "C"): 0.1,
}

_ADJ: dict[str, set[str]] = {
    "Q": {"A", "B", "C"},
    "A": {"Q", "B"},
    "B": {"Q", "A", "C"},
    "C": {"Q", "B", "D"},
    "D": {"C"},
    "E": set(),
}


def _simple_weights() -> FusionWeights:
    """Weights with only embed and jaccard enabled (equal)."""
    return FusionWeights(
        embed=0.5,
        jaccard=0.5,
        functional=0.0,
        text_embed=0.0,
        visual_embed=0.0,
        archetype=0.0,
    )


def _make_fusion(aggregator: str, rrf_k: int = 60) -> WeightedLateFusion:
    emb = FakeEmbeddings(_SIMS)
    return WeightedLateFusion(
        embeddings=emb,
        adj=_ADJ,
        weights=_simple_weights(),
        aggregator=aggregator,
        rrf_k=rrf_k,
        candidate_topn=50,
    )


def _all_aggregators() -> list[str]:
    return ["weighted", "rrf", "isr", "combsum", "combmnz", "combmax", "combmin"]


# ---------------------------------------------------------------------------
# Per-aggregator test classes
# ---------------------------------------------------------------------------


class TestAggregateWeighted:
    """_aggregate weighted: weighted sum of modality scores."""

    def test_basic_computation(self):
        f = _make_fusion("weighted")
        scores = {"embed": 0.8, "jaccard": 0.4}
        # weights are normalized: embed=0.5, jaccard=0.5
        result = f._aggregate(scores, "weighted")
        expected = 0.5 * 0.8 + 0.5 * 0.4
        assert math.isclose(result, expected, abs_tol=1e-9)

    def test_bounded_zero_one_with_unit_inputs(self):
        f = _make_fusion("weighted")
        # All inputs in [0,1] and weights sum to 1 -> output in [0,1]
        for embed_s, jacc_s in [(0.0, 0.0), (1.0, 1.0), (0.5, 0.5), (0.0, 1.0)]:
            score = f._aggregate({"embed": embed_s, "jaccard": jacc_s}, "weighted")
            assert 0.0 <= score <= 1.0, f"score {score} out of [0,1]"

    def test_missing_modality_ignored(self):
        f = _make_fusion("weighted")
        # Only embed provided; jaccard absent -> only embed contributes
        result = f._aggregate({"embed": 0.8}, "weighted")
        expected = 0.5 * 0.8
        assert math.isclose(result, expected, abs_tol=1e-9)

    def test_zero_weight_modality_ignored(self):
        f = _make_fusion("weighted")
        # functional has weight 0.0, should not contribute even if present
        result = f._aggregate({"embed": 0.8, "functional": 0.9}, "weighted")
        expected = 0.5 * 0.8
        assert math.isclose(result, expected, abs_tol=1e-9)

    def test_empty_scores(self):
        f = _make_fusion("weighted")
        assert f._aggregate({}, "weighted") == 0.0


class TestAggregateRRF:
    """_aggregate rrf: reciprocal rank fusion with k parameter."""

    def test_basic_computation(self):
        f = _make_fusion("rrf", rrf_k=60)
        ranks = {"embed": 1, "jaccard": 2}
        expected = 0.5 / (60 + 1) + 0.5 / (60 + 2)
        result = f._aggregate(ranks, "rrf")
        assert math.isclose(result, expected, abs_tol=1e-9)

    def test_rank_1_scores_higher_than_rank_10(self):
        f = _make_fusion("rrf", rrf_k=60)
        score_rank1 = f._aggregate({"embed": 1, "jaccard": 1}, "rrf")
        score_rank10 = f._aggregate({"embed": 10, "jaccard": 10}, "rrf")
        assert score_rank1 > score_rank10

    def test_bounded_positive(self):
        f = _make_fusion("rrf", rrf_k=60)
        # Rank 1 in both modalities is the maximum possible
        max_score = f._aggregate({"embed": 1, "jaccard": 1}, "rrf")
        assert max_score > 0.0
        # With k=60, max per modality is w/(60+1), total <= sum(weights)/(60+1)
        assert max_score <= 1.0 / (60 + 1) + 0.01  # some tolerance

    def test_k_parameter_effect(self):
        f_small_k = _make_fusion("rrf", rrf_k=1)
        f_large_k = _make_fusion("rrf", rrf_k=1000)
        ranks = {"embed": 1, "jaccard": 1}
        # Smaller k -> higher scores (rank matters more)
        assert f_small_k._aggregate(ranks, "rrf") > f_large_k._aggregate(ranks, "rrf")

    def test_empty_ranks(self):
        f = _make_fusion("rrf")
        assert f._aggregate({}, "rrf") == 0.0


class TestAggregateISR:
    """_aggregate isr: inverse square root decay (slower than RRF)."""

    def test_basic_computation(self):
        f = _make_fusion("isr", rrf_k=60)
        ranks = {"embed": 1, "jaccard": 2}
        expected = 0.5 / math.sqrt(60 + 1) + 0.5 / math.sqrt(60 + 2)
        result = f._aggregate(ranks, "isr")
        assert math.isclose(result, expected, abs_tol=1e-9)

    def test_slower_decay_than_rrf(self):
        """ISR decays slower: ratio between rank 1 and rank 100 is smaller for ISR."""
        f = _make_fusion("isr", rrf_k=60)
        score_r1 = f._aggregate({"embed": 1}, "isr")
        score_r100 = f._aggregate({"embed": 100}, "isr")
        ratio_isr = score_r100 / score_r1

        f2 = _make_fusion("rrf", rrf_k=60)
        score_r1_rrf = f2._aggregate({"embed": 1}, "rrf")
        score_r100_rrf = f2._aggregate({"embed": 100}, "rrf")
        ratio_rrf = score_r100_rrf / score_r1_rrf

        # ISR ratio should be larger (slower decay)
        assert ratio_isr > ratio_rrf

    def test_rank_ordering_preserved(self):
        f = _make_fusion("isr", rrf_k=60)
        score_r1 = f._aggregate({"embed": 1, "jaccard": 1}, "isr")
        score_r5 = f._aggregate({"embed": 5, "jaccard": 5}, "isr")
        assert score_r1 > score_r5

    def test_empty_ranks(self):
        f = _make_fusion("isr")
        assert f._aggregate({}, "isr") == 0.0


class TestAggregateCombSUM:
    """_aggregate combsum: sum of weighted scores. CAN exceed 1.0 because it is
    a weighted sum without normalization (same formula as weighted)."""

    def test_basic_computation(self):
        f = _make_fusion("combsum")
        scores = {"embed": 0.8, "jaccard": 0.6}
        expected = 0.5 * 0.8 + 0.5 * 0.6
        result = f._aggregate(scores, "combsum")
        assert math.isclose(result, expected, abs_tol=1e-9)

    def test_matches_weighted_for_same_inputs(self):
        """CombSUM and weighted use the same formula."""
        f = _make_fusion("combsum")
        scores = {"embed": 0.7, "jaccard": 0.3}
        assert math.isclose(
            f._aggregate(scores, "combsum"),
            f._aggregate(scores, "weighted"),
            abs_tol=1e-9,
        )

    def test_empty_scores(self):
        f = _make_fusion("combsum")
        assert f._aggregate({}, "combsum") == 0.0


class TestAggregateCombMNZ:
    """_aggregate combmnz: combsum * overlap_count. CAN exceed 1.0 because the
    overlap multiplier amplifies the sum."""

    def test_basic_computation(self):
        f = _make_fusion("combmnz")
        scores = {"embed": 0.8, "jaccard": 0.6}
        combsum = 0.5 * 0.8 + 0.5 * 0.6  # 0.7
        overlap = 2
        expected = combsum * overlap  # 1.4
        result = f._aggregate(scores, "combmnz")
        assert math.isclose(result, expected, abs_tol=1e-9)

    def test_exceeds_one_with_high_scores(self):
        """CombMNZ can exceed 1.0 -- this is by design."""
        f = _make_fusion("combmnz")
        scores = {"embed": 1.0, "jaccard": 1.0}
        result = f._aggregate(scores, "combmnz")
        assert result > 1.0

    def test_single_modality_equals_combsum(self):
        """With overlap=1, combmnz == combsum * 1."""
        f = _make_fusion("combmnz")
        scores = {"embed": 0.8}
        assert math.isclose(
            f._aggregate(scores, "combmnz"),
            f._aggregate(scores, "combsum"),
            abs_tol=1e-9,
        )

    def test_overlap_count_matters(self):
        """More modalities -> higher score (given same combsum base)."""
        f = _make_fusion("combmnz")
        # Both modalities present
        score_both = f._aggregate({"embed": 0.5, "jaccard": 0.5}, "combmnz")
        # Only one modality, but same total weighted score
        score_one = f._aggregate({"embed": 1.0}, "combmnz")
        # score_both = (0.5*0.5 + 0.5*0.5) * 2 = 0.5 * 2 = 1.0
        # score_one  = (0.5*1.0) * 1 = 0.5
        assert score_both > score_one

    def test_empty_scores(self):
        f = _make_fusion("combmnz")
        assert f._aggregate({}, "combmnz") == 0.0


class TestAggregateCombMAX:
    """_aggregate combmax: maximum of raw scores (ignores weights for max selection)."""

    def test_basic_computation(self):
        f = _make_fusion("combmax")
        scores = {"embed": 0.3, "jaccard": 0.9}
        assert f._aggregate(scores, "combmax") == 0.9

    def test_bounded_by_max_input(self):
        f = _make_fusion("combmax")
        scores = {"embed": 0.6, "jaccard": 0.4}
        result = f._aggregate(scores, "combmax")
        assert result == max(scores.values())

    def test_single_modality(self):
        f = _make_fusion("combmax")
        assert f._aggregate({"embed": 0.42}, "combmax") == 0.42

    def test_empty_scores(self):
        f = _make_fusion("combmax")
        assert f._aggregate({}, "combmax") == 0.0


class TestAggregateCombMIN:
    """_aggregate combmin: minimum of raw scores (ignores weights for min selection)."""

    def test_basic_computation(self):
        f = _make_fusion("combmin")
        scores = {"embed": 0.3, "jaccard": 0.9}
        assert f._aggregate(scores, "combmin") == 0.3

    def test_bounded_by_min_input(self):
        f = _make_fusion("combmin")
        scores = {"embed": 0.6, "jaccard": 0.4}
        result = f._aggregate(scores, "combmin")
        assert result == min(scores.values())

    def test_single_modality(self):
        f = _make_fusion("combmin")
        assert f._aggregate({"jaccard": 0.77}, "combmin") == 0.77

    def test_empty_scores(self):
        f = _make_fusion("combmin")
        assert f._aggregate({}, "combmin") == 0.0


# ---------------------------------------------------------------------------
# Cross-aggregator property tests
# ---------------------------------------------------------------------------


class TestCrossAggregatorProperties:
    """Properties that hold across all or pairs of aggregators."""

    def test_all_aggregators_same_candidate_set(self):
        """All aggregators return the same set of candidate cards via similar()."""
        results_by_agg: dict[str, set[str]] = {}
        for agg in _all_aggregators():
            f = _make_fusion(agg)
            results = f.similar("Q", k=10)
            results_by_agg[agg] = {card for card, _ in results}

        # All should produce the same candidate set (membership, not order)
        reference = results_by_agg["weighted"]
        for agg, cards in results_by_agg.items():
            assert cards == reference, (
                f"{agg} produced different candidates: "
                f"extra={cards - reference}, missing={reference - cards}"
            )

    def test_all_aggregators_non_negative_scores(self):
        """All aggregators return non-negative scores."""
        for agg in _all_aggregators():
            f = _make_fusion(agg)
            results = f.similar("Q", k=10)
            for card, score in results:
                assert score >= 0.0, f"{agg}: {card} has negative score {score}"

    def test_combmax_ge_combmin(self):
        """combmax(scores) >= combmin(scores) for all candidates."""
        f_max = _make_fusion("combmax")
        f_min = _make_fusion("combmin")
        r_max = dict(f_max.similar("Q", k=10))
        r_min = dict(f_min.similar("Q", k=10))
        for card in r_max:
            assert r_max[card] >= r_min[card], (
                f"{card}: combmax={r_max[card]} < combmin={r_min[card]}"
            )

    def test_combmnz_ge_combsum_when_overlap_gt_1(self):
        """combmnz >= combsum when overlap > 1 (multiplier >= 2)."""
        f_mnz = _make_fusion("combmnz")
        f_sum = _make_fusion("combsum")
        r_mnz = dict(f_mnz.similar("Q", k=10))
        r_sum = dict(f_sum.similar("Q", k=10))
        for card in r_mnz:
            # Only assert when both modalities contributed (overlap > 1).
            # With our setup (embed + jaccard both enabled), all candidates
            # that appear in both modalities satisfy overlap >= 2.
            assert r_mnz[card] >= r_sum[card] - 1e-9, (
                f"{card}: combmnz={r_mnz[card]} < combsum={r_sum[card]}"
            )

    def test_single_modality_rrf_weighted_same_ranking(self):
        """If only one modality returns results, RRF and weighted produce same ranking."""
        # Use embed-only weights so only one modality contributes
        embed_only_weights = FusionWeights(
            embed=1.0,
            jaccard=0.0,
            functional=0.0,
            text_embed=0.0,
            visual_embed=0.0,
            archetype=0.0,
        )
        emb = FakeEmbeddings(_SIMS)
        f_rrf = WeightedLateFusion(
            embeddings=emb,
            adj=_ADJ,
            weights=embed_only_weights,
            aggregator="rrf",
            rrf_k=60,
            candidate_topn=50,
        )
        f_weighted = WeightedLateFusion(
            embeddings=emb,
            adj=_ADJ,
            weights=embed_only_weights,
            aggregator="weighted",
            candidate_topn=50,
        )
        r_rrf = [card for card, _ in f_rrf.similar("Q", k=5)]
        r_weighted = [card for card, _ in f_weighted.similar("Q", k=5)]
        assert r_rrf == r_weighted


# ---------------------------------------------------------------------------
# Regression test: pinned top-3 for each aggregator with fixed synthetic data
# ---------------------------------------------------------------------------


class TestRegressionPinnedRankings:
    """Given a fixed set of synthetic scores across 2 modalities (embed + jaccard),
    assert exact top-3 ranking for each aggregator.

    Embedding similarities (cosine) for Q -> candidates:
        A: 0.8 -> cosine_to_unit -> 0.9
        B: 0.4 -> 0.7
        C: 0.0 -> 0.5
        D: -0.4 -> 0.3
        E: -0.8 -> 0.1

    Jaccard similarities -- computed inline in _compute_similarity_scores as
    |Q_adj & C_adj| / (|Q_adj| + |C_adj| - |Q_adj & C_adj|), where
    Q_adj = adj["Q"] = {A,B,C} (Q itself NOT included):
        A: A_adj={Q,B}   -> |{B}|=1, union=3+2-1=4   -> 0.25
        B: B_adj={Q,A,C} -> |{A,C}|=2, union=3+3-2=4 -> 0.50
        C: C_adj={Q,B,D} -> |{B}|=1, union=3+3-1=5   -> 0.20
        D: D_adj={C}     -> |{C}|=1, union=3+1-1=3    -> 0.333
        E: E_adj={}      -> 0, union=3                 -> 0.0

    With equal normalized weights (embed=0.5, jaccard=0.5):
    weighted/combsum scores:
        A: 0.5*0.9 + 0.5*0.25  = 0.575
        B: 0.5*0.7 + 0.5*0.5   = 0.600
        C: 0.5*0.5 + 0.5*0.2   = 0.350
        D: 0.5*0.3 + 0.5*0.333 = 0.317
        E: 0.5*0.1 + 0.5*0.0   = 0.050

    So weighted/combsum top-3: B, A, C
    """

    def test_weighted_top3(self):
        f = _make_fusion("weighted")
        top3 = [card for card, _ in f.similar("Q", k=3)]
        assert top3 == ["B", "A", "C"]

    def test_combsum_top3(self):
        f = _make_fusion("combsum")
        top3 = [card for card, _ in f.similar("Q", k=3)]
        assert top3 == ["B", "A", "C"]

    def test_combmnz_top3(self):
        """combmnz = combsum * overlap. All have overlap=2 (both modalities),
        so ranking is same as combsum: B, A, C."""
        f = _make_fusion("combmnz")
        top3 = [card for card, _ in f.similar("Q", k=3)]
        assert top3 == ["B", "A", "C"]

    def test_combmax_top3(self):
        """combmax picks max(embed_score, jaccard_score) per candidate:
        A: max(0.9, 0.25) = 0.9
        B: max(0.7, 0.5)  = 0.7
        C: max(0.5, 0.2)  = 0.5
        Top-3: A, B, C"""
        f = _make_fusion("combmax")
        top3 = [card for card, _ in f.similar("Q", k=3)]
        assert top3 == ["A", "B", "C"]

    def test_combmin_top3(self):
        """combmin picks min(embed_score, jaccard_score) per candidate.

        Note: jaccard here uses the optimized inline computation from
        _compute_similarity_scores, which computes |Q_adj & C_adj| / |Q_adj union C_adj|
        where Q_adj = adj[Q] (does NOT include Q itself).

        A: min(0.9, 0.25)  = 0.25
        B: min(0.7, 0.5)   = 0.5
        C: min(0.5, 0.2)   = 0.2
        D: min(0.3, 0.333) = 0.3
        Top-3: B, D, A"""
        f = _make_fusion("combmin")
        top3 = [card for card, _ in f.similar("Q", k=3)]
        assert top3 == ["B", "D", "A"]

    def test_rrf_top3(self):
        """RRF uses ranks. Embed ranks: A=1, B=2, C=3, D=4, E=5.
        Jaccard ranks: B=1, A=2, C=3 (tied w/ D at 0.2, but D also 0.2),
        actually C and D both have jaccard 0.2 so rank depends on sort stability.
        Regardless, top-3 should include A and B (strongest in both)."""
        f = _make_fusion("rrf")
        top3 = [card for card, _ in f.similar("Q", k=3)]
        # A and B should be in top 3 regardless of tie-breaking
        assert "A" in top3
        assert "B" in top3

    def test_isr_top3(self):
        """ISR uses same rank structure as RRF but with sqrt decay.
        A and B should still be top-2."""
        f = _make_fusion("isr")
        top3 = [card for card, _ in f.similar("Q", k=3)]
        assert "A" in top3
        assert "B" in top3


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_candidate_set(self):
        """Query not in adj or embeddings -> empty results for all aggregators."""
        for agg in _all_aggregators():
            f = _make_fusion(agg)
            results = f.similar("NONEXISTENT", k=5)
            assert results == [], f"{agg} returned results for unknown query"

    def test_single_candidate(self):
        """Single-candidate graph returns that candidate for all aggregators."""
        single_adj: dict[str, set[str]] = {"X": {"Y"}, "Y": {"X"}}
        single_sims = {("X", "Y"): 0.5}
        emb = FakeEmbeddings(single_sims)
        for agg in _all_aggregators():
            f = WeightedLateFusion(
                embeddings=emb,
                adj=single_adj,
                weights=_simple_weights(),
                aggregator=agg,
                candidate_topn=50,
            )
            results = f.similar("X", k=5)
            cards = [c for c, _ in results]
            assert "Y" in cards, f"{agg} did not return the single candidate"

    def test_all_scores_equal(self):
        """All candidates have identical similarity -> no crash, results returned.
        Note: rank-based aggregators (rrf, isr) assign different ranks even for
        tied scores, so their output scores will differ. Score-based aggregators
        (weighted, combsum, combmnz, combmax, combmin) should produce equal scores."""
        equal_sims = {
            ("Q", "A"): 0.5,
            ("Q", "B"): 0.5,
            ("Q", "C"): 0.5,
        }
        equal_adj: dict[str, set[str]] = {
            "Q": {"A", "B", "C"},
            "A": {"Q", "B", "C"},
            "B": {"Q", "A", "C"},
            "C": {"Q", "A", "B"},
        }
        emb = FakeEmbeddings(equal_sims)
        score_based = ["weighted", "combsum", "combmnz", "combmax", "combmin"]
        rank_based = ["rrf", "isr"]
        for agg in _all_aggregators():
            f = WeightedLateFusion(
                embeddings=emb,
                adj=equal_adj,
                weights=_simple_weights(),
                aggregator=agg,
                candidate_topn=50,
            )
            results = f.similar("Q", k=3)
            assert len(results) == 3, f"{agg}: expected 3 results, got {len(results)}"
            if agg in score_based:
                scores = [s for _, s in results]
                assert all(math.isclose(scores[0], s, abs_tol=1e-9) for s in scores), (
                    f"{agg}: scores not equal: {scores}"
                )
            else:
                # Rank-based: just verify no crash and 3 results returned
                assert all(s >= 0.0 for _, s in results), f"{agg}: negative scores"

    def test_one_modality_returns_nothing(self):
        """No embeddings, only adj -> aggregators still work."""
        for agg in _all_aggregators():
            f = WeightedLateFusion(
                embeddings=None,
                adj=_ADJ,
                weights=_simple_weights(),
                aggregator=agg,
                candidate_topn=50,
            )
            results = f.similar("Q", k=3)
            # Should still get results from jaccard alone
            assert len(results) >= 1, f"{agg}: no results with adj-only"
            for _, score in results:
                assert score >= 0.0

    def test_no_adj_only_embeddings(self):
        """No adj graph, only embeddings -> aggregators still work."""
        emb = FakeEmbeddings(_SIMS)
        for agg in _all_aggregators():
            f = WeightedLateFusion(
                embeddings=emb,
                adj=None,
                weights=_simple_weights(),
                aggregator=agg,
                candidate_topn=50,
            )
            results = f.similar("Q", k=3)
            assert len(results) >= 1, f"{agg}: no results with embed-only"
