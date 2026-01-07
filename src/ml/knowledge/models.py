"""Pydantic models for game knowledge structure."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class GameMechanics(BaseModel):
    """Game-specific mechanics and rules."""

    mana_system: str | None = Field(None, description="How resources work (mana, energy, etc.)")
    color_system: str | None = Field(None, description="Color/attribute system")
    card_types: list[str] = Field(default_factory=list, description="Card type categories")
    keywords: list[str] = Field(default_factory=list, description="Important keywords/abilities")
    special_rules: str | None = Field(None, description="Game-specific rules")
    terminology: dict[str, str] = Field(default_factory=dict, description="Term definitions")


class ArchetypeDefinition(BaseModel):
    """Definition of a deck archetype."""

    name: str = Field(description="Archetype name")
    description: str = Field(description="What this archetype is")
    strategy: str = Field(description="How it wins")
    core_cards: list[str] = Field(default_factory=list, description="Essential cards (70%+ inclusion)")
    flex_slots: list[str] = Field(default_factory=list, description="Common but not essential")
    key_features: list[str] = Field(default_factory=list, description="Characteristics")
    typical_curve: str | None = Field(None, description="Mana/energy curve description")
    interaction_level: str | None = Field(None, description="Interaction level (heavy/medium/light)")
    meta_position: str | None = Field(None, description="Current meta position")


class FormatDefinition(BaseModel):
    """Format rules and context."""

    name: str = Field(description="Format name")
    legal_sets: list[str] | None = Field(None, description="Legal set codes")
    rotation_schedule: str | None = Field(None, description="Rotation information")
    ban_list: list[str] = Field(default_factory=list, description="Banned cards")
    restricted_list: list[str] = Field(default_factory=list, description="Restricted cards")
    meta_context: str | None = Field(None, description="Current meta description")
    last_updated: str | None = Field(None, description="Last update date (ISO format)")


class KnowledgeChunk(BaseModel):
    """A chunk of knowledge for retrieval."""

    id: str = Field(description="Unique chunk ID")
    game: str = Field(description="Game name")
    category: str = Field(description="Category: mechanics, archetype, format, example")
    content: str = Field(description="Knowledge content")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    tags: list[str] = Field(default_factory=list, description="Tags for filtering")


class GameKnowledge(BaseModel):
    """Complete game knowledge structure."""

    game: str = Field(description="Game name (magic, pokemon, yugioh)")
    mechanics: GameMechanics = Field(description="Game mechanics")
    archetypes: list[ArchetypeDefinition] = Field(default_factory=list, description="Archetype definitions")
    formats: list[FormatDefinition] = Field(default_factory=list, description="Format definitions")
    examples: list[dict[str, Any]] = Field(default_factory=list, description="Few-shot examples")
    temporal_context: dict[str, Any] = Field(default_factory=dict, description="Temporal context (meta, bans, etc.)")
    last_updated: str = Field(default_factory=lambda: datetime.now().isoformat(), description="Last update timestamp")

