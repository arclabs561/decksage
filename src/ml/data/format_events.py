#!/usr/bin/env python3
"""
Format Events Database

Tracks format rotations, ban list updates, and set releases for temporal-aware
similarity computation. Based on domain-specific research on MTG, Pokémon TCG, and Yu-Gi-Oh.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


# Format events database
# Based on research: MTG rotations, Pokémon regulation marks, Yu-Gi-Oh ban lists
FORMAT_EVENTS: dict[str, dict[str, list[dict[str, Any]]]] = {
    "MTG": {
        "Standard": [
            {
                "date": "2025-07-29",
                "type": "rotation",
                "rotated_sets": [
                    "Dominaria United",
                    "The Brothers' War",
                    "Phyrexia: All Will Be One",
                    "March of the Machine",
                    "March of the Machine: The Aftermath",
                ],
                "description": "Three-year rotation, removed 5 sets",
            },
            {
                "date": "2025-06-30",
                "type": "ban",
                "banned": ["Izzet Prowess cards"],
                "description": "Pre-rotation cleanup",
            },
            {
                "date": "2025-11-10",
                "type": "ban",
                "banned": ["Proft's Eidetic Memory", "Cori-Steel Cutter", "Screaming Nemesis"],
                "description": "Post-rotation format management",
            },
        ],
        "Modern": [],  # Non-rotating, managed by bans only
        "Legacy": [],  # Non-rotating, managed by bans only
        "Pioneer": [],  # Non-rotating, managed by bans only
    },
    "PKM": {
        "Standard": [
            {
                "date": "2025-04-11",
                "type": "rotation",
                "rotated_marks": ["F"],
                "legal_marks": ["G", "H"],
                "description": "F-block rotated out, G/H remain legal",
            },
            {
                "date": "2025-10-10",
                "type": "ban",
                "banned": ["Flapple"],
                "format": "Expanded",  # Note: Standard rarely has bans
                "description": "Banned due to Forest of Vitality interaction",
            },
        ],
        "Expanded": [
            {
                "date": "2025-10-10",
                "type": "ban",
                "banned": ["Flapple"],
                "description": "Banned due to Forest of Vitality interaction",
            },
        ],
    },
    "YGO": {
        "Advanced": [
            {
                "date": "2025-10-27",
                "type": "ban",
                "limited": ["Astrograph Sorcerer", "Bystial Druiswurm", "Bystial Magnamhut"],
                "semi_limited": ["Black Dragon Collapserpent", "White Dragon Wyverburster"],
                "description": "Quarterly ban list update",
            },
            {
                "date": "2026-01-01",
                "type": "ban",
                "limited": ["Maxx C"],
                "region": "OCG",  # Japanese format, TCG may follow later
                "description": "Major metagame shift",
            },
        ],
    },
}


@dataclass
class FormatEvent:
    """A format event (rotation, ban, etc.)."""

    date: datetime
    event_type: str  # "rotation", "ban", "set_release"
    game: str
    format: str
    description: str | None = None
    rotated_sets: list[str] | None = None
    rotated_marks: list[str] | None = None
    legal_marks: list[str] | None = None
    banned: list[str] | None = None
    limited: list[str] | None = None
    semi_limited: list[str] | None = None
    region: str | None = None  # "OCG", "TCG", or None for both


def get_format_events(
    game: str,
    format: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[FormatEvent]:
    """
    Get format events for a game/format in date range.

    Args:
        game: Game name ("MTG", "PKM", "YGO")
        format: Format name ("Standard", "Modern", "Advanced", etc.)
        start_date: Start of date range (inclusive)
        end_date: End of date range (inclusive)

    Returns:
        List of format events in date range
    """
    events = []

    if game not in FORMAT_EVENTS:
        return events

    if format not in FORMAT_EVENTS[game]:
        return events

    for event_data in FORMAT_EVENTS[game][format]:
        event_date = datetime.fromisoformat(event_data["date"])

        # Filter by date range
        if start_date and event_date < start_date:
            continue
        if end_date and event_date > end_date:
            continue

        event = FormatEvent(
            date=event_date,
            event_type=event_data["type"],
            game=game,
            format=format,
            description=event_data.get("description"),
            rotated_sets=event_data.get("rotated_sets"),
            rotated_marks=event_data.get("rotated_marks"),
            legal_marks=event_data.get("legal_marks"),
            banned=event_data.get("banned"),
            limited=event_data.get("limited"),
            semi_limited=event_data.get("semi_limited"),
            region=event_data.get("region"),
        )
        events.append(event)

    return sorted(events, key=lambda e: e.date)


def is_card_legal_in_period(
    card: str,
    game: str,
    format: str,
    date: datetime,
) -> bool:
    """
    Check if a card was legal in a format at a given date.

    This is a simplified check - for full accuracy, would need card database
    with set release dates and ban list history.

    Args:
        card: Card name
        game: Game name
        format: Format name
        date: Date to check

    Returns:
        True if card was likely legal at that date
    """
    # Get ban events before this date
    ban_events = get_format_events(game, format, end_date=date)

    for event in ban_events:
        if event.event_type == "ban":
            if event.banned and card in event.banned:
                return False
            if event.limited and card in event.limited:
                # Limited is still legal, just restricted
                pass
            if event.semi_limited and card in event.semi_limited:
                # Semi-limited is still legal
                pass

    # For rotation, would need to check if card's set was legal
    # This requires card database integration
    return True


def get_format_period_key(
    game: str,
    format: str,
    date: datetime,
) -> str:
    """
    Get format period key for temporal tracking.

    Examples:
    - "Standard_2024-2025" (MTG rotation period)
    - "Standard_G" (Pokémon regulation mark)
    - "Advanced_2025-Q4" (Yu-Gi-Oh ban list period)

    Args:
        game: Game name
        format: Format name
        date: Date to get period for

    Returns:
        Format period key string
    """
    if game == "PKM" and format == "Standard":
        # Use regulation marks for Pokémon
        events = get_format_events(game, format, end_date=date)
        for event in reversed(events):  # Most recent first
            if event.event_type == "rotation" and event.legal_marks:
                # Use most recent legal mark
                return f"{format}_{event.legal_marks[-1]}"
        # Fallback to year
        return f"{format}_{date.year}"
    elif game == "YGO":
        # Use quarter for Yu-Gi-Oh (ban list updates quarterly)
        quarter = (date.month - 1) // 3 + 1
        return f"{format}_{date.year}-Q{quarter}"
    else:
        # Use year for MTG and others
        return f"{format}_{date.year}"


def get_legal_periods(
    game: str,
    format: str,
    current_date: datetime,
) -> list[tuple[datetime, datetime]]:
    """
    Get list of (start, end) tuples for format-legal periods.

    For rotating formats, returns periods where format was stable.
    For non-rotating formats, returns single period from first event to now.

    Args:
        game: Game name
        format: Format name
        current_date: Current date (end of last period)

    Returns:
        List of (start_date, end_date) tuples
    """
    events = get_format_events(game, format)

    if not events:
        # No events, assume format always legal
        return [(datetime(2000, 1, 1), current_date)]

    periods = []
    start_date = datetime(2000, 1, 1)  # Arbitrary early date

    for event in sorted(events, key=lambda e: e.date):
        if event.event_type == "rotation":
            # Rotation creates new period
            if start_date < event.date:
                periods.append((start_date, event.date))
            start_date = event.date

    # Add final period
    periods.append((start_date, current_date))

    return periods


def is_legal_in_period(
    date: datetime,
    legal_periods: list[tuple[datetime, datetime]],
) -> bool:
    """
    Check if a date falls within any legal period.

    Args:
        date: Date to check
        legal_periods: List of (start, end) tuples

    Returns:
        True if date is within a legal period
    """
    for start, end in legal_periods:
        if start <= date <= end:
            return True
    return False
