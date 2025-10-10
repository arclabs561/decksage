"""Shared data loading utilities for multi-game experiments."""

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from .constants import get_filter_set
from .paths import PATHS

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


def load_test_set(game: str = "magic", path: Path | None = None) -> dict[str, Any]:
    """
    Load canonical test set.

    Args:
        game: 'magic', 'pokemon', or 'yugioh'
        path: Custom path (overrides game parameter)

    Returns:
        Dict mapping query cards to relevance labels
    """
    test_path = Path(path) if path else getattr(PATHS, f"test_{game}")

    with open(test_path) as f:
        return json.load(f)


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
    with open(jsonl_path) as f:
        for line in f:
            if not line.strip():
                continue
            deck = json.loads(line)

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
