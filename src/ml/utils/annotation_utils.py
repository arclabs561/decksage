"""Annotation utilities for loading and converting between annotation formats.

Provides unified interface for:
- Loading similarity annotations (CardSimilarityAnnotation JSONL)
- Loading hand annotations (YAML format with 0-4 relevance scale)
- Converting annotations to substitution pairs
- Converting between annotation formats (0-1 float, 0-4 int, categorical)
- Extracting training signals from annotations
- **NEW**: Filtering annotations to prevent test set leakage
- **NEW**: IAA-aware annotation loading
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


def load_test_set_cards(test_set_path: Path | None = None, game: str | None = None) -> set[str]:
    """Load all cards from test set(s) to prevent leakage.

    Args:
        test_set_path: Optional path to specific test set
        game: Optional game filter ('magic', 'pokemon', 'yugioh')

    Returns:
        Set of card names that appear in test sets (should be excluded from training)
    """
    test_cards = set()

    # If specific path provided, use it
    if test_set_path and test_set_path.exists():
        try:
            with open(test_set_path) as f:
                data = json.load(f)
                queries = data.get("queries", {})
                for query, labels in queries.items():
                    test_cards.add(query)
                    for level in [
                        "highly_relevant",
                        "relevant",
                        "somewhat_relevant",
                        "marginally_relevant",
                        "irrelevant",
                    ]:
                        test_cards.update(labels.get(level, []))
        except Exception as e:
            logger.warning(f"Failed to load test set from {test_set_path}: {e}")
    else:
        # Load all test sets (or game-specific)
        from .paths import PATHS

        test_sets = []
        if game:
            test_set_map = {
                "magic": PATHS.test_magic,
                "pokemon": PATHS.test_pokemon,
                "yugioh": PATHS.test_yugioh,
            }
            if game.lower() in test_set_map:
                test_sets.append(test_set_map[game.lower()])
        else:
            # Load all test sets
            test_sets = [PATHS.test_magic, PATHS.test_pokemon, PATHS.test_yugioh]

        for test_path in test_sets:
            if test_path and test_path.exists():
                try:
                    with open(test_path) as f:
                        data = json.load(f)
                        queries = data.get("queries", {})
                        for query, labels in queries.items():
                            test_cards.add(query)
                            for level in [
                                "highly_relevant",
                                "relevant",
                                "somewhat_relevant",
                                "marginally_relevant",
                                "irrelevant",
                            ]:
                                test_cards.update(labels.get(level, []))
                except Exception as e:
                    logger.warning(f"Failed to load test set from {test_path}: {e}")

    logger.info(f"Loaded {len(test_cards)} test set cards for leakage prevention")
    return test_cards


def filter_annotations_for_training(
    annotations: list[dict[str, Any]],
    test_set_path: Path | None = None,
    game: str | None = None,
    strict: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Filter annotations to exclude test set cards (prevent data leakage).

    CRITICAL: This prevents test set cards from appearing in training annotations,
    which would cause data leakage and invalidate evaluation results.

    Args:
        annotations: List of annotation dictionaries
        test_set_path: Optional path to test set (if None, loads all test sets)
        game: Optional game filter
        strict: If True, exclude ANY annotation containing a test card.
                If False, only exclude if BOTH cards are in test set.

    Returns:
        (filtered_annotations, stats_dict) where stats includes:
        - total: Total annotations before filtering
        - filtered: Number filtered out
        - leaked_pairs: Number of pairs with test cards
    """
    test_cards = load_test_set_cards(test_set_path, game)

    if not test_cards:
        logger.warning(
            "No test set cards loaded - cannot filter for leakage. Proceeding with all annotations."
        )
        return annotations, {"total": len(annotations), "filtered": 0, "leaked_pairs": 0}

    filtered = []
    leaked_count = 0

    for ann in annotations:
        card1 = ann.get("card1", "")
        card2 = ann.get("card2", "")

        # Check if either card is in test set
        card1_in_test = card1 in test_cards
        card2_in_test = card2 in test_cards

        if strict:
            # Strict mode: exclude if ANY card is in test set
            if card1_in_test or card2_in_test:
                leaked_count += 1
                continue
        else:
            # Lenient mode: only exclude if BOTH cards are in test set
            if card1_in_test and card2_in_test:
                leaked_count += 1
                continue

        filtered.append(ann)

    stats = {
        "total": len(annotations),
        "filtered": leaked_count,
        "leaked_pairs": leaked_count,
        "remaining": len(filtered),
    }

    if leaked_count > 0:
        logger.warning(
            f"Filtered {leaked_count}/{len(annotations)} annotations containing test set cards "
            f"(leakage prevention). Remaining: {len(filtered)}"
        )
    else:
        logger.info(
            f"No leakage detected: all {len(annotations)} annotations are safe for training"
        )

    return filtered, stats


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
    annotation_entries = []
    if isinstance(data, list):
        annotation_entries = data
    elif isinstance(data, dict):
        if "annotations" in data:
            annotation_entries = data["annotations"]
        elif "tasks" in data:
            annotation_entries = data["tasks"]
        else:
            # Assume it's a single annotation
            annotation_entries = [data]

    for entry in annotation_entries:
        query_card = entry.get("query_card") or entry.get("query") or entry.get("card")
        candidates = entry.get("candidates", [])

        if not query_card or not candidates:
            continue

        for candidate in candidates:
            if isinstance(candidate, dict):
                card = candidate.get("card") or candidate.get("name")
                relevance = candidate.get("relevance", 0)
                similarity_type = candidate.get("similarity_type", "unknown")
                notes = candidate.get("notes", "")
            else:
                # Simple format: just card name
                card = str(candidate)
                relevance = 0
                similarity_type = "unknown"
                notes = ""

            if not card:
                continue

            # Convert relevance (0-4) to similarity_score (0-1)
            similarity_score = convert_relevance_to_similarity_score(relevance, scale="0-4")

            # Determine is_substitute
            is_substitute = (
                relevance == 4 and similarity_type.lower() in ("substitute", "functional")
            ) or (
                similarity_score >= 0.8 and similarity_type.lower() in ("substitute", "functional")
            )

            annotations.append(
                {
                    "card1": query_card,
                    "card2": card,
                    "similarity_score": similarity_score,
                    "similarity_type": similarity_type,
                    "is_substitute": is_substitute,
                    "relevance": relevance,
                    "reasoning": notes or f"Hand annotation: relevance={relevance}",
                    "source": "hand",
                }
            )

    logger.info(f"Loaded {len(annotations)} hand annotations from {annotation_path}")
    return annotations


