#!/usr/bin/env python3
"""Quality scores and metadata for decks containing physical copies of tagged cards."""

from hypothesis import given
from hypothesis import strategies as st

from ..deck_building.deck_quality import assess_deck_quality


TAGS = {"Forest": {"land", "mana"}, "Island": {"land"}, "Blank": set()}
COUNTS = st.dictionaries(st.sampled_from(tuple(TAGS)), st.integers(1, 4))


def score(counts):
    cards = [{"name": name, "count": count} for name, count in counts.items()]
    deck = {
        "partitions": [
            {"name": "Main", "cards": cards},
            {"name": "Sideboard", "cards": [{"name": "Forest", "count": 3}]},
        ]
    }
    return assess_deck_quality(deck, "magic", TAGS.__getitem__, lambda name: 0)


@given(COUNTS)
def test_quality_scores_bounded(counts):
    quality = score(counts)
    assert 0 <= quality.overall_score <= 10
    assert 0 <= quality.mana_curve_score <= 1
    assert 0 <= quality.tag_balance_score <= 1
    assert 0 <= quality.synergy_score <= 1
    total = sum(counts.values())
    assert quality.num_cards == total
    assert quality.num_unique_tags == len(set().union(*(TAGS[name] for name in counts)))
    expected = sum(count * len(TAGS[name]) for name, count in counts.items())
    assert quality.avg_tags_per_card == (expected / total if total else 0.0)


@given(COUNTS)
def test_quality_assessment_idempotent(counts):
    assert score(counts) == score(counts)


def test_tag_average_counts_copies_and_untagged_cards():
    assert score({"Forest": 4}).avg_tags_per_card == 2
    assert score({"Forest": 2, "Island": 1, "Blank": 1}).avg_tags_per_card == 1.25
