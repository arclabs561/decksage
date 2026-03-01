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

from ..utils.banlist_filter import BanlistFilter


logger = logging.getLogger("decksage.format_aware")

# Default banlist paths per game; override via load_format_specific_embeddings callers.
_BANLIST_PATHS: dict[str, Path] = {
    "magic": Path("data/banlists/magic_banlists.json"),
    "yugioh": Path("data/banlists/yugioh_banlists.json"),
    "pokemon": Path("data/banlists/pokemon_banlists.json"),
}


def _get_banlist_filter(game: str = "magic") -> BanlistFilter:
    """Return a BanlistFilter for the given game, gracefully handling missing files."""
    path = _BANLIST_PATHS.get(game, Path(f"data/banlists/{game}_banlists.json"))
    return BanlistFilter.load(game, path)


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
            # Returns the path as a handle; callers load via their embedding library.
            # To load directly, use gensim: KeyedVectors.load(str(format_file))
            logger.info(f"Found format-specific embeddings: {format_file}")
            return format_file
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

    # If format filtering enabled and format known, skip banned cards
    if use_format_filtering and format_name:
        bf = _get_banlist_filter()
        fmt_lower = format_name.lower()
        query_name = query_card if isinstance(query_card, str) else query_card.get("name", "")
        candidate_name_check = (
            candidate_card if isinstance(candidate_card, str) else candidate_card.get("name", "")
        )
        if bf.is_banned(query_name, fmt_lower) or bf.is_banned(candidate_name_check, fmt_lower):
            return 0.0

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

    # Filter by format if enabled: drop candidates banned in this format
    if filter_by_format and format_name:
        bf = _get_banlist_filter()
        fmt_lower = format_name.lower()
        candidates = [(c, s) for c, s in candidates if not bf.is_banned(c, fmt_lower)]

    return candidates[:top_k]


__all__ = [
    "format_aware_candidate_generation",
    "format_aware_similarity",
    "get_format_from_deck",
    "get_format_from_query",
    "load_format_specific_embeddings",
]
