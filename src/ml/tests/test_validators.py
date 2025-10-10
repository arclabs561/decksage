#!/usr/bin/env python3
"""
Tests for data validators.

Tests Pydantic models, format-specific rules, and validation logic.
"""

import pytest
from pydantic import ValidationError

from ..validation.validators.models import (
    BASIC_LANDS,
    CardDesc,
    MTGDeck,
    Partition,
    PokemonDeck,
    YugiohDeck,
)


# ============================================================================
# CardDesc Tests
# ============================================================================


def test_card_desc_valid():
    """Valid card should pass."""
    card = CardDesc(name="Lightning Bolt", count=4)
    assert card.name == "Lightning Bolt"
    assert card.count == 4


def test_card_desc_normalizes_unicode():
    """Card names should be normalized to NFC."""
    # café with combining accent vs composed character
    card = CardDesc(name="café", count=1)
    assert card.name == "café"


def test_card_desc_rejects_whitespace():
    """Card names with leading/trailing whitespace should fail."""
    with pytest.raises(ValidationError, match="whitespace"):
        CardDesc(name=" Lightning Bolt", count=4)

    with pytest.raises(ValidationError, match="whitespace"):
        CardDesc(name="Lightning Bolt ", count=4)


def test_card_desc_rejects_control_characters():
    """Card names with control characters should fail."""
    with pytest.raises(ValidationError, match="control"):
        CardDesc(name="Lightning\x00Bolt", count=4)


@pytest.mark.parametrize("bad_count", [0, -1])
def test_card_desc_rejects_invalid_count(bad_count):
    """Card count must be >= 1."""
    with pytest.raises(ValidationError):
        CardDesc(name="Lightning Bolt", count=bad_count)


# ============================================================================
# Partition Tests
# ============================================================================


def test_partition_valid():
    """Valid partition should pass."""
    partition = Partition(
        name="Main",
        cards=[
            CardDesc(name="Lightning Bolt", count=4),
            CardDesc(name="Mountain", count=20),
        ],
    )
    assert partition.name == "Main"
    assert partition.total_cards() == 24
    assert partition.unique_cards() == 2


def test_partition_rejects_empty():
    """Partitions must have at least one card."""
    with pytest.raises(ValidationError, match="at least one"):
        Partition(name="Main", cards=[])


# ============================================================================
# MTG Deck Tests - Basic Validation
# ============================================================================


def test_mtg_deck_valid_modern():
    """Valid Modern deck should pass."""
    deck = MTGDeck(
        deck_id="test_modern_1",
        format="Modern",
        partitions=[
            Partition(
                name="Main",
                cards=[
                    CardDesc(name="Lightning Bolt", count=4),
                    CardDesc(name="Lava Spike", count=4),
                    CardDesc(name="Rift Bolt", count=4),
                    CardDesc(name="Monastery Swiftspear", count=4),
                    CardDesc(name="Mountain", count=20),
                    CardDesc(name="Goblin Guide", count=4),
                    CardDesc(name="Eidolon of the Great Revel", count=4),
                    CardDesc(name="Searing Blaze", count=4),
                    CardDesc(name="Skullcrack", count=4),
                    CardDesc(name="Boros Charm", count=4),
                    CardDesc(name="Sacred Foundry", count=4),
                ],
            ),
            Partition(
                name="Sideboard",
                cards=[
                    CardDesc(name="Path to Exile", count=4),
                    CardDesc(name="Rest in Peace", count=4),
                    CardDesc(name="Wear // Tear", count=4),
                    CardDesc(name="Deflecting Palm", count=3),
                ],
            ),
        ],
    )
    assert deck.format == "Modern"
    assert deck.get_main_deck().total_cards() == 60
    assert deck.get_sideboard().total_cards() == 15


def test_mtg_deck_too_few_cards():
    """Modern deck with <60 cards should fail."""
    with pytest.raises(ValidationError, match="at least 60"):
        MTGDeck(
            deck_id="test_small",
            format="Modern",
            partitions=[
                Partition(
                    name="Main",
                    cards=[
                        CardDesc(name="Lightning Bolt", count=4),
                        CardDesc(name="Mountain", count=20),
                    ],
                ),
            ],
        )


def test_mtg_deck_too_many_copies():
    """Modern deck with >4 copies should fail."""
    with pytest.raises(ValidationError, match="max 4 copies"):
        MTGDeck(
            deck_id="test_too_many",
            format="Modern",
            partitions=[
                Partition(
                    name="Main",
                    cards=[
                        CardDesc(name="Lightning Bolt", count=5),  # Too many!
                        CardDesc(name="Mountain", count=55),
                    ],
                ),
            ],
        )


