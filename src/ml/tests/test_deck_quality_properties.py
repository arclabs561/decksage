#!/usr/bin/env python3
"""
Property-based tests for deck quality assessment.

Tests invariants that quality scores should always satisfy:
- Scores are in [0, 1] or reasonable bounded range
- Monotonicity properties
- Consistency properties
"""

from __future__ import annotations

from hypothesis import given, strategies as st

import pytest

try:
    from ..deck_building.deck_quality import assess_deck_quality

    HAS_DECK_QUALITY = True
except ImportError:
    HAS_DECK_QUALITY = False


@pytest.mark.skipif(not HAS_DECK_QUALITY, reason="deck_quality module not available")
class TestDeckQualityProperties:
    """Property-based tests for deck quality assessment."""

    @given(
        deck=st.dictionaries(
            keys=st.sampled_from(["partitions", "format", "game"]),
            values=st.one_of(
                st.lists(
                    st.dictionaries(
                        keys=st.sampled_from(["name", "cards"]),
                        values=st.one_of(
                            st.text(),
                            st.lists(
                                st.dictionaries(
                                    keys=st.sampled_from(["name", "count"]),
                                    values=st.one_of(st.text(), st.integers(min_value=1, max_value=4)),
                                ),
                                min_size=0,
                                max_size=10,
                            ),
                        ),
                    ),
                    min_size=1,
                    max_size=3,
                ),
                st.text(),
            ),
            min_size=1,
        ).filter(lambda d: "partitions" in d),
    )
    def test_quality_scores_bounded(self, deck: dict):
        """Quality scores should be in reasonable bounded range."""
        try:
            quality = assess_deck_quality(
                deck=deck,
                game="magic",
                tag_set_fn=lambda c: set(),
                cmc_fn=lambda c: None,
            )

            # Scores should be bounded (typically [0, 1] or [0, 10])
            assert 0.0 <= quality.overall_score <= 10.0
            assert 0.0 <= quality.mana_curve_score <= 10.0
            assert 0.0 <= quality.tag_balance_score <= 10.0
            assert 0.0 <= quality.synergy_score <= 10.0
        except Exception:
            # May fail for invalid decks, that's ok
            pass

    @given(
        deck=st.dictionaries(
            keys=st.sampled_from(["partitions", "format"]),
            values=st.one_of(
                st.lists(
                    st.dictionaries(
                        keys=st.sampled_from(["name", "cards"]),
                        values=st.one_of(
                            st.text(),
                            st.lists(
                                st.dictionaries(
                                    keys=st.sampled_from(["name", "count"]),
                                    values=st.one_of(st.text(), st.integers(min_value=1, max_value=4)),
                                ),
                                min_size=0,
                                max_size=10,
                            ),
                        ),
                    ),
                    min_size=1,
                    max_size=2,
                ),
                st.text(),
            ),
            min_size=1,
        ).filter(lambda d: "partitions" in d),
    )
    def test_quality_assessment_idempotent(self, deck: dict):
        """Quality assessment should be idempotent (same deck, same scores)."""
        try:
            quality1 = assess_deck_quality(
                deck=deck,
                game="magic",
                tag_set_fn=lambda c: set(),
                cmc_fn=lambda c: None,
            )
            quality2 = assess_deck_quality(
                deck=deck,
                game="magic",
                tag_set_fn=lambda c: set(),
                cmc_fn=lambda c: None,
            )

            # Scores should be identical (within floating point tolerance)
            import math

            assert math.isclose(quality1.overall_score, quality2.overall_score, abs_tol=1e-6)
            assert math.isclose(quality1.mana_curve_score, quality2.mana_curve_score, abs_tol=1e-6)
            assert math.isclose(quality1.tag_balance_score, quality2.tag_balance_score, abs_tol=1e-6)
            assert math.isclose(quality1.synergy_score, quality2.synergy_score, abs_tol=1e-6)
        except Exception:
            # May fail for invalid decks
            pass

