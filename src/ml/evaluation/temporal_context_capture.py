#!/usr/bin/env python3
"""
Temporal Context Capture

Captures temporal context when making recommendations for first-class temporal evaluation.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .temporal_evaluation_dimensions import TemporalContext


def capture_temporal_context(
    recommendation_timestamp: datetime | None = None,
    format_name: str | None = None,
    game: str = "magic",
    format_state: dict[str, Any] | None = None,
    meta_state: dict[str, Any] | None = None,
    price_state: dict[str, float] | None = None,
    format_rotation_dates: list[datetime] | None = None,
    recent_ban_list_changes: list[dict[str, Any]] | None = None,
) -> TemporalContext:
    """
    Capture temporal context for a recommendation.

    Args:
        recommendation_timestamp: When the recommendation is being made (defaults to now)
        format_name: Format name (e.g., "modern", "standard")
        game: Game name (e.g., "magic", "yugioh", "pokemon")
        format_state: Format state at recommendation time (ban list, legal sets, etc.)
        meta_state: Meta state at recommendation time (top decks, meta share, etc.)
        price_state: Card prices at recommendation time
        format_rotation_dates: Upcoming format rotation dates
        recent_ban_list_changes: Recent ban/unban changes

    Returns:
        TemporalContext object
    """
    if recommendation_timestamp is None:
        recommendation_timestamp = datetime.now()

    # If format_state not provided, try to load from data
    if format_state is None:
        format_state = _load_format_state(format_name, game, recommendation_timestamp)

    # If meta_state not provided, try to load from data
    if meta_state is None:
        meta_state = _load_meta_state(format_name, game, recommendation_timestamp)

    # If price_state not provided, try to load from data
    if price_state is None:
        price_state = _load_price_state(game, recommendation_timestamp)

    # If format_rotation_dates not provided, try to load from data
    if format_rotation_dates is None:
        format_rotation_dates = _load_format_rotation_dates(format_name, game)

    # If recent_ban_list_changes not provided, try to load from data
    if recent_ban_list_changes is None:
        recent_ban_list_changes = _load_recent_ban_list_changes(
            format_name, game, recommendation_timestamp
        )

    return TemporalContext(
        recommendation_timestamp=recommendation_timestamp,
        format_state_at_time=format_state,
        meta_state_at_time=meta_state,
        price_state_at_time=price_state,
        format_rotation_dates=format_rotation_dates,
        recent_ban_list_changes=recent_ban_list_changes,
    )


def _load_format_state(
    format_name: str | None,
    game: str,
    timestamp: datetime,
) -> dict[str, Any]:
    """Load format state from data files."""
    # TODO: Implement actual loading from data files
    # For now, return empty dict
    return {
        "ban_list": [],
        "legal_sets": [],
        "format_name": format_name or "unknown",
        "game": game,
    }


def _load_meta_state(
    format_name: str | None,
    game: str,
    timestamp: datetime,
) -> dict[str, Any]:
    """Load meta state from data files."""
    # TODO: Implement actual loading from data files
    # For now, return empty dict
    return {
        "top_decks": [],
        "meta_share": {},
        "format_name": format_name or "unknown",
        "game": game,
    }


def _load_price_state(
    game: str,
    timestamp: datetime,
) -> dict[str, float]:
    """Load price state from data files."""
    # TODO: Implement actual loading from data files
    # For now, return empty dict
    return {}


def _load_format_rotation_dates(
    format_name: str | None,
    game: str,
) -> list[datetime] | None:
    """Load format rotation dates from data files."""
    # TODO: Implement actual loading from data files
    # For now, return None
    return None


def _load_recent_ban_list_changes(
    format_name: str | None,
    game: str,
    timestamp: datetime,
) -> list[dict[str, Any]] | None:
    """Load recent ban list changes from data files."""
    # TODO: Implement actual loading from data files
    # For now, return None
    return None


def save_temporal_context(
    context: TemporalContext,
    output_path: Path,
) -> None:
    """Save temporal context to JSON file."""
    data = {
        "recommendation_timestamp": context.recommendation_timestamp.isoformat(),
        "format_state_at_time": context.format_state_at_time,
        "meta_state_at_time": context.meta_state_at_time,
        "price_state_at_time": context.price_state_at_time,
        "format_rotation_dates": (
            [d.isoformat() for d in context.format_rotation_dates]
            if context.format_rotation_dates
            else None
        ),
        "recent_ban_list_changes": context.recent_ban_list_changes,
    }

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)


def load_temporal_context(
    input_path: Path,
) -> TemporalContext:
    """Load temporal context from JSON file."""
    with open(input_path) as f:
        data = json.load(f)

    return TemporalContext(
        recommendation_timestamp=datetime.fromisoformat(data["recommendation_timestamp"]),
        format_state_at_time=data["format_state_at_time"],
        meta_state_at_time=data["meta_state_at_time"],
        price_state_at_time=data["price_state_at_time"],
        format_rotation_dates=(
            [datetime.fromisoformat(d) for d in data["format_rotation_dates"]]
            if data.get("format_rotation_dates")
            else None
        ),
        recent_ban_list_changes=data.get("recent_ban_list_changes"),
    )


__all__ = [
    "capture_temporal_context",
    "load_temporal_context",
    "save_temporal_context",
]