def test_mtg_deck_basic_lands_exempt():
    """Basic lands can appear any number of times."""
    deck = MTGDeck(
        deck_id="test_basics",
        format="Modern",
        partitions=[
            Partition(
                name="Main",
                cards=[
                    CardDesc(name="Lightning Bolt", count=4),
                    CardDesc(name="Mountain", count=56),  # More than 4 is OK for basics
                ],
            ),
        ],
    )
    assert deck.get_main_deck().total_cards() == 60


def test_mtg_deck_commander_singleton():
    """Commander decks must be singleton (except basics)."""
    with pytest.raises(ValidationError, match="singleton"):
        MTGDeck(
            deck_id="test_commander",
            format="Commander",
            partitions=[
                Partition(
                    name="Main",
                    cards=[
                        CardDesc(name="Lightning Bolt", count=2),  # Violates singleton
                        CardDesc(name="Sol Ring", count=1),
                        CardDesc(name="Mountain", count=97),
                    ],
                ),
            ],
        )


def test_mtg_deck_commander_exact_100():
    """Commander decks must be exactly 100 cards."""
    with pytest.raises(ValidationError, match="at least 100"):
        MTGDeck(
            deck_id="test_commander_size",
            format="Commander",
            partitions=[
                Partition(
                    name="Main",
                    cards=[
                        CardDesc(name="Lightning Bolt", count=1),
                        CardDesc(name="Mountain", count=98),  # Only 99 total
                    ],
                ),
            ],
        )


def test_mtg_deck_commander_no_sideboard():
    """Commander doesn't allow sideboard."""
    with pytest.raises(ValidationError, match="max 0 sideboard"):
        MTGDeck(
            deck_id="test_commander_side",
            format="Commander",
            partitions=[
                Partition(
                    name="Main",
                    cards=[
                        CardDesc(name="Lightning Bolt", count=1),
                        CardDesc(name="Mountain", count=99),
                    ],
                ),
                Partition(
                    name="Sideboard",
                    cards=[CardDesc(name="Path to Exile", count=1)],
                ),
            ],
        )


def test_mtg_deck_sideboard_too_large():
    """Modern sideboard max 15 cards."""
    with pytest.raises(ValidationError, match="max 15 sideboard"):
        MTGDeck(
            deck_id="test_side_large",
            format="Modern",
            partitions=[
                Partition(
                    name="Main",
                    cards=[
                        CardDesc(name="Lightning Bolt", count=4),
                        CardDesc(name="Mountain", count=56),
                    ],
                ),
                Partition(
                    name="Sideboard",
                    cards=[
                        CardDesc(name="Path to Exile", count=4),
                        CardDesc(name="Rest in Peace", count=4),
                        CardDesc(name="Wear // Tear", count=4),
                        CardDesc(name="Deflecting Palm", count=4),  # 16 total - too many
                    ],
                ),
            ],
        )


# ============================================================================
# Yu-Gi-Oh! Tests
# ============================================================================


def test_yugioh_deck_valid():
    """Valid Yu-Gi-Oh! deck should pass."""
    deck = YugiohDeck(
        deck_id="test_ygo",
        format="TCG",
        partitions=[
            Partition(
                name="Main Deck",
                cards=[CardDesc(name="Blue-Eyes White Dragon", count=3)]
                + [CardDesc(name=f"Filler Card {i}", count=1) for i in range(37)],
            ),
            Partition(
                name="Extra Deck",
                cards=[CardDesc(name="Blue-Eyes Ultimate Dragon", count=3)],
            ),
        ],
    )
    assert deck.format == "TCG"
    assert deck.partitions[0].total_cards() == 40


def test_yugioh_deck_too_small():
    """Main deck must be 40-60 cards."""
    with pytest.raises(ValidationError, match="40-60 cards"):
        YugiohDeck(
            deck_id="test_ygo_small",
            format="TCG",
            partitions=[
                Partition(
                    name="Main Deck",
                    cards=[CardDesc(name="Blue-Eyes White Dragon", count=3)],
                ),
            ],
        )


def test_yugioh_deck_too_large():
    """Main deck must be 40-60 cards."""
    with pytest.raises(ValidationError, match="40-60 cards"):
        YugiohDeck(
            deck_id="test_ygo_large",
            format="TCG",
            partitions=[
                Partition(
                    name="Main Deck",
                    cards=[CardDesc(name=f"Card {i}", count=1) for i in range(61)],
                ),
            ],
        )


