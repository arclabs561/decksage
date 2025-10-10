#!/usr/bin/env python3
"""Test harmonization across all three game implementations."""

from ..validation.validators.models import (
    MTGDeck,
    YugiohDeck,
    PokemonDeck,
    CardDesc,
    Partition,
)


def test_all_decks_have_get_all_cards():
    """All deck types should have get_all_cards method."""
    mtg = MTGDeck(
        deck_id="test",
        format="Unknown",
        partitions=[Partition(name="Main", cards=[CardDesc(name="Test", count=1)])],
    )
    
    ygo = YugiohDeck(
        deck_id="test",
        format="Unknown",
        partitions=[Partition(name="Main Deck", cards=[CardDesc(name="Test", count=1)])],
    )
    
    pkmn = PokemonDeck(
        deck_id="test",
        format="Unknown",
        partitions=[Partition(name="Main Deck", cards=[CardDesc(name="Test", count=1)])],
    )
    
    # All should have get_all_cards
    assert hasattr(mtg, "get_all_cards")
    assert hasattr(ygo, "get_all_cards")
    assert hasattr(pkmn, "get_all_cards")
    
    assert len(mtg.get_all_cards()) == 1
    assert len(ygo.get_all_cards()) == 1
    assert len(pkmn.get_all_cards()) == 1


def test_all_decks_have_get_main_deck():
    """All deck types should have get_main_deck method."""
    mtg = MTGDeck(
        deck_id="test",
        format="Unknown",
        partitions=[Partition(name="Main", cards=[CardDesc(name="Test", count=1)])],
    )
    
    ygo = YugiohDeck(
        deck_id="test",
        format="Unknown",
        partitions=[Partition(name="Main Deck", cards=[CardDesc(name="Test", count=1)])],
    )
    
    pkmn = PokemonDeck(
        deck_id="test",
        format="Unknown",
        partitions=[Partition(name="Main Deck", cards=[CardDesc(name="Test", count=1)])],
    )
    
    assert mtg.get_main_deck() is not None
    assert ygo.get_main_deck() is not None
    assert pkmn.get_main_deck() is not None


def test_all_decks_have_same_metadata_fields():
    """All deck types should have consistent metadata fields."""
    mtg = MTGDeck(
        deck_id="test",
        format="Unknown",
        archetype="Test",
        source="mtgtop8",
        player="TestPlayer",
        event="TestEvent",
        placement=1,
        partitions=[Partition(name="Main", cards=[CardDesc(name="Test", count=1)])],
    )
    
    ygo = YugiohDeck(
        deck_id="test",
        format="Unknown",
        archetype="Test",
        source="ygoprodeck",
        player="TestPlayer",
        event="TestEvent",
        placement=1,
        partitions=[Partition(name="Main Deck", cards=[CardDesc(name="Test", count=1)])],
    )
    
    pkmn = PokemonDeck(
        deck_id="test",
        format="Unknown",
        archetype="Test",
        source="limitless",
        player="TestPlayer",
        event="TestEvent",
        placement=1,
        partitions=[Partition(name="Main Deck", cards=[CardDesc(name="Test", count=1)])],
    )
    
    # All should have these fields
    for deck in [mtg, ygo, pkmn]:
        assert hasattr(deck, "deck_id")
        assert hasattr(deck, "format")
        assert hasattr(deck, "archetype")
        assert hasattr(deck, "source")
        assert hasattr(deck, "player")
        assert hasattr(deck, "event")
        assert hasattr(deck, "placement")
        assert hasattr(deck, "partitions")


def test_model_dump_preserves_data():
    """Verify model_dump doesn't lose data."""
    mtg = MTGDeck(
        deck_id="test_123",
        format="Unknown",
        archetype="Burn",
        source="mtgtop8",
        partitions=[
            Partition(
                name="Main",
                cards=[
                    CardDesc(name="Lightning Bolt", count=4),
                    CardDesc(name="Mountain", count=20),
                ],
            )
        ],
    )
    
    dumped = mtg.model_dump()
    
    # Check all fields preserved
    assert dumped["deck_id"] == "test_123"
    assert dumped["format"] == "Unknown"
    assert dumped["archetype"] == "Burn"
    assert dumped["source"] == "mtgtop8"
    assert len(dumped["partitions"]) == 1
    assert dumped["partitions"][0]["name"] == "Main"
    assert len(dumped["partitions"][0]["cards"]) == 2


def test_split_card_normalization_consistent():
    """Split cards should normalize consistently across all games."""
    variations = [
        "Fire//Ice",
        "Fire // Ice",
        "Fire  //  Ice",
        "Fire/ /Ice",
    ]
    
    for var in variations[:3]:  # First 3 have // pattern
        card = CardDesc(name=var, count=1)
        assert card.name == "Fire // Ice", f"Failed to normalize: {var} -> {card.name}"


def test_source_inference_from_url():
    """Test source inference helper."""
    from ..validation.validators.loader import _infer_source_from_url
    
    test_cases = {
        "https://www.mtgtop8.com/deck/123": "mtgtop8",
        "https://mtggoldfish.com/deck/456": "goldfish",
        "https://deckbox.org/sets/789": "deckbox",
        "https://db.ygoprodeck.com/deck/999": "ygoprodeck",
        "https://play.limitless.gg/deck/111": "limitless",
    }
    
    for url, expected in test_cases.items():
        result = _infer_source_from_url(url)
        assert result == expected, f"Failed to infer {expected} from {url}, got {result}"


def test_inferred_source_used_in_loading():
    """Verify inferred source is actually populated in loaded decks."""
    from pathlib import Path
    from ..validation.validators.loader import load_decks_validated
    
    result = load_decks_validated(
        Path("src/backend/decks_hetero.jsonl"),
        game="auto",
        max_decks=10,
        collect_metrics=True,
    )
    
    # Check that sources were inferred
    assert result.metrics["inferred_source"]
    assert result.metrics["inferred_source"]["deckbox"] > 0
    
    # Check that decks have source populated
    for deck in result.decks:
        assert deck.source is not None, f"Deck {deck.deck_id} has null source after inference"


def test_unknown_format_skips_validation():
    """Unknown formats should skip format-specific validation."""
    # MTG with unknown format
    mtg = MTGDeck(
        deck_id="test",
        format="CustomFormat",
        partitions=[Partition(name="Main", cards=[CardDesc(name="Test", count=5)])],
    )
    # Should not raise even though only 5 cards (would fail Modern's 60-card rule)
    assert mtg.format == "CustomFormat"
    
    # YGO with unknown format
    ygo = YugiohDeck(
        deck_id="test",
        format="CustomYGO",
        partitions=[Partition(name="Main Deck", cards=[CardDesc(name="Test", count=5)])],
    )
    # Should not raise even though <40 cards
    assert ygo.format == "CustomYGO"
    
    # Pokemon with unknown format
    pkmn = PokemonDeck(
        deck_id="test",
        format="CustomPokemon",
        partitions=[Partition(name="Main Deck", cards=[CardDesc(name="Test", count=5)])],
    )
    # Should not raise even though != 60 cards
    assert pkmn.format == "CustomPokemon"
