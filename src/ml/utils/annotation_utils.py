"""Annotation utilities for loading and converting between annotation formats.

Provides unified interface for:
- Loading similarity annotations (CardSimilarityAnnotation JSONL)
- Loading hand annotations (YAML format with 0-4 relevance scale)
- Converting annotations to substitution pairs
- Converting between annotation formats (0-1 float, 0-4 int, categorical)
- Extracting training signals from annotations
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any


try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False
    yaml = None

try:
    from .logging_config import get_logger

    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


def load_hand_annotations(annotation_path: Path) -> list[dict[str, Any]]:
    """Load hand annotations from YAML file and convert to similarity annotation format.

    Hand annotations use:
    - YAML format with query_card and candidates
    - 0-4 relevance scale
    - similarity_type field (e.g., "substitute")

    Converts to similarity annotation format:
    - card1 = query_card, card2 = candidate card
    - similarity_score = converted from relevance (0-4 → 0-1)
    - is_substitute = True if relevance=4 and similarity_type="substitute"

    Args:
        annotation_path: Path to YAML file with hand annotations

    Returns:
        List of annotation dictionaries in similarity annotation format
    """
    if not HAS_YAML:
        logger.error("PyYAML required for loading hand annotations. Install: pip install pyyaml")
        return []

    annotations = []
    if not annotation_path.exists():
        logger.warning(f"Annotation file not found: {annotation_path}")
        return annotations

    try:
        with open(annotation_path) as f:
            data = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load YAML from {annotation_path}: {e}")
        return []

    # Handle both formats: annotations list or tasks list
    annotation_entries = data.get("annotations", []) or data.get("tasks", [])

    for entry in annotation_entries:
        query_card = entry.get("query_card") or entry.get("query")
        if not query_card:
            continue

        candidates = entry.get("candidates", [])
        for cand in candidates:
            card2 = cand.get("card")
            if not card2:
                continue

            relevance = cand.get("relevance")
            if relevance is None:
                continue

            try:
                relevance_int = int(relevance)
            except (ValueError, TypeError):
                continue

            similarity_type = cand.get("similarity_type", "")

            # Convert to similarity annotation format
            similarity_score = convert_relevance_to_similarity_score(relevance_int, scale="0-4")

            # is_substitute: Use explicit field if available, otherwise infer from relevance+type
            is_substitute_explicit = cand.get("is_substitute")
            if is_substitute_explicit is not None:
                is_substitute = bool(is_substitute_explicit)
            else:
                # Fallback: infer from relevance=4 and similarity_type
                is_substitute = relevance_int == 4 and similarity_type in (
                    "substitute",
                    "functional",
                )

            ann = {
                "card1": query_card,
                "card2": card2,
                "similarity_score": similarity_score,
                "similarity_type": similarity_type or "unknown",
                "is_substitute": is_substitute,
                "reasoning": cand.get("notes", ""),
                "context_dependent": similarity_type in ("synergy", "archetype"),
                "example_decks": [],
                # Enhanced fields for downstream tasks
                "role_match": cand.get("role_match"),
                "archetype_context": cand.get("archetype_context"),
                "format_context": cand.get("format_context"),
                "substitution_quality": cand.get("substitution_quality"),
            }
            annotations.append(ann)

    logger.info(
        f"Loaded {len(annotations)} annotations from hand annotation file {annotation_path}"
    )
    return annotations


def load_similarity_annotations(annotation_path: Path) -> list[dict[str, Any]]:
    """Load similarity annotations from JSONL file.

    Auto-detects format: JSONL (LLM annotations) or YAML (hand annotations).

    Args:
        annotation_path: Path to JSONL or YAML file

    Returns:
        List of annotation dictionaries in unified format
    """
    if not annotation_path.exists():
        logger.warning(f"Annotation file not found: {annotation_path}")
        return []

    # Auto-detect format by extension
    if annotation_path.suffix in (".yaml", ".yml"):
        return load_hand_annotations(annotation_path)

    # Default to JSONL
    annotations = []
    with open(annotation_path) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                ann = json.loads(line)
                annotations.append(ann)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse line {line_num} in {annotation_path}: {e}")
                continue

    logger.info(f"Loaded {len(annotations)} similarity annotations from {annotation_path}")
    return annotations


def extract_substitution_pairs_from_annotations(
    annotations: list[dict[str, Any]],
    min_similarity: float = 0.8,
    require_substitute_flag: bool = True,
    min_relevance: int | None = None,
) -> list[tuple[str, str]]:
    """Extract substitution pairs from similarity annotations.

    Filters annotations where:
    - is_substitute=True (if require_substitute_flag=True)
    - similarity_score >= min_similarity (for LLM annotations)
    - relevance >= min_relevance (for hand annotations, if provided)
    - similarity_type is 'functional' or 'substitute' (preferred)

    Args:
        annotations: List of annotation dictionaries
        min_similarity: Minimum similarity score (0-1) for LLM annotations
        require_substitute_flag: If True, only include pairs with is_substitute=True
        min_relevance: Minimum relevance (0-4) for hand annotations. If None, uses min_similarity conversion

    Returns:
        List of (card1, card2) tuples
    """
    pairs = []

    # Convert min_relevance to min_similarity if not provided
    if min_relevance is not None:
        min_similarity_effective = convert_relevance_to_similarity_score(min_relevance, scale="0-4")
    else:
        min_similarity_effective = min_similarity

    for ann in annotations:
        # Check is_substitute flag
        if require_substitute_flag and not ann.get("is_substitute", False):
            continue

        # Check similarity score (converted from relevance if needed)
        similarity_score = ann.get("similarity_score", 0.0)
        if similarity_score < min_similarity_effective:
            continue

        # Prefer functional/substitute similarity types
        similarity_type = ann.get("similarity_type", "")
        if similarity_type not in ("functional", "substitute", "similar_function"):
            # Still include if is_substitute=True, but log
            if require_substitute_flag:
                logger.debug(
                    f"Including {ann.get('card1')} <-> {ann.get('card2')} "
                    f"with type '{similarity_type}' (is_substitute=True)"
                )

        card1 = ann.get("card1")
        card2 = ann.get("card2")

        if not card1 or not card2:
            logger.warning(f"Skipping annotation with missing cards: {ann}")
            continue

        # Normalize pair (always store in consistent order)
        pair = tuple(sorted([card1, card2]))
        pairs.append(pair)

    # Deduplicate
    pairs = list(set(pairs))

    logger.info(
        f"Extracted {len(pairs)} substitution pairs "
        f"(min_similarity={min_similarity_effective:.2f}, require_substitute={require_substitute_flag})"
    )

    return pairs


def convert_annotations_to_substitution_pairs(
    annotation_path: Path,
    output_path: Path | None = None,
    min_similarity: float = 0.8,
    min_relevance: int | None = None,
    require_substitute_flag: bool = True,
) -> list[tuple[str, str]]:
    """Convert annotations to substitution pairs format.

    Supports both LLM annotations (JSONL) and hand annotations (YAML).
    This is the main conversion function that bridges annotations to training.

    Args:
        annotation_path: Path to similarity annotations (JSONL) or hand annotations (YAML)
        output_path: Optional path to save substitution pairs JSON
        min_similarity: Minimum similarity score threshold (0-1) for LLM annotations
        min_relevance: Minimum relevance threshold (0-4) for hand annotations. If None, uses min_similarity conversion
        require_substitute_flag: Only include pairs with is_substitute=True

    Returns:
        List of (card1, card2) tuples in format used by training scripts
    """
    # Load annotations (auto-detects format)
    annotations = load_similarity_annotations(annotation_path)

    if not annotations:
        logger.warning(f"No annotations found in {annotation_path}")
        return []

    # Extract substitution pairs
    pairs = extract_substitution_pairs_from_annotations(
        annotations,
        min_similarity=min_similarity,
        min_relevance=min_relevance,
        require_substitute_flag=require_substitute_flag,
    )

    # Save if output path provided
    if output_path and pairs:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Save in format expected by training scripts: [[card1, card2], ...]
        pairs_list = [[card1, card2] for card1, card2 in pairs]
        with open(output_path, "w") as f:
            json.dump(pairs_list, f, indent=2)
        logger.info(f"Saved {len(pairs)} substitution pairs to {output_path}")

    return pairs


def convert_similarity_score_to_relevance(
    similarity_score: float,
    scale: str = "0-4",
) -> int:
    """Convert similarity score (0-1 float) to relevance scale (0-4 int).

    Args:
        similarity_score: Float score 0.0-1.0
        scale: Target scale ("0-4" for int, "0-1" for float)

    Returns:
        Relevance score on target scale
    """
    if scale == "0-4":
        # Map 0-1 to 0-4
        if similarity_score >= 0.9:
            return 4
        elif similarity_score >= 0.7:
            return 3
        elif similarity_score >= 0.5:
            return 2
        elif similarity_score >= 0.3:
            return 1
        else:
            return 0
    elif scale == "0-1":
        return similarity_score
    else:
        raise ValueError(f"Unknown scale: {scale}")


def convert_relevance_to_similarity_score(
    relevance: int,
    scale: str = "0-4",
) -> float:
    """Convert relevance score to similarity score.

    Args:
        relevance: Relevance score (0-4 int or 0-1 float)
        scale: Source scale ("0-4" for int, "0-1" for float)

    Returns:
        Similarity score (0-1 float)
    """
    if scale == "0-4":
        # Map 0-4 to 0-1
        mapping = {4: 0.95, 3: 0.75, 2: 0.55, 1: 0.35, 0: 0.1}
        return mapping.get(relevance, 0.0)
    elif scale == "0-1":
        return float(relevance)
    else:
        raise ValueError(f"Unknown scale: {scale}")


def load_substitution_pairs_from_annotations(
    annotation_path: Path,
    min_similarity: float = 0.8,
) -> list[tuple[str, str]]:
    """Load substitution pairs from similarity annotations.

    Convenience wrapper for convert_annotations_to_substitution_pairs.
    Used by training scripts to load annotations directly.

    Args:
        annotation_path: Path to similarity annotations JSONL
        min_similarity: Minimum similarity score threshold

    Returns:
        List of (card1, card2) tuples
    """
    return convert_annotations_to_substitution_pairs(
        annotation_path,
        min_similarity=min_similarity,
        require_substitute_flag=True,
    )
