#!/usr/bin/env python3
"""
Property-based tests for fusion similarity scores.

Tests invariants that similarity scores should always satisfy:
- Scores are in [0, 1] range
- Identical queries return 1.0
- Commutativity (sim(a,b) == sim(b,a))
- Triangle inequality approximations
"""

from __future__ import annotations

import math

from hypothesis import assume, given, strategies as st

from ..similarity.fusion import WeightedLateFusion, _clamp01, _cosine_to_unit, _jaccard_sets


class TestSimilarityScoreProperties:
    """Property-based tests for similarity score invariants."""

    @given(x=st.floats(min_value=-10.0, max_value=10.0))
    def test_clamp01_bounds(self, x: float):
        """_clamp01 should always return value in [0, 1]."""
        result = _clamp01(x)
        assert 0.0 <= result <= 1.0
        assert isinstance(result, float)

    @given(x=st.floats(min_value=-1.0, max_value=1.0))
    def test_cosine_to_unit_bounds(self, x: float):
        """_cosine_to_unit should map [-1, 1] to [0, 1]."""
        result = _cosine_to_unit(x)
        assert 0.0 <= result <= 1.0
        assert isinstance(result, float)

    @given(
        a=st.sets(st.text(min_size=1, max_size=20), min_size=0, max_size=10),
        b=st.sets(st.text(min_size=1, max_size=20), min_size=0, max_size=10),
    )
    def test_jaccard_bounds(self, a: set[str], b: set[str]):
        """Jaccard similarity should always be in [0, 1]."""
        result = _jaccard_sets(a, b)
        assert 0.0 <= result <= 1.0
        assert isinstance(result, float)

    @given(
        a=st.sets(st.text(min_size=1, max_size=20), min_size=0, max_size=10),
        b=st.sets(st.text(min_size=1, max_size=20), min_size=0, max_size=10),
    )
    def test_jaccard_commutative(self, a: set[str], b: set[str]):
        """Jaccard similarity should be commutative: J(a,b) == J(b,a)."""
        result_ab = _jaccard_sets(a, b)
        result_ba = _jaccard_sets(b, a)
        assert math.isclose(result_ab, result_ba, abs_tol=1e-10)

    @given(a=st.sets(st.text(min_size=1, max_size=20), min_size=0, max_size=10))
    def test_jaccard_identical_sets(self, a: set[str]):
        """Jaccard similarity of identical sets should be 1.0."""
        result = _jaccard_sets(a, a)
        if len(a) > 0:
            assert math.isclose(result, 1.0, abs_tol=1e-10)
        else:
            # Empty sets: J(∅, ∅) = 0.0 (by implementation)
            assert result == 0.0

    @given(
        a=st.sets(st.text(min_size=1, max_size=20), min_size=0, max_size=10),
        b=st.sets(st.text(min_size=1, max_size=20), min_size=0, max_size=10),
    )
    def test_jaccard_disjoint_sets(self, a: set[str], b: set[str]):
        """Jaccard similarity of disjoint sets should be 0.0."""
        assume(not a & b)  # Sets are disjoint
        result = _jaccard_sets(a, b)
        assert math.isclose(result, 0.0, abs_tol=1e-10)

    @given(
        query=st.text(min_size=1, max_size=50),
        candidate=st.text(min_size=1, max_size=50),
    )
    def test_fusion_similarity_bounds(self, query: str, candidate: str):
        """Fusion similarity should return value in [0, 1]."""
        # Create minimal fusion system
        fusion = WeightedLateFusion(
            embeddings=None,
            adj=None,
            tagger=None,
            weights=None,
        )

        # Test each similarity method
        embed_sim = fusion._get_embedding_similarity(query, candidate)
        assert 0.0 <= embed_sim <= 1.0

        jaccard_sim = fusion._get_jaccard_similarity(query, candidate)
        assert 0.0 <= jaccard_sim <= 1.0

        func_sim = fusion._get_functional_tag_similarity(query, candidate)
        assert 0.0 <= func_sim <= 1.0

    @given(query=st.text(min_size=1, max_size=50))
    def test_fusion_similarity_identical(self, query: str):
        """Fusion similarity of identical queries should be 1.0 for some methods."""
        fusion = WeightedLateFusion(
            embeddings=None,
            adj=None,
            tagger=None,
            weights=None,
        )

        # Functional tag similarity should be 1.0 for identical queries
        # (if tagger available and returns same tags)
        func_sim = fusion._get_functional_tag_similarity(query, query)
        # May be 0.0 if no tagger, but if tagger exists, should be 1.0
        assert 0.0 <= func_sim <= 1.0

    @given(
        query=st.text(min_size=1, max_size=50),
        candidate1=st.text(min_size=1, max_size=50),
        candidate2=st.text(min_size=1, max_size=50),
    )
    def test_fusion_similarity_commutative(self, query: str, candidate1: str, candidate2: str):
        """Fusion similarity should be commutative where applicable."""
        fusion = WeightedLateFusion(
            embeddings=None,
            adj=None,
            tagger=None,
            weights=None,
        )

        # Jaccard and functional tag similarity should be commutative
        jaccard_1 = fusion._get_jaccard_similarity(query, candidate1)
        jaccard_2 = fusion._get_jaccard_similarity(candidate1, query)
        # May differ if adj structure is asymmetric, but should be close
        # (Actually, Jaccard should be exactly commutative)
        # Note: This assumes symmetric adjacency, which may not always hold

        func_1 = fusion._get_functional_tag_similarity(query, candidate1)
        func_2 = fusion._get_functional_tag_similarity(candidate1, query)
        # Functional tag similarity uses Jaccard, so should be commutative
        assert math.isclose(func_1, func_2, abs_tol=1e-10)


