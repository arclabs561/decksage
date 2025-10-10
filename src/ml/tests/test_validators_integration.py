#!/usr/bin/env python3
"""
Integration tests for validators with real data.

Tests loading from actual JSONL files in both formats:
1. export-hetero format (flat cards list)
2. Collection format (nested structure)
"""

import json
from pathlib import Path

import pytest

from ..validation.validators.loader import load_decks_lenient, load_decks_validated
from ..validation.validators.models import MTGDeck, PokemonDeck, YugiohDeck


# ============================================================================
# Test Data Paths
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA = PROJECT_ROOT / "src" / "backend" / "decks_hetero.jsonl"
FIXTURE_DATA = Path(__file__).parent / "fixtures" / "decks_export_hetero_small.jsonl"

DECKS_HETERO = DEFAULT_DATA if DEFAULT_DATA.exists() else FIXTURE_DATA
DECKS_WITH_METADATA = PROJECT_ROOT / "data" / "processed" / "decks_with_metadata.jsonl"


# ============================================================================
# Export-Hetero Format Tests
# ============================================================================


@pytest.mark.skipif(not DECKS_HETERO.exists(), reason="decks_hetero.jsonl not found")
def test_load_export_hetero_format():
    """Test loading real export-hetero JSONL format."""
    result = load_decks_validated(
        DECKS_HETERO,
        game="auto",
        check_legality=False,
        fail_on_schema_error=False,
        max_decks=100,
    )

    # Should successfully load some decks
    assert result.total_processed == 100
    assert len(result.decks) > 0, "Failed to load any decks from export-hetero format"

    # Check types
    for deck in result.decks:
        assert isinstance(deck, (MTGDeck, YugiohDeck, PokemonDeck))

    # Check that partitions were reconstructed
    for deck in result.decks:
        assert len(deck.partitions) > 0, f"Deck {deck.deck_id} has no partitions"
        main = next((p for p in deck.partitions if p.name in ["Main", "Main Deck"]), None)
        assert main is not None, f"Deck {deck.deck_id} has no main partition"

    # Print summary
    print(f"\n✓ Loaded {len(result.decks)}/{result.total_processed} decks")
    print(f"  Parse failures: {result.failed_to_parse}")
    print(f"  Schema violations: {result.schema_violations}")


@pytest.mark.skipif(not DECKS_HETERO.exists(), reason="decks_hetero.jsonl not found")
def test_export_hetero_schema_structure():
    """Verify export-hetero format structure."""
    with open(DECKS_HETERO) as f:
        for line in f:
            if line.strip():
                deck = json.loads(line)

                # Check expected fields
                assert "deck_id" in deck
                assert "cards" in deck
                assert isinstance(deck["cards"], list)

                # Check card structure
                if deck["cards"]:
                    card = deck["cards"][0]
                    assert "name" in card
                    assert "count" in card
                    assert "partition" in card

                break  # Just check first deck


@pytest.mark.skipif(not DECKS_HETERO.exists(), reason="decks_hetero.jsonl not found")
def test_empty_format_archetype_handling():
    """Test handling of empty format/archetype fields."""
    with open(DECKS_HETERO) as f:
        for line in f:
            if line.strip():
                deck = json.loads(line)
                # Many decks have empty format/archetype
                if deck.get("format") == "" or deck.get("archetype") == "":
                    # Try to load it
                    result = load_decks_validated(
                        DECKS_HETERO,
                        game="auto",
                        max_decks=1,
                        fail_on_schema_error=False,
                    )
                    # Should normalize empty strings to "Unknown" or None
                    if result.decks:
                        loaded_deck = result.decks[0]
                        assert loaded_deck.format != "", "Empty format not normalized"
                    break


@pytest.mark.skipif(not DECKS_HETERO.exists(), reason="decks_hetero.jsonl not found")
def test_game_type_detection():
    """Test auto-detection of game types."""
    result = load_decks_validated(
        DECKS_HETERO,
        game="auto",
        max_decks=50,
        fail_on_schema_error=False,
    )

    # Count game types
    game_types = {}
    for deck in result.decks:
        deck_type = type(deck).__name__
        game_types[deck_type] = game_types.get(deck_type, 0) + 1

    print(f"\nGame type detection results:")
    for game_type, count in game_types.items():
        print(f"  {game_type}: {count}")

    assert len(game_types) > 0, "No game types detected"


@pytest.mark.skipif(not DECKS_HETERO.exists(), reason="decks_hetero.jsonl not found")
def test_split_card_handling():
    """Test handling of split cards like 'Fire // Ice'."""
    # Find a split card in the data
    with open(DECKS_HETERO) as f:
        for line in f:
            if line.strip():
                deck = json.loads(line)
                for card in deck.get("cards", []):
                    if "//" in card["name"]:
                        # Found a split card
                        result = load_decks_validated(
                            DECKS_HETERO,
                            game="auto",
                            max_decks=10,
                            fail_on_schema_error=False,
                        )
                        # Should load without error
                        assert len(result.decks) > 0
                        return

    pytest.skip("No split cards found in sample")


# ============================================================================
# Collection Format Tests
# ============================================================================


