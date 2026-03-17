"""
Deterministic, multi-game deck validators.

These models are intended for *data hygiene* and *cross-game consistency*:
- Validate structure (partitions/cards)
- Enforce deck construction rules (size + copy limits) for supported games
- Keep behavior explicit (fail-closed rather than silently accepting invalid decks)
"""

from __future__ import annotations

import unicodedata
from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Helpers (Unicode/name hygiene)
# ---------------------------------------------------------------------------


def _nfkc_strip(s: str) -> str:
    return unicodedata.normalize("NFKC", (s or "")).strip()


def _has_control_chars(s: str) -> bool:
    # Unicode category Cc = control chars. (Avoid hidden separators/control.)
    return any(unicodedata.category(ch) == "Cc" for ch in s)


# ---------------------------------------------------------------------------
# Core deck structure
# ---------------------------------------------------------------------------


class CardDesc(BaseModel):
    """A card entry with name + count."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, description="Card name")
    count: int = Field(..., ge=1, description="Number of copies")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        v = _nfkc_strip(v)
        if not v:
            raise ValueError("card name must be non-empty")
        if _has_control_chars(v):
            raise ValueError("card name contains control characters")
        return v


class Partition(BaseModel):
    """A deck partition (main/side/extra/etc.)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, description="Partition name")
    cards: list[CardDesc] = Field(..., min_length=1, description="Cards in partition")

    @field_validator("name")
    @classmethod
    def _validate_partition_name(cls, v: str) -> str:
        v = _nfkc_strip(v)
        if not v:
            raise ValueError("partition name must be non-empty")
        if _has_control_chars(v):
            raise ValueError("partition name contains control characters")
        return v

    def total_cards(self) -> int:
        return sum(int(c.count) for c in self.cards)


