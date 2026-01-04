#!/usr/bin/env python3
"""
Tests for deck patch application and greedy completion.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from unittest.mock import MagicMock

try:
    from ..deck_building.deck_patch import DeckPatch, apply_deck_patch
except ImportError:
    # deck_patch module doesn't exist (commented out in deck_completion.py)
    DeckPatch = None
    apply_deck_patch = None
    pytest.skip("deck_patch module not available", allow_module_level=True)

from ..deck_building.deck_completion import (
    CompletionConfig,
    greedy_complete,
    suggest_additions,
)
from ..validation.validators import MTGDeck, Partition, CardDesc

try:
    from .fixtures.decks import DECK_ROUGHS, DECK_TRONS  # type: ignore
except Exception:
    DECK_ROUGHS, DECK_TRONS = [], []


def load_deck_from_dict(data: dict, game: str = "magic") -> MTGDeck:
    """Helper to load a deck from a dictionary for testing."""
    # This is a simplified loader for test purposes.
    # The main loader in validators/loader.py is much more complex.
    return MTGDeck.model_validate(data)


def example_partial_mtg() -> dict:
    return {
        "deck_id": "ex1",
        "format": "Modern",
        "partitions": [
            {
                "name": "Main",
                "cards": [
                    {"name": "Lightning Bolt", "count": 4},
                    {"name": "Monastery Swiftspear", "count": 4},
                    {"name": "Goblin Guide", "count": 4},
                    {"name": "Mountain", "count": 20},
                ],
            }
        ],
    }


def dummy_candidate_fn(card: str, k: int):
    # Provide a small pool of plausible burn cards
    pool = [
        ("Lava Spike", 0.99),
        ("Rift Bolt", 0.98),
        ("Searing Blaze", 0.97),
        ("Skewer the Critics", 0.96),
        ("Boros Charm", 0.95),
    ]
    return pool[:k]


def dummy_price_fn(name: str) -> float | None:
    # Make two cards expensive
    expensive = {"Boros Charm": 25.0, "Searing Blaze": 8.0}
    return expensive.get(name, 0.5)


def dummy_tag_set_fn(name: str) -> set[str]:
    # Toy tag sets
    mapping = {
        "Lava Spike": {"burn"},
        "Rift Bolt": {"suspend", "burn"},
        "Searing Blaze": {"burn", "creature_removal"},
        "Skewer the Critics": {"spectacle", "burn"},
        "Boros Charm": {"burn", "indestructible"},
        "Lightning Bolt": {"burn", "creature_removal"},
        "Monastery Swiftspear": {"prowess", "threat"},
        "Goblin Guide": {"threat"},
    }
    return mapping.get(name, set())


def test_apply_patch_add_card_valid():
    deck = example_partial_mtg()
    patch = DeckPatch(ops=[{"op": "add_card", "partition": "Main", "card": "Lava Spike", "count": 4}])
    res = apply_deck_patch("magic", deck, patch)
    # Partial deck size errors should be ignored in lenient mode; deck is returned
    assert res.is_valid
    assert res.deck is not None
    main = next(p for p in res.deck["partitions"] if p["name"] == "Main")
    names = {c["name"] for c in main["cards"]}
    assert "Lava Spike" in names


def test_apply_patch_copy_limit_enforced():
    deck = example_partial_mtg()
    # Already 4 Lightning Bolt; adding 1 should fail copy limit
    patch = DeckPatch(ops=[{"op": "add_card", "partition": "Main", "card": "Lightning Bolt", "count": 1}])
    res = apply_deck_patch("magic", deck, patch)
    assert not res.is_valid


def test_greedy_complete_progresses():
    deck = example_partial_mtg()
    cfg = CompletionConfig(game="magic", target_main_size=60, max_steps=10, budget_max=5.0, coverage_weight=0.2)
    out, steps, quality_metrics = greedy_complete("magic", deck, dummy_candidate_fn, cfg, price_fn=dummy_price_fn, tag_set_fn=dummy_tag_set_fn)
    # Expect greedy to add at least one legal card toward completion
    assert len(steps) >= 1, "Greedy completion did not add any cards"
    main = next(p for p in out["partitions"] if p["name"] == "Main")
    size = sum(c["count"] for c in main["cards"])
    assert size >= 32  # 32 initial -> should increase


def test_budget_fallback_when_no_affordable():
    deck = example_partial_mtg()
    # Set budget very low so only fallback (unpriced) or none
    cfg = CompletionConfig(game="magic", target_main_size=33, max_steps=2, budget_max=0.01)
    out, steps, quality_metrics = greedy_complete("magic", deck, dummy_candidate_fn, cfg, price_fn=lambda _: None)
    # Should still add at least one via fallback path
    assert len(steps) >= 1


def test_suggest_additions_respects_budget_and_coverage():
    deck = example_partial_mtg()
    # Without filters, Boros Charm would score high; budget filter should drop it
    pairs = suggest_additions(
        "magic",
        deck,
        dummy_candidate_fn,
        top_k=5,
        price_fn=dummy_price_fn,
        max_unit_price=5.0,
        tag_set_fn=dummy_tag_set_fn,
        coverage_weight=0.5,
    )
    top_names = [c for c, _ in pairs[:3]]
    assert "Boros Charm" not in top_names


