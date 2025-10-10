#!/usr/bin/env python3
from __future__ import annotations

import pytest

from ..deck_building.completion_eval import (
    deck_price_total,
    functional_coverage_delta,
)
from ..enrichment.card_functional_tagger import FunctionalTagger
from ..validation.validators.models import MTGDeck
from dataclasses import asdict


@pytest.fixture(scope="function")
def tagger(monkeypatch):
    """Fixture to provide a FunctionalTagger with a mocked card DB."""
    from ..enrichment.card_functional_tagger import FunctionalTagger

    def mock_load_db(self):
        return {
            "Lightning Bolt": {
                "oracle_text": "Lightning Bolt deals 3 damage to any target.",
                "type_line": "Instant",
            },
            "Counterspell": {
                "oracle_text": "Counter target spell.",
                "type_line": "Instant",
            },
            "Swords to Plowshares": {
                "oracle_text": "Exile target creature. Its controller gains life equal to its power.",
                "type_line": "Instant",
            },
        }

    monkeypatch.setattr(FunctionalTagger, "_load_card_database", mock_load_db)
    return FunctionalTagger()


def _deck(cards):
    return {"deck_id": "x", "format": "Modern", "partitions": [{"name": "Main", "cards": cards}]}


def test_functional_coverage_delta_gain(tagger):
    """Test that adding a card with a new tag increases coverage."""
    deck_before = {
        "partitions": [
            {
                "name": "Main",
                "cards": [
                    {"name": "Lightning Bolt", "count": 4},
                    {"name": "Mountain", "count": 56},
                ],
            }
        ]
    }
    deck_after = {
        "partitions": [
            {
                "name": "Main",
                "cards": [
                    {"name": "Lightning Bolt", "count": 4},
                    {"name": "Counterspell", "count": 1},
                    {"name": "Mountain", "count": 55},
                ],
            }
        ]
    }

    def tag_set_fn(name: str) -> set[str]:
        tags_obj = tagger.tag_card(name)
        allowed = {
            "creature_removal",
            "artifact_removal",
            "enchantment_removal",
            "planeswalker_removal",
            "land_removal",
            "any_permanent_removal",
            "counterspell",
            "card_draw",
            "ramp",
        }
        return {t for t, v in asdict(tags_obj).items() if isinstance(v, bool) and v and t in allowed}

    delta = functional_coverage_delta(
        before=deck_before, after=deck_after, tag_set_fn=tag_set_fn, main_partition="Main"
    )
    assert delta > 0


def test_functional_coverage_delta_no_gain(tagger):
    """Test that adding a card with an existing tag has zero delta."""
    deck_before = {
        "partitions": [
            {
                "name": "Main",
                "cards": [
                    {"name": "Lightning Bolt", "count": 4},
                    {"name": "Mountain", "count": 56},
                ],
            }
        ]
    }
    deck_after = {
        "partitions": [
            {
                "name": "Main",
                "cards": [
                    {"name": "Lightning Bolt", "count": 4},
                    {"name": "Swords to Plowshares", "count": 1},
                    {"name": "Mountain", "count": 55},
                ],
            }
        ]
    }

    def tag_set_fn(name: str) -> set[str]:
        tags_obj = tagger.tag_card(name)
        allowed = {
            "creature_removal",
            "artifact_removal",
            "enchantment_removal",
            "planeswalker_removal",
            "land_removal",
            "any_permanent_removal",
            "counterspell",
            "card_draw",
            "ramp",
        }
        return {t for t, v in asdict(tags_obj).items() if isinstance(v, bool) and v and t in allowed}

    delta = functional_coverage_delta(
        before=deck_before, after=deck_after, tag_set_fn=tag_set_fn, main_partition="Main"
    )
    assert delta == 0.0


def test_deck_price_total_simple():
    """Test basic price calculation."""
    deck = {
        "partitions": [
            {
                "name": "Main",
                "cards": [
                    {"name": "Card A", "count": 4},
                    {"name": "Card B", "count": 2},
                    {"name": "Mountain", "count": 54},
                ],
            }
        ]
    }

    def price_fn(card: str) -> float | None:
        return {"Card A": 10.0, "Card B": 5.0}.get(card)

    total, missing = deck_price_total(deck, price_fn, main_partition="Main")
    assert total == (4 * 10.0 + 2 * 5.0)
    assert "Mountain" in missing


def test_deck_price_total_with_missing():
    """Test price calculation with some cards missing prices."""
    deck = {
        "partitions": [
            {
                "name": "Main",
                "cards": [
                    {"name": "Card A", "count": 4},
                    {"name": "Card C", "count": 1},
                    {"name": "Mountain", "count": 55},
                ],
            }
        ]
    }

    def price_fn(card: str) -> float | None:
        return {"Card A": 10.0}.get(card)

    total, missing = deck_price_total(deck, price_fn, main_partition="Main")
    assert total == 40.0
    assert sorted(missing) == sorted(["Card C", "Mountain"])