class _DeckBase(BaseModel):
    """
    Base model for deck-like objects.

    We allow extra fields because deck exports carry metadata (url/event/player/etc.)
    and we don't want validators to reject forward-compatible enrichments.
    """

    model_config = ConfigDict(extra="allow")

    deck_id: str = Field(..., min_length=1, description="Unique deck identifier")
    # lowercase canonical: magic|pokemon|yugioh
    game: Literal["magic", "pokemon", "yugioh"] | None = Field(
        None, description="Game identifier (lowercase)"
    )
    format: str | None = Field(None, description="Format name (e.g., Modern, Standard, Advanced)")
    archetype: str | None = Field(None, description="Archetype label (optional)")
    partitions: list[Partition] = Field(..., min_length=1, description="Deck partitions")

    @field_validator("deck_id")
    @classmethod
    def _validate_deck_id(cls, v: str) -> str:
        v = _nfkc_strip(v)
        if not v:
            raise ValueError("deck_id must be non-empty")
        return v

    @field_validator("format")
    @classmethod
    def _validate_format(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = _nfkc_strip(v)
        return v or None

    @field_validator("archetype")
    @classmethod
    def _validate_archetype(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = _nfkc_strip(v)
        return v or None

    def get_partition(self, *names: str) -> Partition | None:
        """Return first partition matching any name (case-insensitive)."""
        want = {n.strip().lower() for n in names if n and n.strip()}
        for p in self.partitions:
            if p.name.strip().lower() in want:
                return p
        return None

    def get_main_deck(self) -> Partition:
        """Return the main deck partition (best-effort, never None)."""
        return self.get_partition("main", "mainboard", "main deck", "deck") or self.partitions[0]

    def get_sideboard(self) -> Partition | None:
        """Return the sideboard/side deck partition, if present."""
        return self.get_partition("sideboard", "side board", "side deck", "side")

    def get_extra_deck(self) -> Partition | None:
        """Return the extra deck partition, if present (Yu-Gi-Oh!)."""
        return self.get_partition("extra deck", "extra")

    def get_all_cards(self) -> list[str]:
        """Return all cards (expanded by count) across all partitions."""
        cards: list[str] = []
        for p in self.partitions:
            for cd in p.cards:
                cards.extend([cd.name] * int(cd.count))
        return cards

    def all_card_counts(self) -> Counter[str]:
        """Aggregate counts across all partitions."""
        c: Counter[str] = Counter()
        for p in self.partitions:
            for cd in p.cards:
                c[cd.name] += int(cd.count)
        return c


# ---------------------------------------------------------------------------
# Game-specific constraints
# ---------------------------------------------------------------------------


# MTG: basics exempt from copy limits
BASIC_LANDS: set[str] = {
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


class MTGDeck(_DeckBase):
    """Magic: The Gathering deck with deterministic construction rules."""

    @model_validator(mode="after")
    def _validate_mtg(self) -> MTGDeck:
        fmt = (self.format or "").strip()
        fmt_lower = fmt.lower()

        main = self.get_partition("main", "mainboard") or self.partitions[0]
        side = self.get_partition("sideboard", "side board")

        main_n = main.total_cards()
        side_n = side.total_cards() if side else 0

        singleton_formats = {"commander", "cedh", "duel commander", "brawl"}

        if fmt_lower in {"commander", "cedh", "duel commander"}:
            if main_n != 100:
                raise ValueError(f"{fmt} requires exactly 100 cards in Main (has {main_n})")
            if side_n != 0:
                # Commander sideboards exist in some contexts, but treat as invalid for now (be explicit).
                raise ValueError(f"{fmt} expects no Sideboard (has {side_n})")
        elif fmt_lower == "brawl":
            if main_n != 60:
                raise ValueError(f"Brawl requires exactly 60 cards in Main (has {main_n})")
            if side_n != 0:
                raise ValueError(f"Brawl expects no Sideboard (has {side_n})")
        else:
            if main_n < 60:
                raise ValueError(f"Main deck requires at least 60 cards (has {main_n})")
            if side_n > 15:
                raise ValueError(f"Sideboard cannot exceed 15 cards (has {side_n})")

        # Copy limits
        counts = self.all_card_counts()
        for card, n in counts.items():
            if card in BASIC_LANDS:
                continue
            if fmt_lower in singleton_formats:
                if n > 1:
                    raise ValueError(
                        f"{fmt or 'Singleton format'} allows max 1 copy, but {card} has {n}"
                    )
            else:
                if n > 4:
                    raise ValueError(f"Modern-style formats allow max 4 copies, but {card} has {n}")

        self.game = "magic"
        return self


class PokemonDeck(_DeckBase):
    """Pokémon TCG deck rules (baseline)."""

    _BASIC_ENERGY: set[str] = {
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

    @model_validator(mode="after")
    def _validate_pokemon(self) -> PokemonDeck:
        # Pokemon decks are 60 cards total; sideboards generally not a thing.
        total = sum(p.total_cards() for p in self.partitions)
        if total != 60:
            raise ValueError(f"Pokémon decks require exactly 60 total cards (has {total})")

        counts = self.all_card_counts()
        for card, n in counts.items():
            if card in self._BASIC_ENERGY:
                continue
            if n > 4:
                raise ValueError(f"Pokémon allows max 4 copies per card, but {card} has {n}")

        self.game = "pokemon"
        return self


class YugiohDeck(_DeckBase):
    """Yu-Gi-Oh! deck rules (baseline)."""

    @model_validator(mode="after")
    def _validate_yugioh(self) -> YugiohDeck:
        main = self.get_partition("main deck", "main") or self.partitions[0]
        extra = self.get_partition("extra deck", "extra")
        side = self.get_partition("side deck", "side")

        main_n = main.total_cards()
        extra_n = extra.total_cards() if extra else 0
        side_n = side.total_cards() if side else 0

        if main_n < 40 or main_n > 60:
            raise ValueError(f"Yu-Gi-Oh! main deck must be 40-60 cards (has {main_n})")
        if extra_n > 15:
            raise ValueError(f"Yu-Gi-Oh! extra deck cannot exceed 15 cards (has {extra_n})")
        if side_n > 15:
            raise ValueError(f"Yu-Gi-Oh! side deck cannot exceed 15 cards (has {side_n})")

        counts = self.all_card_counts()
        for card, n in counts.items():
            if n > 3:
                raise ValueError(f"Yu-Gi-Oh! allows max 3 copies per card, but {card} has {n}")

        self.game = "yugioh"
        return self


class Collection(BaseModel):
    """A generic card collection (e.g., cube, binder) partitioned similarly to decks."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(..., min_length=1)
    partitions: list[Partition] = Field(..., min_length=1)


__all__ = [
    "BASIC_LANDS",
    "CardDesc",
    "Collection",
    "MTGDeck",
    "Partition",
    "PokemonDeck",
    "YugiohDeck",
]