def test_yugioh_extra_deck_limit():
    """Extra deck max 15 cards."""
    with pytest.raises(ValidationError, match="Extra Deck max 15"):
        YugiohDeck(
            deck_id="test_ygo_extra",
            format="TCG",
            partitions=[
                Partition(
                    name="Main Deck",
                    cards=[CardDesc(name=f"Card {i}", count=1) for i in range(40)],
                ),
                Partition(
                    name="Extra Deck",
                    cards=[CardDesc(name=f"Extra {i}", count=1) for i in range(16)],
                ),
            ],
        )


def test_yugioh_three_copy_limit():
    """Yu-Gi-Oh! allows max 3 copies per card."""
    with pytest.raises(ValidationError, match="max 3 copies"):
        YugiohDeck(
            deck_id="test_ygo_copies",
            format="TCG",
            partitions=[
                Partition(
                    name="Main Deck",
                    cards=[CardDesc(name="Blue-Eyes White Dragon", count=4)]  # Too many
                    + [CardDesc(name=f"Card {i}", count=1) for i in range(36)],
                ),
            ],
        )


# ============================================================================
# Pokemon Tests
# ============================================================================


def test_pokemon_deck_valid():
    """Valid Pokemon deck should pass."""
    deck = PokemonDeck(
        deck_id="test_pkmn",
        format="Standard",
        partitions=[
            Partition(
                name="Main Deck",
                cards=[
                    CardDesc(name="Pikachu", count=4),
                    CardDesc(name="Raichu", count=3),
                    CardDesc(name="Lightning Energy", count=20),
                    CardDesc(name="Professor's Research", count=4),
                    CardDesc(name="Boss's Orders", count=4),
                ]
                + [CardDesc(name=f"Trainer {i}", count=1) for i in range(25)],
            ),
        ],
    )
    assert deck.format == "Standard"
    assert deck.partitions[0].total_cards() == 60


def test_pokemon_deck_wrong_size():
    """Pokemon deck must be exactly 60 cards."""
    with pytest.raises(ValidationError, match="exactly 60 cards"):
        PokemonDeck(
            deck_id="test_pkmn_size",
            format="Standard",
            partitions=[
                Partition(
                    name="Main Deck",
                    cards=[CardDesc(name="Pikachu", count=4)],
                ),
            ],
        )


def test_pokemon_four_copy_limit():
    """Pokemon allows max 4 copies (except basic energy)."""
    with pytest.raises(ValidationError, match="max 4 copies"):
        PokemonDeck(
            deck_id="test_pkmn_copies",
            format="Standard",
            partitions=[
                Partition(
                    name="Main Deck",
                    cards=[CardDesc(name="Pikachu", count=5)]  # Too many
                    + [CardDesc(name=f"Card {i}", count=1) for i in range(55)],
                ),
            ],
        )


def test_pokemon_basic_energy_exempt():
    """Basic energy can appear unlimited times."""
    deck = PokemonDeck(
        deck_id="test_pkmn_energy",
        format="Standard",
        partitions=[
            Partition(
                name="Main Deck",
                cards=[
                    CardDesc(name="Pikachu", count=4),
                    CardDesc(name="Lightning Energy", count=56),  # More than 4 is OK
                ],
            ),
        ],
    )
    assert deck.partitions[0].total_cards() == 60


# ============================================================================
# Integration Tests
# ============================================================================


def test_mtg_deck_missing_main_partition():
    """Deck without Main partition should fail."""
    with pytest.raises(ValidationError, match="missing Main"):
        MTGDeck(
            deck_id="test_no_main",
            format="Modern",
            partitions=[
                Partition(
                    name="Sideboard",
                    cards=[CardDesc(name="Path to Exile", count=4)],
                ),
            ],
        )


def test_mtg_deck_unknown_format_accepts():
    """Unknown formats should be accepted (be liberal in what you accept)."""
    deck = MTGDeck(
        deck_id="test_unknown",
        format="CustomFormat",
        partitions=[
            Partition(
                name="Main",
                cards=[
                    CardDesc(name="Lightning Bolt", count=4),
                    CardDesc(name="Mountain", count=20),
                ],
            ),
        ],
    )
    # Should not raise - we don't validate unknown formats
    assert deck.format == "CustomFormat"


def test_mtg_deck_copy_limit_across_partitions():
    """Copy limits apply across all partitions."""
    with pytest.raises(ValidationError, match="max 4 copies"):
        MTGDeck(
            deck_id="test_across_partitions",
            format="Modern",
            partitions=[
                Partition(
                    name="Main",
                    cards=[
                        CardDesc(name="Lightning Bolt", count=4),
                        CardDesc(name="Mountain", count=56),
                    ],
                ),
                Partition(
                    name="Sideboard",
                    cards=[
                        CardDesc(name="Lightning Bolt", count=1),  # 5 total across partitions
                    ],
                ),
            ],
        )
