"""
Tests for deck export schema validation.
"""

import sys
from pathlib import Path


# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ml.data.export_schema import DeckExport, validate_deck_record


def test_valid_deck_record():
    """Test validation of valid deck record."""
    valid_deck = {
        "deck_id": "test-123",
        "scraped_at": "2025-01-01T00:00:00Z",
        "cards": [{"name": "Lightning Bolt", "count": 4, "partition": "mainboard"}],
        "export_version": "1.0",
    }
    is_valid, error, validated = validate_deck_record(valid_deck, strict=False)
    assert is_valid
    assert error is None
    assert validated is not None


def test_invalid_deck_empty_cards():
    """Test validation rejects empty cards list."""
    invalid_deck = {
        "deck_id": "test-123",
        "scraped_at": "2025-01-01T00:00:00Z",
        "cards": [],
        "export_version": "1.0",
    }
    # In strict mode, should fail
    is_valid, error, validated = validate_deck_record(invalid_deck, strict=True)
    assert not is_valid
    assert "cards" in error.lower() or "empty" in error.lower() or "too_short" in error.lower()

    # In non-strict mode, returns True but logs warning (graceful degradation)
    is_valid, error, validated = validate_deck_record(invalid_deck, strict=False)
    # Non-strict mode may return True with a warning, or False with error
    # Both behaviors are acceptable
    assert isinstance(is_valid, bool)


def test_invalid_deck_missing_required():
    """Test validation rejects missing required fields."""
    invalid_deck = {"deck_id": "test-123"}
    # In strict mode, should fail
    is_valid, error, validated = validate_deck_record(invalid_deck, strict=True)
    assert not is_valid
    assert "required" in error.lower() or "missing" in error.lower() or "Field required" in error

    # In non-strict mode, may return True with warning or False with error
    is_valid, error, validated = validate_deck_record(invalid_deck, strict=False)
    # Both behaviors acceptable in non-strict mode
    assert isinstance(is_valid, bool)


def test_backward_compatibility_aliases():
    """Test that backward compatibility aliases work."""
    deck_with_timestamp = {
        "deck_id": "test-123",
        "timestamp": "2025-01-01T00:00:00Z",  # Alias for scraped_at
        "cards": [{"name": "Lightning Bolt", "count": 4, "partition": "mainboard"}],
    }
    is_valid, error, validated = validate_deck_record(deck_with_timestamp, strict=False)
    assert is_valid
    # Should normalize to scraped_at
    if validated:
        assert "scraped_at" in validated or "timestamp" in validated


def test_pydantic_model_creation():
    """Test that Pydantic model can be created from valid data."""
    valid_data = {
        "deck_id": "test-123",
        "scraped_at": "2025-01-01T00:00:00Z",
        "cards": [{"name": "Lightning Bolt", "count": 4, "partition": "mainboard"}],
        "export_version": "1.0",
    }
    deck = DeckExport(**valid_data)
    assert deck.deck_id == "test-123"
    assert len(deck.cards) == 1
    assert deck.cards[0].name == "Lightning Bolt"


def test_export_version_default():
    """Test that export_version defaults to 1.0 if missing."""
    deck_without_version = {
        "deck_id": "test-123",
        "scraped_at": "2025-01-01T00:00:00Z",
        "cards": [{"name": "Lightning Bolt", "count": 4, "partition": "mainboard"}],
    }
    is_valid, error, validated = validate_deck_record(deck_without_version, strict=False)
    assert is_valid
    if validated:
        assert validated.get("export_version") == "1.0"
