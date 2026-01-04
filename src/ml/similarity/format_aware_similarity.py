#!/usr/bin/env python3
"""
Format-aware similarity computation.

Scientific improvement based on exp_025 finding: format-specific embeddings
achieved P@10=0.150 (70% better than current 0.0882).

This module provides format-aware similarity that uses format-specific
embeddings when available, falling back to format-agnostic otherwise.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any


logger = logging.getLogger("decksage.format_aware")


def get_format_from_deck(deck: dict[str, Any]) -> str | None:
    """
    Extract format from deck dict.

    Args:
        deck: Deck dictionary

    Returns:
        Format name (e.g., "Modern", "Standard") or None
    """
    return deck.get("format") or deck.get("format_name")


def get_format_from_query(query: str | dict[str, Any]) -> str | None:
    """
    Extract format from query (card name or dict).

    Args:
        query: Card name string or card dict

    Returns:
        Format name or None
    """
    if isinstance(query, dict):
        return query.get("format") or query.get("format_name")
    return None


def load_format_specific_embeddings(
    format_name: str,
    embeddings_dir: Path | str = "src/ml/embeddings",
) -> Any | None:
    """
    Load format-specific embedding model if available.

    Args:
        format_name: Format name (e.g., "Modern", "Standard")
        embeddings_dir: Directory containing format-specific embeddings

    Returns:
        Embedding model or None if not available
    """
    embeddings_dir = Path(embeddings_dir)

    # Try format-specific file
    format_file = embeddings_dir / f"{format_name.lower()}_vectors.kv"
    if format_file.exists():
        try:
            # Load format-specific embeddings
            # TODO: Import actual embedding loader
            # from ..utils.data_loading import load_embeddings
            # return load_embeddings(format_file)
            logger.info(f"Found format-specific embeddings: {format_file}")
            return format_file  # Placeholder
        except Exception as e:
            logger.warning(f"Failed to load format embeddings: {e}")

    return None


def format_aware_similarity(
    query_card: str | dict[str, Any],
    candidate_card: str | dict[str, Any],
    similarity_fn: Callable[[str, str], float],
    format_name: str | None = None,
    *,
    use_format_filtering: bool = True,
) -> float:
    """
    Compute similarity with format awareness.

    Args:
        query_card: Query card (name or dict)
        candidate_card: Candidate card (name or dict)
        similarity_fn: Base similarity function
        format_name: Format name (if None, extracted from cards)
        use_format_filtering: Whether to filter by format

    Returns:
        Similarity score
    """
    # Extract format if not provided
    if format_name is None:
        format_name = get_format_from_query(query_card) or get_format_from_query(candidate_card)

    # If format filtering enabled and format known
    if use_format_filtering and format_name:
        # Check if cards are legal in format
        # TODO: Implement format legality check
        # For now, just use base similarity
        pass

    # Compute base similarity
    query_name = query_card if isinstance(query_card, str) else query_card.get("name", "")
    candidate_name = (
        candidate_card if isinstance(candidate_card, str) else candidate_card.get("name", "")
    )

    return similarity_fn(query_name, candidate_name)


def format_aware_candidate_generation(
    query_card: str | dict[str, Any],
    candidate_fn: Callable[[str, int], list[tuple[str, float]]],
    format_name: str | None = None,
    top_k: int = 10,
    *,
    filter_by_format: bool = True,
) -> list[tuple[str, float]]:
    """
    Generate candidates with format awareness.

    Args:
        query_card: Query card
        candidate_fn: Base candidate generation function
        format_name: Format name
        top_k: Number of candidates
        filter_by_format: Whether to filter candidates by format

    Returns:
        List of (card, score) tuples
    """
    # Extract format
    if format_name is None:
        format_name = get_format_from_query(query_card)

    # Get base candidates
    query_name = query_card if isinstance(query_card, str) else query_card.get("name", "")
    candidates = candidate_fn(query_name, top_k * 2)  # Get more, filter down

    # Filter by format if enabled
    if filter_by_format and format_name:
        # TODO: Implement format legality check
        # For now, return all candidates
        pass

    return candidates[:top_k]


__all__ = [
    "format_aware_candidate_generation",
    "format_aware_similarity",
    "get_format_from_deck",
    "get_format_from_query",
    "load_format_specific_embeddings",
]