def load_similarity_annotations(
    annotation_path: Path,
    filter_test_cards: bool = True,
    test_set_path: Path | None = None,
    game: str | None = None,
    filter_temporal: bool = False,
    train_frac: float = 0.7,
    val_frac: float = 0.15,
) -> list[dict[str, Any]]:
    """Load similarity annotations from JSONL file.

    **NEW**: Now supports filtering test set cards and temporal filtering to prevent data leakage.

    Args:
        annotation_path: Path to JSONL file with similarity annotations
        filter_test_cards: If True, exclude annotations containing test set cards
        test_set_path: Optional path to test set (for leakage filtering)
        game: Optional game filter
        filter_temporal: If True, filter annotations by temporal split (exclude test-period cards)
        train_frac: Training fraction for temporal split (default: 0.7)
        val_frac: Validation fraction for temporal split (default: 0.15)

    Returns:
        List of annotation dictionaries
    """
    annotations = []
    if not annotation_path.exists():
        logger.warning(f"Annotation file not found: {annotation_path}")
        return annotations

    # Auto-detect format
    if annotation_path.suffix.lower() in (".yaml", ".yml"):
        annotations = load_hand_annotations(annotation_path)
    else:
        # JSONL format
        with open(annotation_path) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    ann = json.loads(line)
                    annotations.append(ann)
                except json.JSONDecodeError as e:
                    logger.warning(
                        f"Skipping invalid JSON on line {line_num} of {annotation_path}: {e}"
                    )
                    continue

    logger.info(f"Loaded {len(annotations)} annotations from {annotation_path}")

    # Filter test set cards if requested (CRITICAL for preventing leakage)
    if filter_test_cards:
        annotations, stats = filter_annotations_for_training(
            annotations, test_set_path=test_set_path, game=game, strict=True
        )
        if stats["filtered"] > 0:
            logger.warning(
                f"⚠️  LEAKAGE PREVENTION: Filtered {stats['filtered']} annotations "
                f"containing test set cards. Remaining: {stats['remaining']}"
            )

    # Temporal filtering (exclude test-period annotations)
    if filter_temporal:
        try:
            from .temporal_filtering import (
                filter_annotations_by_temporal_split,
                load_decks_for_temporal_filtering,
            )

            decks = load_decks_for_temporal_filtering(game=game)
            if decks:
                train_anns, filtered, temp_stats = filter_annotations_by_temporal_split(
                    annotations, decks, train_frac=train_frac, val_frac=val_frac, game=game
                )
                if temp_stats.get("filtered_out", 0) > 0:
                    logger.warning(
                        f"⚠️  TEMPORAL FILTERING: Removed {temp_stats['filtered_out']} annotations "
                        f"from test period. Remaining: {len(train_anns)}"
                    )
                annotations = train_anns
        except ImportError:
            logger.warning("Temporal filtering not available - install required dependencies")
        except Exception as e:
            logger.warning(f"Temporal filtering failed: {e}")

    return annotations


def convert_relevance_to_similarity_score(relevance: int, scale: str = "0-4") -> float:
    """Convert relevance score (0-4) to similarity score (0-1)."""
    if scale == "0-4":
        # Map 0-4 to 0.0-1.0
        return relevance / 4.0
    else:
        # Default: assume already 0-1
        return float(relevance)


