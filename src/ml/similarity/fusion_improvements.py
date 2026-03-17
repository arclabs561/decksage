"""
Fusion System Improvements

Research-based improvements for hybrid embedding fusion:
1. Query-adaptive weighting
2. Task-specific weight optimization
3. Confidence-based weighting
"""

from __future__ import annotations

import logging
from typing import Any

from .fusion import FusionWeights


try:
    from ..utils.logging_config import get_logger

    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


def compute_component_confidence(
    query: str,
    candidate: str,
    component_scores: dict[str, float],
    component_metadata: dict[str, Any] | None = None,
) -> dict[str, float]:
    """
    Compute confidence scores for each fusion component.

    Confidence based on:
    - Score magnitude (higher = more confident)
    - Component reliability (historical performance)
    - Query characteristics (new card vs established)

    Args:
        query: Query card name
        candidate: Candidate card name
        component_scores: Scores from each component
        component_metadata: Optional metadata (vocab coverage, etc.)

    Returns:
        Dictionary mapping component -> confidence score (0-1)
    """
    confidences: dict[str, float] = {}

    # Base confidence from score magnitude (normalized)
    max_score = max(component_scores.values()) if component_scores else 1.0
    for component, score in component_scores.items():
        # Normalize to [0, 1] and apply sigmoid-like transformation
        normalized = abs(score) / max_score if max_score > 0 else 0.0
        confidences[component] = normalized

    # Adjust based on component reliability (if metadata available)
    if component_metadata:
        reliability = component_metadata.get("reliability", {})
        for component in confidences:
            if component in reliability:
                confidences[component] *= reliability[component]

    return confidences


def create_query_adaptive_weights(
    query: str,
    is_new_card: bool = False,
    has_graph_data: bool = True,
    base_weights: FusionWeights | None = None,
) -> FusionWeights:
    """
    Create adaptive fusion weights based on query characteristics.

    Research finding: New cards benefit more from instruction-tuned embeddings,
    established cards benefit more from co-occurrence.

    Args:
        query: Query card name
        is_new_card: Whether query is a new card (not in training data)
        has_graph_data: Whether graph data is available for query
        base_weights: Base weights to adapt from

    Returns:
        Adapted FusionWeights
    """
    if base_weights is None:
        base_weights = FusionWeights()

    if is_new_card:
        # New cards: Higher instruction-tuned, lower co-occurrence
        return FusionWeights(
            embed=base_weights.embed * 0.5,  # Reduce co-occurrence
            jaccard=base_weights.jaccard * 0.5,  # Reduce Jaccard
            functional=base_weights.functional,
            text_embed=base_weights.text_embed * 1.5,  # Increase instruction-tuned
        ).normalized()
    else:
        # Established cards: Standard weights
        return base_weights


def create_task_specific_weights(
    task: str,
    base_weights: FusionWeights | None = None,
) -> FusionWeights:
    """
    Create task-specific fusion weights.

    Research finding: Different tasks benefit from different component combinations.

    Args:
        task: Task type ('substitution', 'similarity', 'discovery', 'completion')
        base_weights: Base weights to adapt from

    Returns:
        Task-specific FusionWeights
    """
    if base_weights is None:
        base_weights = FusionWeights()

    if task == "substitution":
        # Substitution: DISABLE co-occurrence signals (embed, jaccard).
        # Co-occurrence embeddings anti-correlate functional substitutes:
        # cards that replace each other rarely appear in the same deck.
        # Functional AUC = 0.317 (worse than random) on co-occurrence.
        # Rely on text_embed (instruction-tuned with "substitution" prefix)
        # and functional tags instead.
        return FusionWeights(
            embed=0.0,  # Co-occurrence anti-correlates substitutes
            jaccard=0.0,  # Same problem -- shared neighbors != shared role
            functional=base_weights.functional * 2.0,  # Role-based similarity
            text_embed=base_weights.text_embed * 1.5,  # Instruction-tuned is the primary signal
            visual_embed=base_weights.visual_embed
            * 1.2,  # Visual helps identify reprints/alternates
        ).normalized()

    elif task == "completion":
        # Completion: Higher instruction-tuned for deck context, balanced co-occurrence
        return FusionWeights(
            embed=base_weights.embed * 1.0,
            jaccard=base_weights.jaccard * 1.1,  # Co-occurrence important for deck synergy
            functional=base_weights.functional * 1.2,  # Functional tags help fill gaps
            text_embed=base_weights.text_embed * 1.3,  # Instruction-tuned for deck context
            visual_embed=base_weights.visual_embed * 1.0,
        ).normalized()

    elif task == "synergy":
        # Synergy: Higher co-occurrence for multi-hop relationships
        return FusionWeights(
            embed=base_weights.embed * 0.9,
            jaccard=base_weights.jaccard * 1.3,  # Co-occurrence critical for synergies
            functional=base_weights.functional * 0.9,
            text_embed=base_weights.text_embed * 1.1,
            visual_embed=base_weights.visual_embed * 0.8,
        ).normalized()

    elif task == "similar" or task == "similarity":
        # Similarity: Higher co-occurrence
        return FusionWeights(
            embed=base_weights.embed * 1.2,  # Increase co-occurrence
            jaccard=base_weights.jaccard * 1.1,  # Increase Jaccard
            functional=base_weights.functional * 0.8,
            text_embed=base_weights.text_embed * 0.9,
            visual_embed=base_weights.visual_embed * 1.2,  # Visual important for similarity
        ).normalized()

    elif task == "discovery":
        # Discovery: Balanced
        return FusionWeights(
            embed=base_weights.embed,
            jaccard=base_weights.jaccard,
            functional=base_weights.functional,
            text_embed=base_weights.text_embed,
            visual_embed=base_weights.visual_embed
            * 1.1,  # Visual helps discover visually similar cards
        ).normalized()

    elif task == "refinement":
        # Refinement: Similar to completion but with more functional tags
        return FusionWeights(
            embed=base_weights.embed * 0.9,
            jaccard=base_weights.jaccard * 1.0,
            functional=base_weights.functional * 1.3,  # Functional tags critical for refinement
            text_embed=base_weights.text_embed * 1.2,
            visual_embed=base_weights.visual_embed * 1.0,
        ).normalized()

    elif task in ("upgrade", "downgrade"):
        # Upgrade/Downgrade: Higher functional and instruction-tuned for alternatives
        return FusionWeights(
            embed=base_weights.embed * 0.9,
            jaccard=base_weights.jaccard * 0.9,
            functional=base_weights.functional * 1.4,  # Functional equivalence important
            text_embed=base_weights.text_embed * 1.3,  # Instruction-tuned for alternatives
            visual_embed=base_weights.visual_embed
            * 1.1,  # Visual helps identify similar-looking alternatives
        ).normalized()

    elif task == "quality":
        # Quality: Balanced with emphasis on functional tags
        return FusionWeights(
            embed=base_weights.embed * 1.0,
            jaccard=base_weights.jaccard * 1.0,
            functional=base_weights.functional * 1.2,  # Functional tags indicate quality
            text_embed=base_weights.text_embed * 1.1,
            visual_embed=base_weights.visual_embed * 1.0,
        ).normalized()

    else:
        # Default: Use base weights
        return base_weights