@pytest.mark.skipif(
    not DECKS_WITH_METADATA.exists(), reason="decks_with_metadata.jsonl not found"
)
def test_load_collection_format():
    """Test loading Collection format (nested structure)."""
    # Check first line to see format
    with open(DECKS_WITH_METADATA) as f:
        first_line = f.readline()
        if first_line.strip():
            data = json.loads(first_line)

            # Determine format
            if "cards" in data and isinstance(data["cards"], list):
                # This is export-hetero format
                pytest.skip("File is in export-hetero format, not Collection format")
            elif "partitions" in data:
                # This is Collection format
                result = load_decks_validated(
                    DECKS_WITH_METADATA,
                    game="auto",
                    max_decks=100,
                    fail_on_schema_error=False,
                )
                assert len(result.decks) > 0
            else:
                pytest.skip("Unknown format")


# ============================================================================
# Error Handling Tests
# ============================================================================


def test_malformed_json():
    """Test handling of malformed JSON."""
    # Create temp file with bad JSON
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write('{"valid": "json"}\n')
        f.write("{invalid json\n")  # Malformed
        f.write('{"another": "valid"}\n')
        temp_path = Path(f.name)

    try:
        result = load_decks_validated(
            temp_path,
            game="magic",
            fail_on_schema_error=False,
        )

        # Should skip malformed line but load valid ones
        assert result.failed_to_parse == 1
        assert result.total_processed == 3
    finally:
        temp_path.unlink()


def test_missing_required_fields():
    """Test handling of decks missing required fields."""
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        # Missing deck_id
        f.write('{"format": "Modern", "cards": []}\n')
        # Valid
        f.write(
            '{"deck_id": "test", "format": "Modern", "cards": [{"name": "Test", "count": 1, "partition": "Main"}]}\n'
        )
        temp_path = Path(f.name)

    try:
        result = load_decks_validated(
            temp_path,
            game="magic",
            fail_on_schema_error=False,
        )

        # Should have some schema violations
        assert result.schema_violations > 0
    finally:
        temp_path.unlink()


# ============================================================================
# Performance Tests
# ============================================================================


@pytest.mark.skipif(not DECKS_HETERO.exists(), reason="decks_hetero.jsonl not found")
def test_validation_performance():
    """Measure validation throughput."""
    import time

    start = time.time()
    result = load_decks_validated(
        DECKS_HETERO,
        game="auto",
        max_decks=1000,
        check_legality=False,
        fail_on_schema_error=False,
    )
    elapsed = time.time() - start

    decks_per_sec = result.total_processed / elapsed if elapsed > 0 else 0

    print(f"\nPerformance:")
    print(f"  Processed: {result.total_processed} decks")
    print(f"  Time: {elapsed:.2f}s")
    print(f"  Throughput: {decks_per_sec:.0f} decks/sec")

    # Should be reasonably fast (>100 decks/sec without legality checks)
    assert decks_per_sec > 100, f"Too slow: {decks_per_sec:.0f} decks/sec"


# ============================================================================
# Lenient Mode Tests
# ============================================================================


@pytest.mark.skipif(not DECKS_HETERO.exists(), reason="decks_hetero.jsonl not found")
def test_lenient_mode_maximizes_data():
    """Lenient mode should load as many decks as possible."""
    decks = load_decks_lenient(
        DECKS_HETERO,
        game="auto",
        max_decks=1000,
        check_legality=False,
        verbose=False,
    )

    # Should load most decks even if some are invalid
    assert len(decks) > 900, f"Lenient mode only loaded {len(decks)}/1000 decks"


# ============================================================================
# End-to-End Test
# ============================================================================


@pytest.mark.skipif(not DECKS_HETERO.exists(), reason="decks_hetero.jsonl not found")
def test_end_to_end_pipeline():
    """Test complete pipeline from JSONL to validated decks."""
    # Load decks
    decks = load_decks_lenient(
        DECKS_HETERO,
        game="auto",
        max_decks=100,
        check_legality=False,
        verbose=True,
    )

    assert len(decks) > 0, "Failed to load any decks"

    # Check each deck is valid
    for deck in decks[:10]:  # Check first 10
        # Should have basic fields
        assert deck.deck_id
        assert deck.format
        assert len(deck.partitions) > 0

        # Should have cards
        main = deck.get_main_deck() if hasattr(deck, "get_main_deck") else deck.partitions[0]
        assert main.total_cards() > 0

        # Format-specific checks (lenient - data may have incomplete decks)
        if isinstance(deck, MTGDeck):
            # MTG decks should have some cards (we accept incomplete decks in export-hetero)
            assert main.total_cards() > 0, "MTG deck has no cards"
        elif isinstance(deck, YugiohDeck):
            # YGO main deck should have cards
            main_deck = next((p for p in deck.partitions if p.name == "Main Deck"), None)
            if main_deck:
                assert main_deck.total_cards() > 0
        elif isinstance(deck, PokemonDeck):
            # Pokemon should have cards
            assert main.total_cards() > 0

    print(f"\n✓ End-to-end test passed with {len(decks)} decks")
