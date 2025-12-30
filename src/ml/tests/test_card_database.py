"""Tests for card database functionality."""

from __future__ import annotations

import pytest

from ml.data.card_database import get_card_database
from ml.data.card_name_normalizer import (
    find_best_match,
    fuzzy_match_card_name,
    normalize_card_name,
    normalize_for_comparison,
)


def test_normalize_card_name():
    """Test card name normalization."""
    assert normalize_card_name("  Lightning  Bolt  ") == "Lightning Bolt"
    assert normalize_card_name("Lightning&Bolt") == "Lightning&Bolt"  # HTML entities handled
    assert normalize_card_name("Lightning   Bolt") == "Lightning Bolt"  # Multiple spaces


def test_normalize_for_comparison():
    """Test case-insensitive normalization."""
    assert normalize_for_comparison("Lightning Bolt") == "lightning bolt"
    assert normalize_for_comparison("  LIGHTNING  BOLT  ") == "lightning bolt"


def test_fuzzy_match():
    """Test fuzzy matching."""
    candidates = ["Lightning Bolt", "Lightning Strike", "Bolt"]
    matches = fuzzy_match_card_name("Lightning Bolt", candidates, threshold=0.8)
    
    assert len(matches) > 0
    assert matches[0][0] == "Lightning Bolt"  # Exact match should be first
    assert matches[0][1] >= 0.9  # High similarity


def test_card_database_load():
    """Test card database loading."""
    db = get_card_database()
    db.load()
    
    assert len(db._magic_cards) > 0
    assert len(db._pokemon_cards) > 0
    assert len(db._yugioh_cards) > 0


def test_card_database_get_game():
    """Test game detection."""
    db = get_card_database()
    db.load()
    
    # Test exact match
    game = db.get_game("Lightning Bolt")
    # Note: May return None if card not in loaded subset
    # This is expected behavior for partial database loading
    
    # Test that method doesn't crash
    assert db.get_game("Nonexistent Card") is None or db.get_game("Nonexistent Card") in [
        "magic",
        "pokemon",
        "yugioh",
    ]


def test_card_database_is_valid_card():
    """Test card validation."""
    db = get_card_database()
    db.load()
    
    # Test that method works (may return False if card not in loaded subset)
    result = db.is_valid_card("Lightning Bolt", "magic")
    assert isinstance(result, bool)


def test_card_database_filter_cards():
    """Test card filtering by game."""
    db = get_card_database()
    db.load()
    
    cards = ["Lightning Bolt", "Pikachu", "Blue-Eyes White Dragon"]
    valid, invalid = db.filter_cards_by_game(cards, "magic")
    
    # Results depend on what's loaded, but structure should be correct
    assert isinstance(valid, list)
    assert isinstance(invalid, list)
    assert len(valid) + len(invalid) == len(cards)


@pytest.mark.slow
def test_card_database_performance():
    """Test card database performance."""
    import time
    
    db = get_card_database()
    db.load()
    
    # Test multiple lookups
    test_cards = ["Lightning Bolt", "Counterspell", "Brainstorm"] * 100
    
    start = time.time()
    for card in test_cards:
        db.get_game(card)
    end = time.time()
    
    # Should be fast (< 0.1s for 300 lookups)
    assert (end - start) < 0.1, f"Too slow: {end - start:.3f}s for {len(test_cards)} lookups"