def extract_substitution_pairs_from_annotations(
    annotations: list[dict[str, Any]],
    min_similarity: float = 0.8,
    require_substitute_flag: bool = True,
    min_relevance: int | None = None,
    filter_test_cards: bool = True,
    test_set_path: Path | None = None,
    game: str | None = None,
) -> list[tuple[str, str]]:
    """Extract substitution pairs from similarity annotations.

    **NEW**: Now supports filtering test set cards to prevent data leakage.

    Filters annotations where:
    - is_substitute=True (if require_substitute_flag=True)
    - similarity_score >= min_similarity (for LLM annotations)
    - relevance >= min_relevance (for hand annotations, if provided)
    - similarity_type is 'functional' or 'substitute' (preferred)
    - **NEW**: Cards are NOT in test set (if filter_test_cards=True)

    Args:
        annotations: List of annotation dictionaries
        min_similarity: Minimum similarity score (0-1) for LLM annotations
        require_substitute_flag: If True, only include pairs with is_substitute=True
        min_relevance: Minimum relevance (0-4) for hand annotations. If None, uses min_similarity conversion
        filter_test_cards: If True, exclude pairs containing test set cards (CRITICAL for leakage prevention)
        test_set_path: Optional path to test set (for leakage filtering)
        game: Optional game filter

    Returns:
        List of (card1, card2) tuples
    """
    # Filter test set cards first (before extracting pairs)
    if filter_test_cards:
        annotations, filter_stats = filter_annotations_for_training(
            annotations, test_set_path=test_set_path, game=game, strict=True
        )
        if filter_stats["filtered"] > 0:
            logger.warning(
                f"⚠️  LEAKAGE PREVENTION: Filtered {filter_stats['filtered']} annotations "
                f"before extracting substitution pairs"
            )

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
        f"(min_similarity={min_similarity_effective:.2f}, require_substitute={require_substitute_flag}, "
        f"filter_test_cards={filter_test_cards})"
    )

    return pairs


def convert_annotations_to_substitution_pairs(
    annotation_path: Path,
    output_path: Path | None = None,
    min_similarity: float = 0.8,
    min_relevance: int | None = None,
    require_substitute_flag: bool = True,
    filter_test_cards: bool = True,
    test_set_path: Path | None = None,
    game: str | None = None,
) -> list[tuple[str, str]]:
    """Convert annotations to substitution pairs format.

    **NEW**: Now supports filtering test set cards to prevent data leakage.

    Supports both LLM annotations (JSONL) and hand annotations (YAML).
    This is the main conversion function that bridges annotations to training.

    Args:
        annotation_path: Path to similarity annotations (JSONL) or hand annotations (YAML)
        output_path: Optional path to save substitution pairs JSON
        min_similarity: Minimum similarity score threshold (0-1) for LLM annotations
        min_relevance: Minimum relevance threshold (0-4) for hand annotations. If None, uses min_similarity conversion
        require_substitute_flag: Only include pairs with is_substitute=True
        filter_test_cards: If True, exclude pairs containing test set cards (CRITICAL for leakage prevention)
        test_set_path: Optional path to test set (for leakage filtering)
        game: Optional game filter

    Returns:
        List of (card1, card2) tuples in format used by training scripts
    """
    # Load annotations (auto-detects format, filters test cards if requested)
    annotations = load_similarity_annotations(
        annotation_path,
        filter_test_cards=filter_test_cards,
        test_set_path=test_set_path,
        game=game,
    )

    if not annotations:
        logger.warning(f"No annotations found in {annotation_path}")
        return []

    # Extract substitution pairs (already filtered if filter_test_cards=True)
    pairs = extract_substitution_pairs_from_annotations(
        annotations,
        min_similarity=min_similarity,
        min_relevance=min_relevance,
        require_substitute_flag=require_substitute_flag,
        filter_test_cards=False,  # Already filtered in load_similarity_annotations
        test_set_path=test_set_path,
        game=game,
    )

    # Save if output path provided
    if output_path and pairs:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Save in format expected by training scripts: [[card1, card2], ...]
        pairs_list = [[card1, card2] for card1, card2 in pairs]
        with open(output_path, "w") as f:
            json.dump(pairs_list, f, indent=2)
        logger.info(f"Saved {len(pairs)} substitution pairs to {output_path}")
        if filter_test_cards:
            logger.info("  ✓ Test set cards filtered (leakage prevention enabled)")

    return pairs


def convert_similarity_score_to_relevance(
    similarity_score: float,
    scale: str = "0-4",
) -> int:
    """Convert similarity score (0-1) to relevance score (0-4)."""
    if scale == "0-4":
        # Map 0.0-1.0 to 0-4
        return int(round(similarity_score * 4.0))
    else:
        # Default: assume already 0-4
        return int(similarity_score)
