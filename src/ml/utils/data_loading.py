"""Shared data loading utilities for multi-game experiments."""

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from .constants import get_filter_set
from .paths import PATHS


logger = logging.getLogger(__name__)

# Schema validation (optional, graceful degradation)
try:
    from ..data.export_schema import validate_deck_record

    HAS_SCHEMA_VALIDATION = True
except ImportError:
    HAS_SCHEMA_VALIDATION = False
    validate_deck_record = None


try:
    from gensim.models import KeyedVectors

    HAS_GENSIM = True
except ImportError:
    HAS_GENSIM = False
    KeyedVectors = None


def load_pairs(
    dataset: str = "large",
    game: str | None = None,
    filter_common: bool = False,
    filter_level: str = "basic",
) -> pd.DataFrame:
    """
    Load card co-occurrence pairs.

    Args:
        dataset: 'large' (39K decks), '500' (500 decks), or custom path
        game: 'magic', 'yugioh', 'pokemon' (for filtering)
        filter_common: Remove common cards (lands, energy, etc.)
        filter_level: 'basic', 'common', 'all' (game-specific)

    Returns:
        DataFrame with columns: NAME_1, NAME_2, COUNT_MULTISET
    """
    if dataset == "large":
        path = PATHS.pairs_large
    elif dataset == "500":
        path = PATHS.pairs_500
    else:
        path = Path(dataset)  # Custom path

    df = pd.read_csv(path)

    if filter_common and game:
        filter_set = get_filter_set(game, filter_level)
        if filter_set:
            df = df[~df["NAME_1"].isin(filter_set)]
            df = df[~df["NAME_2"].isin(filter_set)]

    return df


def load_embeddings(name: str) -> "KeyedVectors":
    """
    Load embedding model.

    Args:
        name: Model name (e.g., 'magic_39k_decks_pecanpy', 'deepwalk', 'node2vec_bfs')

    Returns:
        Gensim KeyedVectors
    """
    if not HAS_GENSIM:
        raise ImportError("Install gensim: pip install gensim")

    path = PATHS.embedding(name)

    # Handle both with and without extension
    if not path.exists() and not str(name).endswith(".wv"):
        path = PATHS.embeddings / f"{name}.wv"

    return KeyedVectors.load(str(path))


