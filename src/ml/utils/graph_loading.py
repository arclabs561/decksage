"""
Unified graph loading for DeckSage.

Consolidates 3 competing implementations (similarity_methods.load_graph,
data_loading.load_graph_adjacency, shared_operations.load_graph_for_jaccard)
into one interface with consistent caching and return types.
"""

from __future__ import annotations

import logging
import pickle
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple


logger = logging.getLogger(__name__)

# Game name -> DB short code mapping
GAME_DB_CODES = {"magic": "MTG", "pokemon": "PKM", "yugioh": "YGO"}

# Basic lands to optionally filter (Magic only)
_BASIC_LANDS = {
    "Plains",
    "Island",
    "Swamp",
    "Mountain",
    "Forest",
    "Snow-Covered Plains",
    "Snow-Covered Island",
    "Snow-Covered Swamp",
    "Snow-Covered Mountain",
    "Snow-Covered Forest",
    "Wastes",
}


class GraphData(NamedTuple):
    """Unified graph representation.

    adjacency: card -> set of neighbor cards (always present)
    weights: (card1, card2) -> edge weight (None if include_weights=False)
    """

    adjacency: dict[str, set[str]]
    weights: dict[tuple[str, str], float] | None = None


def load_graph(
    source: Path | str | None = None,
    *,
    game: str | None = None,
    filter_lands: bool = False,
    include_weights: bool = True,
    use_cache: bool = True,
) -> GraphData:
    """
    Load a co-occurrence graph from SQLite DB or CSV.

    Resolution order:
    1. If source is a .db file -> load from IncrementalCardGraph
    2. If source is a .csv file -> load from CSV pairs
    3. If source is None -> auto-discover from PATHS

    Args:
        source: Path to .db or .csv file, or None for auto-discovery
        game: Game name (magic/pokemon/yugioh) for DB filtering
        filter_lands: Remove basic land nodes (Magic only)
        include_weights: Whether to compute edge weights
        use_cache: Use pickle cache for CSV sources
    """
    from .paths import PATHS

    if source is None:
        # Auto-discover: prefer unified DB, fall back to largest CSV
        db_path = PATHS.incremental_graph_db
        if db_path and db_path.exists():
            source = db_path
        else:
            pairs_dir = PATHS.project_root / "data/processed"
            game_prefix = f"pairs_{game}_" if game else "pairs_"
            candidates = sorted(
                pairs_dir.glob(f"{game_prefix}*.csv"),
                key=lambda p: p.stat().st_size,
                reverse=True,
            )
            if candidates:
                source = candidates[0]
            else:
                raise FileNotFoundError(
                    f"No graph source found (checked {db_path} and {pairs_dir}/{game_prefix}*.csv)"
                )

    source = Path(source)

    if source.suffix == ".db":
        return _load_from_db(
            source, game=game, filter_lands=filter_lands, include_weights=include_weights
        )
    elif source.suffix == ".csv":
        return _load_from_csv(
            source, filter_lands=filter_lands, include_weights=include_weights, use_cache=use_cache
        )
    else:
        raise ValueError(f"Unsupported graph source format: {source.suffix} (expected .db or .csv)")


def _load_from_db(
    db_path: Path,
    game: str | None = None,
    filter_lands: bool = False,
    include_weights: bool = True,
) -> GraphData:
    """Load graph from IncrementalCardGraph SQLite database."""
    from ..data.incremental_graph import IncrementalCardGraph

    graph = IncrementalCardGraph(graph_path=db_path, use_sqlite=True)
    db_game = GAME_DB_CODES.get(game, game) if game else None
    edges = graph.query_edges(game=db_game, min_weight=1)

    adj: dict[str, set[str]] = defaultdict(set)
    weights: dict[tuple[str, str], float] = {} if include_weights else None

    for edge in edges:
        c1, c2 = edge.card1, edge.card2
        if filter_lands and (c1 in _BASIC_LANDS or c2 in _BASIC_LANDS):
            continue
        adj[c1].add(c2)
        adj[c2].add(c1)
        if include_weights:
            key = (c1, c2) if c1 <= c2 else (c2, c1)
            weights[key] = max(weights.get(key, 0.0), edge.weight)

    result = GraphData(adjacency=dict(adj), weights=weights)
    logger.info(
        "Loaded graph from %s: %d cards, %s edges",
        db_path.name,
        len(result.adjacency),
        f"{len(weights):,}" if weights else "no weights",
    )
    return result


def _load_from_csv(
    csv_path: Path,
    filter_lands: bool = False,
    include_weights: bool = True,
    use_cache: bool = True,
) -> GraphData:
    """Load graph from pairs CSV (columns: NAME_1, NAME_2, optional COUNT_MULTISET)."""
    import csv

    # Check pickle cache
    cache_suffix = "_nw" if not include_weights else ""
    cache_path = csv_path.with_suffix(f".graph{cache_suffix}.pkl")
    if use_cache and cache_path.exists():
        csv_mtime = csv_path.stat().st_mtime
        cache_mtime = cache_path.stat().st_mtime
        if cache_mtime > csv_mtime:
            try:
                with open(cache_path, "rb") as f:
                    cached = pickle.load(f)
                logger.info(
                    "Loaded graph from cache: %s (%d cards)", cache_path.name, len(cached.adjacency)
                )
                return cached
            except (pickle.UnpicklingError, EOFError, KeyError):
                pass

    adj: dict[str, set[str]] = defaultdict(set)
    weights: dict[tuple[str, str], float] = {} if include_weights else None

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            c1 = row.get("NAME_1", "").strip()
            c2 = row.get("NAME_2", "").strip()
            if not c1 or not c2 or c1 == c2:
                continue
            if filter_lands and (c1 in _BASIC_LANDS or c2 in _BASIC_LANDS):
                continue
            adj[c1].add(c2)
            adj[c2].add(c1)
            if include_weights:
                w = float(row.get("COUNT_MULTISET", row.get("weight", 1)))
                key = (c1, c2) if c1 <= c2 else (c2, c1)
                weights[key] = weights.get(key, 0.0) + w

    result = GraphData(adjacency=dict(adj), weights=weights)

    # Save cache
    if use_cache:
        try:
            with open(cache_path, "wb") as f:
                pickle.dump(result, f, protocol=pickle.HIGHEST_PROTOCOL)
        except OSError:
            pass

    logger.info("Loaded graph from CSV: %s (%d cards)", csv_path.name, len(result.adjacency))
    return result
