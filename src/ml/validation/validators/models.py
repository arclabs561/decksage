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

from ...deck_building.constants import MAGIC_BASIC_LANDS as BASIC_LANDS
from ..deck_rules import construction_errors, construction_partition_key


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

    def _check_construction(self, game: Literal["magic", "pokemon", "yugioh"]) -> None:
        errors = construction_errors(
            game,
            self.format,
            ((p.name, ((c.name, c.count) for c in p.cards)) for p in self.partitions),
        )
        if errors:
            raise ValueError(errors[0])
        self.game = game

    def get_partition(self, *names: str) -> Partition | None:
        """Return first partition matching any name (case-insensitive)."""
        want = {n.strip().lower() for n in names if n and n.strip()}
        for p in self.partitions:
            if p.name.strip().lower() in want:
                return p
        return None

    def get_main_deck(self) -> Partition:
        """Return the main deck partition (best-effort, never None)."""
        return next(
            (p for p in self.partitions if construction_partition_key(p.name, self.game) == "main"),
            self.partitions[0],
        )

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


class MTGDeck(_DeckBase):
    """Magic: The Gathering deck with deterministic construction rules."""

    @model_validator(mode="after")
    def _validate_mtg(self) -> MTGDeck:
        self._check_construction("magic")
        return self


class PokemonDeck(_DeckBase):
    """Pokémon TCG deck rules (baseline)."""

    @model_validator(mode="after")
    def _validate_pokemon(self) -> PokemonDeck:
        self._check_construction("pokemon")
        return self


class YugiohDeck(_DeckBase):
    """Yu-Gi-Oh! deck rules (baseline)."""

    @model_validator(mode="after")
    def _validate_yugioh(self) -> YugiohDeck:
        self._check_construction("yugioh")
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