def load_test_set(
    game: str = "magic",
    path: Path | None = None,
    validate: bool = False,
    auto_fix: bool = False,
) -> dict[str, Any]:
    """
    Load unified test set (merged from best available sources).

    Args:
        game: 'magic', 'pokemon', or 'yugioh'
        path: Custom path (overrides game parameter)
        validate: If True, validate test set coverage and log issues
        auto_fix: If True and validate=True, automatically fix issues (expand test set, etc.)

    Returns:
        Dict with 'queries' key containing query cards to relevance labels mapping

    Raises:
        FileNotFoundError: If test set file doesn't exist
        json.JSONDecodeError: If file is not valid JSON
        ValueError: If test set is empty or invalid format
    """
    # Get test set path
    if path:
        test_path = Path(path)
    else:
        # Try to get from PATHS
        try:
            test_path = getattr(PATHS, f"test_{game}")
        except AttributeError:
            # Fallback: construct path manually
            from .paths import PATHS as P

            test_path = P.experiments / f"test_set_unified_{game}.json"

    # Check file exists
    if not test_path.exists():
        raise FileNotFoundError(f"Test set not found: {test_path}")

    # Check file is not empty
    if test_path.stat().st_size == 0:
        raise ValueError(f"Test set file is empty: {test_path}")

    # Load JSON
    try:
        with open(test_path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in test set {test_path}: {e}") from e

    # Validate basic structure
    if not isinstance(data, dict):
        raise ValueError(f"Test set must be a dict, got {type(data)}")

    # Check if empty
    queries = data.get("queries", data) if isinstance(data, dict) else data
    if not queries or (isinstance(queries, dict) and len(queries) == 0):
        raise ValueError(f"Test set is empty: {test_path}")

    # Optional validation and auto-fixing
    if validate:
        try:
            from ..utils.test_set_helpers import load_test_set_with_validation

            # Use helper which handles validation without circular dependency
            validated_data, validation_result = load_test_set_with_validation(
                test_set_path=test_path,
                game=game,
                min_queries=100,
                min_labels=5,
                auto_fix=auto_fix,
            )

            # Use validated data if auto_fix was successful
            if auto_fix and validation_result.get("valid"):
                data = validated_data

            if not validation_result["valid"]:
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(f"Test set validation issues for {test_path}:")
                for issue in validation_result.get("issues", []):
                    logger.warning(f"  - {issue}")
        except Exception as e:
            # Don't fail loading if validation fails, but log it
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Test set validation failed (continuing anyway): {e}")

    return data


def build_adjacency_dict(df: pd.DataFrame, filter_set: set[str] | None = None) -> dict[str, set]:
    """
    Build adjacency dictionary from pairs.

    Args:
        df: DataFrame with NAME_1, NAME_2 columns
        filter_set: Optional set of cards to exclude

    Returns:
        Dict mapping card -> set of co-occurring cards
    """
    from collections import defaultdict

    adj = defaultdict(set)

    for _, row in df.iterrows():
        c1, c2 = row["NAME_1"], row["NAME_2"]

        if filter_set and (c1 in filter_set or c2 in filter_set):
            continue

        adj[c1].add(c2)
        adj[c2].add(c1)

    return dict(adj)


def load_decks_jsonl(
    jsonl_path: Path | None = None,
    sources: list[str] | None = None,
    max_placement: int | None = None,
    formats: list[str] | None = None,
    validate: bool = True,
) -> list[dict[str, Any]]:
    """
    Load decks from JSONL export with optional filtering and validation.

    Args:
        jsonl_path: Path to JSONL file (default: decks_with_metadata)
        sources: Filter by source (NOTE: source field is null in current data)
        max_placement: Filter by placement (e.g., 8 for Top 8 only)
        formats: Filter by format (e.g., ['Modern', 'Legacy'])
        validate: Use Pydantic validation (default True)

    Returns:
        List of deck dictionaries with full metadata

    Note: With validate=True, returns validated decks as dicts.
          Invalid decks are skipped in lenient mode.
    """
    if jsonl_path is None:
        jsonl_path = PATHS.decks_with_metadata

    if validate:
        # Use validators for type safety and data quality
        from ..validation.validators.loader import load_decks_lenient

        validated_decks = load_decks_lenient(
            jsonl_path,
            game="auto",
            check_legality=False,
            verbose=False,
        )

        # Apply filters
        filtered = []
        for deck in validated_decks:
            # Source filter (not usable - field is null in data)
            if sources:
                # Can't filter by source - all null
                pass

            # Placement filter
            if max_placement is not None:
                placement = deck.placement or 0
                if placement <= 0 or placement > max_placement:
                    continue

            # Format filter
            if formats and deck.format not in formats:
                continue

            # Convert to dict for backward compatibility and normalize placement
            d = deck.model_dump()
            if d.get("placement") is None:
                d["placement"] = 0
            filtered.append(d)

        return filtered

    # Legacy path: no validation
    decks = []
    validation_warnings = 0
    validation_errors = 0

    with open(jsonl_path) as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue

            try:
                deck = json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning(f"Line {line_num}: Invalid JSON - {e}")
                continue

            # Schema validation (non-strict by default)
            if HAS_SCHEMA_VALIDATION and validate_deck_record is not None:
                is_valid, error, validated_deck = validate_deck_record(deck, strict=False)
                if not is_valid:
                    validation_errors += 1
                    if validation_errors <= 5:  # Log first 5 errors
                        logger.warning(f"Line {line_num}: Schema validation failed - {error}")
                    continue
                elif error:  # Warning but valid
                    validation_warnings += 1
                    if validation_warnings <= 5:  # Log first 5 warnings
                        logger.debug(f"Line {line_num}: Schema validation warning - {error}")
                # Use validated deck if available (normalized)
                if validated_deck:
                    deck = validated_deck

            # Apply filters
            if sources and deck.get("source") not in sources:
                continue

            if max_placement is not None:
                placement = deck.get("placement", 0)
                if placement <= 0 or placement > max_placement:
                    continue

            if formats and deck.get("format") not in formats:
                continue

            decks.append(deck)

    if validation_warnings > 0 or validation_errors > 0:
        logger.info(
            f"Schema validation: {len(decks)} valid decks, "
            f"{validation_warnings} warnings, {validation_errors} errors"
        )

    return decks


def load_tournament_decks(jsonl_path: Path | None = None) -> list[dict[str, Any]]:
    """
    Load only tournament-curated decks (mtgtop8, goldfish).

    Convenience wrapper for load_decks_jsonl with tournament sources.
    """
    return load_decks_jsonl(jsonl_path, sources=["mtgtop8", "goldfish"])


def group_by_source(decks: list[dict]) -> dict[str, list[dict]]:
    """Group decks by data source."""
    grouped = defaultdict(list)
    for deck in decks:
        source = deck.get("source", "unknown")
        grouped[source].append(deck)
    return dict(grouped)


def group_by_format(decks: list[dict]) -> dict[str, list[dict]]:
    """Group decks by format."""
    grouped = defaultdict(list)
    for deck in decks:
        fmt = deck.get("format", "unknown")
        grouped[fmt].append(deck)
    return dict(grouped)


def deck_stats(decks: list[dict]) -> dict[str, Any]:
    """
    Compute summary statistics for a collection of decks.

    Returns dict with:
        - total: Number of decks
        - by_source: Count per source
        - by_format: Count per format
        - by_archetype: Count per archetype
        - has_player: Number with player field
        - has_event: Number with event field
        - has_placement: Number with placement field
    """
    stats = {
        "total": len(decks),
        "by_source": defaultdict(int),
        "by_format": defaultdict(int),
        "by_archetype": defaultdict(int),
        "has_player": 0,
        "has_event": 0,
        "has_placement": 0,
    }

    for deck in decks:
        stats["by_source"][deck.get("source", "unknown")] += 1
        stats["by_format"][deck.get("format", "unknown")] += 1
        stats["by_archetype"][deck.get("archetype", "unknown")] += 1

        if deck.get("player"):
            stats["has_player"] += 1
        if deck.get("event"):
            stats["has_event"] += 1
        placement = deck.get("placement") or 0
        if placement > 0:
            stats["has_placement"] += 1

    # Convert defaultdicts to regular dicts
    stats["by_source"] = dict(stats["by_source"])
    stats["by_format"] = dict(stats["by_format"])
    stats["by_archetype"] = dict(stats["by_archetype"])

    return stats


def load_card_attributes(
    attrs_path: Path | None = None,
    enrich_with_images: bool = False,
    game: str | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Load card attributes from CSV with optional image URL enrichment.

    Args:
        attrs_path: Path to card attributes CSV (default: PATHS.card_attributes)
        enrich_with_images: If True, fetch missing image URLs from Scryfall API
        game: Game filter for image fetching (currently only 'magic' supported)

    Returns:
        Dict mapping card name -> card attributes dict
    """
    if attrs_path is None:
        attrs_path = PATHS.card_attributes

    if not attrs_path or not attrs_path.exists():
        import logging

        logger = logging.getLogger(__name__)
        logger.debug(f"Card attributes file not found: {attrs_path}")
        return {}

    try:
        import logging

        logger = logging.getLogger(__name__)
        logger.info(f"Loading card attributes from {attrs_path}...")
        attrs_df = pd.read_csv(attrs_path)

        # Find name column
        name_col = None
        for col in ["NAME", "name", "card_name", "Card"]:
            if col in attrs_df.columns:
                name_col = col
                break

        if not name_col:
            logger.warning("Could not find name column in card attributes CSV")
            return {}

        # Build attributes dict
        card_attributes = {}
        valid_mask = attrs_df[name_col].notna() & (attrs_df[name_col].astype(str).str.strip() != "")
        valid_df = attrs_df[valid_mask]

        for idx in valid_df.index:
            row = valid_df.loc[idx]
            card_name = str(row[name_col]).strip()
            if card_name:
                # Convert row to dict, preserving all columns
                attrs = row.to_dict()
                # Normalize name field
                attrs["name"] = card_name
                card_attributes[card_name] = attrs

        logger.info(f"Loaded attributes for {len(card_attributes):,} cards")

        # Optionally enrich with image URLs
        if enrich_with_images and (game is None or game == "magic"):
            try:
                from ..utils.scryfall_image_urls import enrich_card_attributes_with_images

                logger.info("Enriching card attributes with image URLs...")
                stats = enrich_card_attributes_with_images(card_attributes, resume=True)
                logger.info(
                    f"Image URL enrichment: {stats['fetched']} fetched, "
                    f"{stats['failed']} failed, {stats['already_had']} already had"
                )
            except Exception as e:
                logger.warning(f"Failed to enrich with image URLs: {e}")

        return card_attributes
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Could not load card attributes: {e}")
        return {}
