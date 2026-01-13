#!/usr/bin/env python3
"""
Comprehensive feature extraction for Learning-to-Rank.

Extracts features from multiple similarity signals including:
- Direct similarity scores
- Rank positions
- Aggregation features (max, min, mean, variance)
- Query-dependent features (card type, CMC)
- Cross-modal agreement features
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np


logger = logging.getLogger(__name__)


def extract_ltr_features_optimized(
    query: str,
    candidate: str,
    fusion: Any,  # WeightedLateFusion instance
    card_data: dict[str, dict[str, Any]] | None = None,
    cached_scores: dict[str, float] | None = None,
    limit_candidates: set[str] | None = None,
) -> dict[str, float]:
    """
    Optimized version of extract_ltr_features that uses cached similarity scores.

    Args:
        query: Query card name
        candidate: Candidate card name
        fusion: WeightedLateFusion instance
        card_data: Card metadata dictionary
        cached_scores: Pre-computed similarity scores (optional)
        limit_candidates: Limited candidate set for rank computation (optional)

    Returns:
        Dictionary of features
    """
    # Use cached scores if available, otherwise compute
    if cached_scores:
        candidate_scores = cached_scores
    else:
        scores = fusion._compute_similarity_scores(query, {candidate})
        candidate_scores = scores.get(candidate, {})

    # Get rank positions (use limited candidate set for speed)
    ranks = _get_rank_positions(query, candidate, fusion, limit_candidates=limit_candidates)

    # Get metadata
    query_meta = _get_card_metadata(query, card_data) if card_data else {}
    candidate_meta = _get_card_metadata(candidate, card_data) if card_data else {}

    # Build features (same as extract_ltr_features but using cached scores)
    features = {}

    # Similarity scores
    for mod in [
        "embed",
        "jaccard",
        "functional",
        "text_embed",
        "visual_embed",
        "gnn",
        "sideboard",
        "temporal",
        "archetype",
        "format",
    ]:
        features[f"{mod}_score"] = float(candidate_scores.get(mod, 0.0))
        features[f"{mod}_rank"] = float(ranks.get(mod, 999))

    # Aggregation statistics
    score_values = [v for v in candidate_scores.values() if isinstance(v, (int, float))]
    if score_values:
        features["num_modalities"] = float(len(score_values))
        features["max_score"] = float(max(score_values))
        features["min_score"] = float(min(score_values))
        features["mean_score"] = float(sum(score_values) / len(score_values))
        if len(score_values) > 1:
            import numpy as np

            features["score_variance"] = float(np.var(score_values))
            features["score_std"] = float(np.std(score_values))
        else:
            features["score_variance"] = 0.0
            features["score_std"] = 0.0
        features["score_range"] = features["max_score"] - features["min_score"]
    else:
        features["num_modalities"] = 0.0
        features["max_score"] = 0.0
        features["min_score"] = 0.0
        features["mean_score"] = 0.0
        features["score_variance"] = 0.0
        features["score_std"] = 0.0
        features["score_range"] = 0.0

    # Cross-modal agreement
    embed_score = candidate_scores.get("embed", 0.0)
    text_score = candidate_scores.get("text_embed", 0.0)
    visual_score = candidate_scores.get("visual_embed", 0.0)
    gnn_score = candidate_scores.get("gnn", 0.0)
    jaccard_score = candidate_scores.get("jaccard", 0.0)

    features["text_visual_agreement"] = (
        1.0
        if (text_score > 0.5 and visual_score > 0.5) or (text_score < 0.3 and visual_score < 0.3)
        else 0.0
    )
    features["embed_gnn_agreement"] = (
        1.0
        if (embed_score > 0.5 and gnn_score > 0.5) or (embed_score < 0.3 and gnn_score < 0.3)
        else 0.0
    )
    features["text_jaccard_agreement"] = (
        1.0
        if (text_score > 0.5 and jaccard_score > 0.5) or (text_score < 0.3 and jaccard_score < 0.3)
        else 0.0
    )
    features["visual_gnn_agreement"] = (
        1.0
        if (visual_score > 0.5 and gnn_score > 0.5) or (visual_score < 0.3 and gnn_score < 0.3)
        else 0.0
    )

    all_high = all(
        s > 0.5 for s in [embed_score, text_score, visual_score, gnn_score, jaccard_score] if s > 0
    )
    all_low = all(
        s < 0.3 for s in [embed_score, text_score, visual_score, gnn_score, jaccard_score] if s > 0
    )
    features["all_signals_agree"] = (
        1.0
        if (all_high or all_low)
        and len(
            [s for s in [embed_score, text_score, visual_score, gnn_score, jaccard_score] if s > 0]
        )
        >= 3
        else 0.0
    )

    # Query metadata
    if query_meta:
        features["query_cmc"] = float(query_meta.get("cmc", 0))
        query_types = query_meta.get("types", [])
        features["query_is_creature"] = 1.0 if "Creature" in query_types else 0.0
        features["query_is_instant"] = 1.0 if "Instant" in query_types else 0.0
        features["query_is_sorcery"] = 1.0 if "Sorcery" in query_types else 0.0
        features["query_is_artifact"] = 1.0 if "Artifact" in query_types else 0.0
        features["query_is_enchantment"] = 1.0 if "Enchantment" in query_types else 0.0
    else:
        features["query_cmc"] = 0.0
        features["query_is_creature"] = 0.0
        features["query_is_instant"] = 0.0
        features["query_is_sorcery"] = 0.0
        features["query_is_artifact"] = 0.0
        features["query_is_enchantment"] = 0.0

    # Candidate metadata
    if candidate_meta:
        features["candidate_cmc"] = float(candidate_meta.get("cmc", 0))
        candidate_types = candidate_meta.get("types", [])
        features["candidate_is_creature"] = 1.0 if "Creature" in candidate_types else 0.0
        features["candidate_is_instant"] = 1.0 if "Instant" in candidate_types else 0.0
        features["candidate_is_sorcery"] = 1.0 if "Sorcery" in candidate_types else 0.0
        features["candidate_is_artifact"] = 1.0 if "Artifact" in candidate_types else 0.0
        features["candidate_is_enchantment"] = 1.0 if "Enchantment" in candidate_types else 0.0
    else:
        features["candidate_cmc"] = 0.0
        features["candidate_is_creature"] = 0.0
        features["candidate_is_instant"] = 0.0
        features["candidate_is_sorcery"] = 0.0
        features["candidate_is_artifact"] = 0.0
        features["candidate_is_enchantment"] = 0.0

    # Query-candidate interaction
    if query_meta and candidate_meta:
        query_cmc = query_meta.get("cmc", 0)
        candidate_cmc = candidate_meta.get("cmc", 0)
        query_types = set(query_meta.get("types", []))
        candidate_types = set(candidate_meta.get("types", []))
        query_colors = set(query_meta.get("colors", []))
        candidate_colors = set(candidate_meta.get("colors", []))

        features["cmc_diff"] = abs(query_cmc - candidate_cmc)
        features["cmc_same"] = 1.0 if query_cmc == candidate_cmc else 0.0
        features["same_type"] = 1.0 if bool(query_types & candidate_types) else 0.0
        features["same_colors"] = 1.0 if query_colors == candidate_colors else 0.0
        features["color_overlap"] = float(len(query_colors & candidate_colors))
    else:
        features["cmc_diff"] = 0.0
        features["cmc_same"] = 0.0
        features["same_type"] = 0.0
        features["same_colors"] = 0.0
        features["color_overlap"] = 0.0

    return features


def extract_ltr_features(
    query: str,
    candidate: str,
    fusion: Any,  # WeightedLateFusion instance
    card_data: dict[str, dict[str, Any]] | None = None,
) -> dict[str, float]:
    """
    Extract comprehensive feature set for Learning-to-Rank.

    Args:
        query: Query card name
        candidate: Candidate card name
        fusion: WeightedLateFusion instance for computing similarity scores
        card_data: Optional card metadata dict

    Returns:
        Dictionary of feature names to feature values
    """
    # Get all similarity scores
    scores = fusion._compute_similarity_scores(query, {candidate})
    candidate_scores = scores.get(candidate, {})

    # Get rank positions (compute by ranking all candidates)
    # For faster evaluation, we could limit to retrieved candidates, but for training we want full ranks
    ranks = _get_rank_positions(query, candidate, fusion, limit_candidates=None)

    # Get query and candidate metadata
    # Handle both card_data dict and card_attrs dict (different naming conventions)
    metadata_dict = (
        card_data or getattr(fusion, "card_data", None) or getattr(fusion, "card_attrs", None)
    )

    # Ensure metadata_dict is actually a dict (not tuple or other type)
    if metadata_dict is not None:
        if not isinstance(metadata_dict, dict):
            logger.warning(
                f"metadata_dict is not a dict: {type(metadata_dict)}, skipping metadata extraction"
            )
            metadata_dict = None
        else:
            # Check if values are dicts (not tuples)
            sample_keys = list(metadata_dict.keys())[:5] if metadata_dict else []
            for key in sample_keys:
                val = metadata_dict[key]
                if not isinstance(val, dict):
                    logger.warning(f"metadata_dict[{key}] is not a dict: {type(val)}, value: {val}")
                    # Try to convert if it's a Series
                    import pandas as pd

                    if isinstance(val, pd.Series):
                        metadata_dict[key] = val.to_dict()
                    else:
                        logger.warning(
                            f"Cannot convert {type(val)} to dict, skipping metadata for this key"
                        )

    query_meta = _get_card_metadata(query, metadata_dict) if metadata_dict else {}
    candidate_meta = _get_card_metadata(candidate, metadata_dict) if metadata_dict else {}

    # Extract all features
    features: dict[str, float] = {}

    # === Direct Similarity Scores ===
    features["embed_score"] = candidate_scores.get("embed", 0.0)
    features["jaccard_score"] = candidate_scores.get("jaccard", 0.0)
    features["functional_score"] = candidate_scores.get("functional", 0.0)
    features["text_embed_score"] = candidate_scores.get("text_embed", 0.0)
    features["visual_embed_score"] = candidate_scores.get("visual_embed", 0.0)
    features["gnn_score"] = candidate_scores.get("gnn", 0.0)
    features["sideboard_score"] = candidate_scores.get("sideboard", 0.0)
    features["temporal_score"] = candidate_scores.get("temporal", 0.0)
    features["archetype_score"] = candidate_scores.get("archetype", 0.0)
    features["format_score"] = candidate_scores.get("format", 0.0)

    # === Rank Positions (for RRF-style methods) ===
    features["embed_rank"] = float(ranks.get("embed", 999))
    features["jaccard_rank"] = float(ranks.get("jaccard", 999))
    features["text_embed_rank"] = float(ranks.get("text_embed", 999))
    features["visual_embed_rank"] = float(ranks.get("visual_embed", 999))
    features["gnn_rank"] = float(ranks.get("gnn", 999))
    features["functional_rank"] = float(ranks.get("functional", 999))

    # === Aggregation Features ===
    score_values = [v for v in candidate_scores.values() if v > 0]
    if score_values:
        features["num_modalities"] = float(len(score_values))
        features["max_score"] = float(max(score_values))
        features["min_score"] = float(min(score_values))
        features["mean_score"] = float(np.mean(score_values))
        features["score_variance"] = float(np.var(score_values))
        features["score_range"] = float(max(score_values) - min(score_values))
        features["score_std"] = float(np.std(score_values))
    else:
        features["num_modalities"] = 0.0
        features["max_score"] = 0.0
        features["min_score"] = 0.0
        features["mean_score"] = 0.0
        features["score_variance"] = 0.0
        features["score_range"] = 0.0
        features["score_std"] = 0.0

    # === Cross-Modal Agreement ===
    text_score = candidate_scores.get("text_embed", 0.0)
    visual_score = candidate_scores.get("visual_embed", 0.0)
    embed_score = candidate_scores.get("embed", 0.0)
    gnn_score = candidate_scores.get("gnn", 0.0)
    jaccard_score = candidate_scores.get("jaccard", 0.0)

    features["text_visual_agreement"] = abs(text_score - visual_score)
    features["embed_gnn_agreement"] = abs(embed_score - gnn_score)
    features["text_jaccard_agreement"] = abs(text_score - jaccard_score)
    features["visual_gnn_agreement"] = abs(visual_score - gnn_score)

    # All signals agree (low variance)
    if score_values and len(score_values) > 1:
        features["all_signals_agree"] = 1.0 if np.std(score_values) < 0.1 else 0.0
    else:
        features["all_signals_agree"] = 0.0

    # === Query-Dependent Features ===
    if query_meta:
        query_types = query_meta.get("types", [])
        features["query_cmc"] = float(query_meta.get("cmc", 0))
        features["query_is_creature"] = 1.0 if "Creature" in query_types else 0.0
        features["query_is_instant"] = 1.0 if "Instant" in query_types else 0.0
        features["query_is_sorcery"] = 1.0 if "Sorcery" in query_types else 0.0
        features["query_is_artifact"] = 1.0 if "Artifact" in query_types else 0.0
        features["query_is_enchantment"] = 1.0 if "Enchantment" in query_types else 0.0
        features["query_is_land"] = 1.0 if "Land" in query_types else 0.0
    else:
        features["query_cmc"] = 0.0
        features["query_is_creature"] = 0.0
        features["query_is_instant"] = 0.0
        features["query_is_sorcery"] = 0.0
        features["query_is_artifact"] = 0.0
        features["query_is_enchantment"] = 0.0
        features["query_is_land"] = 0.0

    # === Candidate-Dependent Features ===
    if candidate_meta:
        candidate_types = candidate_meta.get("types", [])
        features["candidate_cmc"] = float(candidate_meta.get("cmc", 0))
        features["candidate_is_creature"] = 1.0 if "Creature" in candidate_types else 0.0
        features["candidate_is_instant"] = 1.0 if "Instant" in candidate_types else 0.0
        features["candidate_is_sorcery"] = 1.0 if "Sorcery" in candidate_types else 0.0
        features["candidate_is_artifact"] = 1.0 if "Artifact" in candidate_types else 0.0
        features["candidate_is_enchantment"] = 1.0 if "Enchantment" in candidate_types else 0.0
        features["candidate_is_land"] = 1.0 if "Land" in candidate_types else 0.0
    else:
        features["candidate_cmc"] = 0.0
        features["candidate_is_creature"] = 0.0
        features["candidate_is_instant"] = 0.0
        features["candidate_is_sorcery"] = 0.0
        features["candidate_is_artifact"] = 0.0
        features["candidate_is_enchantment"] = 0.0
        features["candidate_is_land"] = 0.0

    # === Query-Candidate Interaction ===
    if query_meta and candidate_meta:
        query_cmc = query_meta.get("cmc", 0)
        candidate_cmc = candidate_meta.get("cmc", 0)
        query_types = set(query_meta.get("types", []))
        candidate_types = set(candidate_meta.get("types", []))
        query_colors = set(query_meta.get("colors", []))
        candidate_colors = set(candidate_meta.get("colors", []))

        features["cmc_diff"] = abs(query_cmc - candidate_cmc)
        features["cmc_same"] = 1.0 if query_cmc == candidate_cmc else 0.0
        features["same_type"] = 1.0 if bool(query_types & candidate_types) else 0.0
        features["same_colors"] = 1.0 if query_colors == candidate_colors else 0.0
        features["color_overlap"] = float(len(query_colors & candidate_colors))
    else:
        features["cmc_diff"] = 0.0
        features["cmc_same"] = 0.0
        features["same_type"] = 0.0
        features["same_colors"] = 0.0
        features["color_overlap"] = 0.0

    return features


def _get_rank_positions(
    query: str, candidate: str, fusion: Any, limit_candidates: set[str] | None = None
) -> dict[str, int]:
    """
    Get rank positions of candidate in each modality's ranked list.

    Args:
        query: Query card name
        candidate: Candidate card name
        fusion: WeightedLateFusion instance

    Returns:
        Dictionary mapping modality name to rank position (1-indexed)
    """
    ranks: dict[str, int] = {}

    try:
        # Get all candidates
        all_candidates = fusion._get_candidates(query)

        # Limit to provided candidates if specified (for faster evaluation)
        if limit_candidates:
            all_candidates = all_candidates & limit_candidates

        if candidate not in all_candidates:
            return ranks

        # Compute scores for all candidates (only the limited set if provided)
        # This is much faster when limit_candidates is small (e.g., 20 vs thousands)
        modality_scores = fusion._compute_similarity_scores(query, all_candidates)

        # Build ranked lists per modality
        for modality in ["embed", "jaccard", "functional", "text_embed", "visual_embed", "gnn"]:
            ranked_list = []
            for c in all_candidates:
                if modality in modality_scores.get(c, {}):
                    ranked_list.append((c, modality_scores[c][modality]))

            # Sort by score descending
            ranked_list.sort(key=lambda x: x[1], reverse=True)

            # Find rank of candidate
            for rank, (c, _) in enumerate(ranked_list, start=1):
                if c == candidate:
                    ranks[modality] = rank
                    break
            else:
                ranks[modality] = 999  # Not in top results

    except Exception as e:
        logger.warning(f"Error computing ranks for {query}-{candidate}: {e}")

    return ranks


def _get_card_metadata(card_name: str, card_data: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """
    Extract metadata for a card.

    Args:
        card_name: Card name
        card_data: Card data dictionary

    Returns:
        Dictionary with metadata (types, cmc, colors, etc.)
    """
    if not card_data or card_name not in card_data:
        return {}

    card = card_data[card_name]

    # Handle pandas Series (from CSV loading) - convert to dict
    import pandas as pd

    if isinstance(card, pd.Series) or (hasattr(card, "to_dict") and callable(card.to_dict)):
        card = card.to_dict()
    elif not isinstance(card, dict):
        # If it's not a dict and not a Series, try to convert
        try:
            if isinstance(card, (tuple, list)):
                # Skip tuples/lists - can't extract metadata
                return {}
            card = dict(card)
        except (TypeError, ValueError):
            return {}

    # Ensure it's a dict now
    if not isinstance(card, dict):
        return {}

    # Extract types (handle various formats)
    types = []
    if "type_line" in card:
        type_line = card["type_line"]
        if isinstance(type_line, str):
            types = [t.strip() for t in type_line.split("—")[0].split()]
        elif isinstance(type_line, list):
            types = type_line
    elif "types" in card:
        types = card["types"] if isinstance(card["types"], list) else [card["types"]]
    elif "type" in card:
        # Handle CSV format with "type" column
        type_str = card.get("type", "")
        if isinstance(type_str, str):
            types = [t.strip() for t in type_str.split("—")[0].split()]

    # Extract CMC (handle both "cmc" and "CMC" column names)
    cmc = card.get("cmc") or card.get("CMC") or card.get("mana_value", 0)
    if not isinstance(cmc, (int, float)) or (
        isinstance(cmc, float) and (cmc != cmc)
    ):  # Check for NaN
        cmc = 0

    # Extract colors (handle both string and list formats)
    colors = card.get("colors", [])
    if isinstance(colors, str):
        colors = list(colors) if colors else []  # Convert "RW" to ["R", "W"]
    elif not isinstance(colors, (list, tuple, set)):
        # Handle non-iterable types (e.g., float/NaN from pandas)
        try:
            import pandas as pd

            if pd.isna(colors):
                colors = []
            else:
                colors = []
        except (ImportError, TypeError):
            colors = []

    return {
        "types": types,
        "cmc": int(cmc),
        "colors": colors,
    }


__all__ = ["_get_card_metadata", "_get_rank_positions", "extract_ltr_features"]
