#!/usr/bin/env python3
"""
Visual embedding coverage tracking and adaptive weight adjustment.

Tracks image coverage and adjusts fusion weights based on availability.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("decksage.visual_coverage")


def compute_visual_coverage(
    visual_embedder: Any | None,
    card_data: dict[str, dict[str, Any]] | None = None,
    card_names: list[str] | None = None,
) -> dict[str, Any]:
    """
    Compute visual embedding coverage statistics.

    Args:
        visual_embedder: CardVisualEmbedder instance (or None)
        card_data: Optional dict mapping card name -> card dict
        card_names: Optional list of card names to check

    Returns:
        Dict with coverage statistics:
        {
            "total_cards": int,
            "cards_with_images": int,
            "coverage_rate": float,  # 0.0 to 1.0
            "zero_embeddings": int,
            "valid_embeddings": int,
        }
    """
    if visual_embedder is None:
        return {
            "total_cards": 0,
            "cards_with_images": 0,
            "coverage_rate": 0.0,
            "zero_embeddings": 0,
            "valid_embeddings": 0,
            "embedder_available": False,
        }

    # Get cards to check
    if card_names is None:
        if card_data:
            card_names = list(card_data.keys())
        else:
            # Try to get from embedder cache
            if hasattr(visual_embedder, "_memory_cache"):
                card_names = list(visual_embedder._memory_cache.keys())
            else:
                return {
                    "total_cards": 0,
                    "cards_with_images": 0,
                    "coverage_rate": 0.0,
                    "zero_embeddings": 0,
                    "valid_embeddings": 0,
                    "embedder_available": True,
                }

    total_cards = len(card_names)
    cards_with_images = 0
    zero_embeddings = 0
    valid_embeddings = 0

    # Check each card
    for card_name in card_names[:1000]:  # Limit to 1000 for performance
        try:
            # Get card dict if available
            if card_data and card_name in card_data:
                card = card_data[card_name]
            else:
                card = card_name

            # Check if image URL exists
            if card_data and card_name in card_data:
                card_dict = card_data[card_name]
                image_url = visual_embedder._get_image_url(card_dict) if hasattr(visual_embedder, "_get_image_url") else None
                if image_url:
                    cards_with_images += 1

            # Check embedding (if cached)
            if hasattr(visual_embedder, "_memory_cache"):
                cache_key = visual_embedder._get_cache_key(card) if hasattr(visual_embedder, "_get_cache_key") else None
                if cache_key and cache_key in visual_embedder._memory_cache:
                    embedding = visual_embedder._memory_cache[cache_key]
                    import numpy as np
                    if np.allclose(embedding, 0):
                        zero_embeddings += 1
                    else:
                        valid_embeddings += 1
        except Exception as e:
            logger.debug(f"Error checking coverage for {card_name}: {e}")
            continue

    coverage_rate = cards_with_images / total_cards if total_cards > 0 else 0.0

    return {
        "total_cards": total_cards,
        "cards_with_images": cards_with_images,
        "coverage_rate": coverage_rate,
        "zero_embeddings": zero_embeddings,
        "valid_embeddings": valid_embeddings,
        "embedder_available": True,
    }


def adjust_weights_for_coverage(
    weights: Any,
    coverage_rate: float,
    min_coverage: float = 0.1,
) -> Any:
    """
    Adjust fusion weights based on visual embedding coverage.

    If coverage is low, reduce visual_embed weight and redistribute to other signals.

    Args:
        weights: FusionWeights instance
        coverage_rate: Visual embedding coverage rate (0.0 to 1.0)
        min_coverage: Minimum coverage to use full visual weight (default: 0.1)

    Returns:
        Adjusted FusionWeights instance
    """
    from ..similarity.fusion import FusionWeights

    # If coverage is below minimum, reduce visual weight
    if coverage_rate < min_coverage:
        # Scale visual weight by coverage rate
        adjusted_visual = weights.visual_embed * (coverage_rate / min_coverage)

        # Redistribute the difference to other signals proportionally
        visual_reduction = weights.visual_embed - adjusted_visual

        # Get other signal weights (excluding visual)
        other_weights = {
            "embed": weights.embed,
            "jaccard": weights.jaccard,
            "functional": weights.functional,
            "text_embed": weights.text_embed,
            "sideboard": weights.sideboard,
            "temporal": weights.temporal,
            "gnn": weights.gnn,
            "archetype": weights.archetype,
            "format": weights.format,
        }

        # Sum of other weights
        other_total = sum(w for w in other_weights.values() if w > 0)

        if other_total > 0:
            # Redistribute proportionally
            for key in other_weights:
                if other_weights[key] > 0:
                    other_weights[key] += visual_reduction * (other_weights[key] / other_total)

        return FusionWeights(
            embed=other_weights["embed"],
            jaccard=other_weights["jaccard"],
            functional=other_weights["functional"],
            text_embed=other_weights["text_embed"],
            visual_embed=adjusted_visual,
            sideboard=other_weights["sideboard"],
            temporal=other_weights["temporal"],
            gnn=other_weights["gnn"],
            archetype=other_weights["archetype"],
            format=other_weights["format"],
        ).normalized()
    else:
        # Coverage is sufficient, return original weights
        return weights.normalized()


__all__ = ["compute_visual_coverage", "adjust_weights_for_coverage"]

