#!/usr/bin/env python3
"""
Pydantic models for data validation.

Provides type-safe, validated data structures matching the Go backend schema.
Enforces format-specific deck construction rules.
"""

import unicodedata
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# ============================================================================
# Universal Models (match Go backend games/game.go)
# ============================================================================


class CardDesc(BaseModel):
    """A card reference with count. Universal across all card games."""

    name: str = Field(min_length=1, max_length=200)
    count: int = Field(ge=1, le=100, description="Number of copies")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate and normalize card names."""
        # Unicode normalization (NFC = canonical composition)
        v = unicodedata.normalize("NFC", v)

        # No leading/trailing whitespace
        if v != v.strip():
            raise ValueError("Card name has leading/trailing whitespace")

        # No control characters (matches Go regex `\p{Cc}`)
        if any(unicodedata.category(c) == "Cc" for c in v):
            raise ValueError("Card name contains control characters")

        # Normalize split card notation
        # MTG split cards: "Fire // Ice", "Wear // Tear"
        # Normalize to consistent format with " // " (space slash space slash space)
        if "//" in v:
            # Split on "//" and rejoin with normalized spacing
            parts = [p.strip() for p in v.split("//")]
            v = " // ".join(parts)

        return v


class Partition(BaseModel):
    """Named group of cards (Main, Sideboard, Extra Deck, etc)."""

    name: str = Field(min_length=1)
    cards: list[CardDesc]

    @field_validator("cards")
    @classmethod
    def validate_nonempty(cls, v: list[CardDesc]) -> list[CardDesc]:
        """Partitions must have at least one card."""
        if not v:
            raise ValueError("Partition must have at least one card")
        return v

    def total_cards(self) -> int:
        """Total number of cards in partition."""
        return sum(c.count for c in self.cards)

    def unique_cards(self) -> int:
        """Number of unique card names."""
        return len(self.cards)


# ============================================================================
# Magic: The Gathering
# ============================================================================

# Basic lands that can appear any number of times
BASIC_LANDS = {
    "Plains",
    "Island",
    "Swamp",
    "Mountain",
    "Forest",
    "Wastes",
    "Snow-Covered Plains",
    "Snow-Covered Island",
    "Snow-Covered Swamp",
    "Snow-Covered Mountain",
    "Snow-Covered Forest",
}


class MTGDeck(BaseModel):
    """Magic: The Gathering deck with format-specific validation."""

    deck_id: str
    url: str | None = None
    format: str
    archetype: str | None = None
    partitions: list[Partition]
    source: str | None = None

    # Tournament metadata
    player: str | None = None
    event: str | None = None
    placement: int | None = Field(None, ge=0)
    event_date: str | None = None

    release_date: datetime | None = None

    @model_validator(mode="after")
    def validate_format_rules(self) -> "MTGDeck":
        """Enforce format-specific deck construction rules."""
        # Format rules: (min_main, max_main, max_side, max_copies, singleton)
        format_rules = {
            "Modern": (60, None, 15, 4, False),
            "Legacy": (60, None, 15, 4, False),
            "Vintage": (60, None, 15, 4, False),
            "Pauper": (60, None, 15, 4, False),
            "Pioneer": (60, None, 15, 4, False),
            "Standard": (60, None, 15, 4, False),
            "Commander": (100, 100, 0, 1, True),
            "cEDH": (100, 100, 0, 1, True),
            "Brawl": (60, 60, 0, 1, True),
            "Duel Commander": (100, 100, 0, 1, True),
            "Penny Dreadful": (60, None, 15, 4, False),
            "Premodern": (60, None, 15, 4, False),
        }

        rules = format_rules.get(self.format)
        if not rules:
            # Unknown format, skip validation (be liberal in what you accept)
            return self

        min_main, max_main, max_side, max_copies, singleton = rules

        # Find partitions
        main = next((p for p in self.partitions if p.name == "Main"), None)
        sideboard = next((p for p in self.partitions if p.name == "Sideboard"), None)

        if not main:
            raise ValueError("Deck missing Main partition")

        # Validate main deck size
        main_count = main.total_cards()
        if main_count < min_main:
            raise ValueError(
                f"{self.format} requires at least {min_main} cards in main deck, got {main_count}"
            )
        if max_main is not None and main_count > max_main:
            raise ValueError(
                f"{self.format} requires exactly {max_main} cards in main deck, got {main_count}"
            )

        # Validate sideboard size
        if sideboard:
            side_count = sideboard.total_cards()
            if side_count > max_side:
                raise ValueError(
                    f"{self.format} allows max {max_side} sideboard cards, got {side_count}"
                )
        elif max_side == 0:
            # Some formats (Commander) don't allow sideboards
            if sideboard and sideboard.total_cards() > 0:
                raise ValueError(f"{self.format} does not allow sideboard")

        # Validate copy limits (4-of rule, singleton, etc)
        self._validate_copy_limits(max_copies, singleton)

        return self

    def _validate_copy_limits(self, max_copies: int, singleton: bool) -> None:
        """Check card copy limits across all partitions."""
        # Count copies of each card across all partitions
        card_counts: dict[str, int] = {}
        for partition in self.partitions:
            for card in partition.cards:
                card_counts[card.name] = card_counts.get(card.name, 0) + card.count

        # Check limits
        for card_name, count in card_counts.items():
            # Basic lands are exempt from copy limits
            if card_name in BASIC_LANDS:
                continue

            if singleton and count > 1:
                raise ValueError(
                    f"{self.format} is singleton format, but {card_name} appears {count} times"
                )
            elif count > max_copies:
                raise ValueError(
                    f"{self.format} allows max {max_copies} copies per card, but {card_name} appears {count} times"
                )

    def get_all_cards(self) -> list[CardDesc]:
        """Get all cards across all partitions."""
        return [card for partition in self.partitions for card in partition.cards]

    def get_main_deck(self) -> Partition | None:
        """Get main deck partition."""
        return next((p for p in self.partitions if p.name == "Main"), None)

    def get_sideboard(self) -> Partition | None:
        """Get sideboard partition."""
        return next((p for p in self.partitions if p.name == "Sideboard"), None)


# ============================================================================
# Yu-Gi-Oh!
# ============================================================================


class YugiohDeck(BaseModel):
    """Yu-Gi-Oh! deck with OCG/TCG rules."""

    deck_id: str
    url: str | None = None
    format: str  # TCG, OCG, Master Duel, etc.
    archetype: str | None = None
    partitions: list[Partition]
    source: str | None = None

    player: str | None = None
    event: str | None = None
    placement: int | None = Field(None, ge=0)
    event_date: str | None = None

    release_date: datetime | None = None

    @model_validator(mode="after")
    def validate_yugioh_rules(self) -> "YugiohDeck":
        """Enforce Yu-Gi-Oh! deck construction rules."""
        # Known formats that should be validated
        known_formats = {"TCG", "OCG", "Master Duel", "Speed Duel"}

        # Skip validation for unknown/custom formats
        if self.format not in known_formats:
            # Unknown or custom format, be liberal
            return self

        # Find partitions
        main = next((p for p in self.partitions if p.name == "Main Deck"), None)
        extra = next((p for p in self.partitions if p.name == "Extra Deck"), None)
        side = next((p for p in self.partitions if p.name == "Side Deck"), None)

        if not main:
            raise ValueError("Deck missing Main Deck partition")

        # Main Deck: 40-60 cards
        main_count = main.total_cards()
        if main_count < 40 or main_count > 60:
            raise ValueError(f"Main Deck must be 40-60 cards, got {main_count}")

        # Extra Deck: 0-15 cards
        if extra:
            extra_count = extra.total_cards()
            if extra_count > 15:
                raise ValueError(f"Extra Deck max 15 cards, got {extra_count}")

        # Side Deck: 0-15 cards
        if side:
            side_count = side.total_cards()
            if side_count > 15:
                raise ValueError(f"Side Deck max 15 cards, got {side_count}")

        # Copy limits: 3 per card (no exceptions like MTG basic lands)
        # Note: Limited/Semi-Limited lists enforced by ban list checker, not here
        self._validate_copy_limits()

        return self

    def _validate_copy_limits(self) -> None:
        """Check 3-copy limit across all partitions."""
        card_counts: dict[str, int] = {}
        for partition in self.partitions:
            for card in partition.cards:
                card_counts[card.name] = card_counts.get(card.name, 0) + card.count

        for card_name, count in card_counts.items():
            if count > 3:
                raise ValueError(
                    f"Yu-Gi-Oh! allows max 3 copies per card, {card_name} appears {count} times"
                )

    def get_all_cards(self) -> list[CardDesc]:
        """Get all cards across all partitions."""
        return [card for partition in self.partitions for card in partition.cards]

    def get_main_deck(self) -> Partition | None:
        """Get main deck partition."""
        return next((p for p in self.partitions if p.name == "Main Deck"), None)

    def get_extra_deck(self) -> Partition | None:
        """Get extra deck partition."""
        return next((p for p in self.partitions if p.name == "Extra Deck"), None)

    def get_side_deck(self) -> Partition | None:
        """Get side deck partition."""
        return next((p for p in self.partitions if p.name == "Side Deck"), None)


# ============================================================================
# Pokemon
# ============================================================================


class PokemonDeck(BaseModel):
    """Pokemon TCG deck with format rules."""

    deck_id: str
    url: str | None = None
    format: str  # Standard, Expanded, Unlimited
    archetype: str | None = None
    partitions: list[Partition]
    source: str | None = None

    player: str | None = None
    event: str | None = None
    placement: int | None = Field(None, ge=0)
    event_date: str | None = None

    release_date: datetime | None = None

    @model_validator(mode="after")
    def validate_pokemon_rules(self) -> "PokemonDeck":
        """Enforce Pokemon TCG deck construction rules."""
        # Known formats that should be validated
        known_formats = {"Standard", "Expanded", "Unlimited"}

        # Skip validation for unknown/custom formats
        if self.format not in known_formats:
            # Unknown or custom format, be liberal
            return self

        # Find main deck (Pokemon doesn't have sideboard/extra deck concept)
        main = next((p for p in self.partitions if p.name == "Main Deck"), None)

        if not main:
            raise ValueError("Deck missing Main Deck partition")

        # Deck must be exactly 60 cards
        main_count = main.total_cards()
        if main_count != 60:
            raise ValueError(f"Pokemon deck must be exactly 60 cards, got {main_count}")

        # Copy limits: 4 per card (except basic Energy)
        self._validate_copy_limits()

        return self

    def _validate_copy_limits(self) -> None:
        """Check 4-copy limit (basic Energy exempt)."""
        # Basic Energy cards (can have unlimited)
        basic_energy = {
            "Grass Energy",
            "Fire Energy",
            "Water Energy",
            "Lightning Energy",
            "Psychic Energy",
            "Fighting Energy",
            "Darkness Energy",
            "Metal Energy",
            "Fairy Energy",
        }

        card_counts: dict[str, int] = {}
        for partition in self.partitions:
            for card in partition.cards:
                card_counts[card.name] = card_counts.get(card.name, 0) + card.count

        for card_name, count in card_counts.items():
            # Basic Energy exempt from 4-copy rule
            if card_name in basic_energy:
                continue

            if count > 4:
                raise ValueError(
                    f"Pokemon allows max 4 copies per card, {card_name} appears {count} times"
                )

    def get_all_cards(self) -> list[CardDesc]:
        """Get all cards across all partitions."""
        return [card for partition in self.partitions for card in partition.cards]

    def get_main_deck(self) -> Partition | None:
        """Get main deck partition."""
        return next((p for p in self.partitions if p.name == "Main Deck"), None)


# ============================================================================
# Unified Collection Type
# ============================================================================


class Collection(BaseModel):
    """Universal collection that can hold any game's deck."""

    id: str
    url: str
    type: Literal["Deck", "Set", "Cube", "YGODeck", "PokemonDeck"]
    release_date: datetime
    partitions: list[Partition]
    source: str | None = None

    # Game-specific metadata (only one will be populated)
    mtg_deck: MTGDeck | None = None
    yugioh_deck: YugiohDeck | None = None
    pokemon_deck: PokemonDeck | None = None
