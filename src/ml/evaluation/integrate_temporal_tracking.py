#!/usr/bin/env python3
"""
Integrate Temporal Tracking into Recommendations

Adds timestamps and temporal context to all recommendations.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def add_temporal_context_to_recommendation(
    recommendation: dict[str, Any],
    format_state: dict[str, Any] | None = None,
    meta_state: dict[str, Any] | None = None,
    price_state: dict[str, float] | None = None,
) -> dict[str, Any]:
    """
    Add temporal context to a recommendation.

    Args:
        recommendation: Recommendation dict
        format_state: Format state (ban list, legal sets, etc.)
        meta_state: Meta state (top decks, meta share, etc.)
        price_state: Price state (card prices)

    Returns:
        Recommendation with temporal context added
    """
    # Add timestamp if not present
    if "timestamp" not in recommendation:
        recommendation["timestamp"] = datetime.now().isoformat()

    # Add temporal context
    recommendation["temporal_context"] = {
        "format_state": format_state or {},
        "meta_state": meta_state or {},
        "price_state": price_state or {},
        "timestamp": recommendation["timestamp"],
    }

    return recommendation


def extract_temporal_context_from_recommendation(
    recommendation: dict[str, Any],
) -> dict[str, Any] | None:
    """Extract temporal context from recommendation."""
    return recommendation.get("temporal_context")


__all__ = [
    "add_temporal_context_to_recommendation",
    "extract_temporal_context_from_recommendation",
]
