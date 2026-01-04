#!/usr/bin/env python3
"""
Integration helpers for adding text embeddings to fusion similarity.

This module provides utilities to integrate text embeddings into the existing
fusion system without breaking backward compatibility.
"""

from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger("decksage.fusion_integration")

try:
    from .text_embeddings import CardTextEmbedder, get_text_embedder
except ImportError:
    CardTextEmbedder = None
    logger.warning("text_embeddings not available")


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    """
    Normalize fusion weights to sum to 1.0.

    Args:
        weights: Dictionary of signal names to weights

    Returns:
        Normalized weights dictionary
    """
    total = sum(weights.values())
    if total == 0:
        return weights

    return {k: v / total for k, v in weights.items()}


def add_text_embedding_to_fusion(
    card1: dict[str, Any] | str,
    card2: dict[str, Any] | str,
    weights: dict[str, float],
    text_embedder: CardTextEmbedder | None = None,
) -> float:
    """
    Compute text embedding similarity and add to fusion weights.

    Args:
        card1: First card (dict or name)
        card2: Second card (dict or name)
        weights: Fusion weights (will be normalized)
        text_embedder: Optional embedder instance (creates if None)

    Returns:
        Text embedding similarity score [0, 1]
    """
    if CardTextEmbedder is None:
        logger.warning("Text embeddings not available, returning 0.0")
        return 0.0

    if text_embedder is None:
        text_embedder = get_text_embedder()

    try:
        similarity = text_embedder.similarity(card1, card2)
        return float(similarity)
    except Exception as e:
        logger.error(f"Error computing text embedding similarity: {e}")
        return 0.0


def compute_fusion_with_text(
    similarities: dict[str, float],
    weights: dict[str, float],
    *,
    card1: dict[str, Any] | str | None = None,
    card2: dict[str, Any] | str | None = None,
    text_embedder: CardTextEmbedder | None = None,
) -> float:
    """
    Compute fusion similarity including text embeddings.

    Args:
        similarities: Dict of existing similarities (embed, jaccard, functional)
        weights: Fusion weights (should include text_embed if desired)
        card1: First card (needed for text embedding)
        card2: Second card (needed for text embedding)
        text_embedder: Optional embedder instance

    Returns:
        Fused similarity score
    """
    # Normalize weights
    normalized = normalize_weights(weights)

    # Compute text embedding if requested and cards provided
    if "text_embed" in normalized and card1 is not None and card2 is not None:
        text_sim = add_text_embedding_to_fusion(card1, card2, normalized, text_embedder)
        similarities["text_embed"] = text_sim

    # Weighted sum
    total = 0.0
    for signal, weight in normalized.items():
        if signal in similarities:
            total += similarities[signal] * weight

    return total


def get_default_weights_with_text() -> dict[str, float]:
    """
    Get default fusion weights including text embeddings.

    Based on current weights: embed=0.1, jaccard=0.2, functional=0.7
    Adjusted to include text_embed=0.3

    Returns:
        Default weights dictionary
    """
    return {
        "embed": 0.1,
        "jaccard": 0.2,
        "functional": 0.4,  # Reduced from 0.7
        "text_embed": 0.3,  # New signal
    }


def get_legacy_weights() -> dict[str, float]:
    """
    Get legacy weights (without text embeddings) for backward compatibility.

    Returns:
        Legacy weights dictionary
    """
    return {
        "embed": 0.1,
        "jaccard": 0.2,
        "functional": 0.7,
    }


__all__ = [
    "add_text_embedding_to_fusion",
    "compute_fusion_with_text",
    "get_default_weights_with_text",
    "get_legacy_weights",
    "normalize_weights",
]
