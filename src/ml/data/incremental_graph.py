#!/usr/bin/env python3
"""
Incremental Graph Database for Continuous Card Co-occurrence Updates

Maintains an annotated graph that updates with each scrape/data collection.
Supports:
- Incremental edge/node addition
- Temporal tracking (first_seen, last_seen)
- Efficient export for GNN training
- Graph statistics and monitoring
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np


try:
    import pandas as pd

    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

HAS_PARQUET = False
with suppress(ModuleNotFoundError):
    HAS_PARQUET = importlib.util.find_spec("pyarrow.parquet") is not None

try:
    from ml.data.card_database import get_card_database

    HAS_CARD_DB = True
except ImportError:
    HAS_CARD_DB = False


@dataclass
class CardNode:
    """Node in the card co-occurrence graph."""

    name: str
    game: str | None = None  # "MTG", "PKM", "YGO", or None
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    total_decks: int = 0
    attributes: dict[str, Any] | None = None
    oracle_text: str | None = None
    image_url: str | None = None

    def __post_init__(self):
        if self.first_seen is None:
            self.first_seen = datetime.now()
        if self.last_seen is None:
            self.last_seen = datetime.now()
        if self.attributes is None:
            self.attributes = {}

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        result = {
            "name": self.name,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "total_decks": self.total_decks,
        }
        if self.game:
            result["game"] = self.game
        if self.attributes:
            result["attributes"] = self.attributes
        if self.oracle_text:
            result["oracle_text"] = self.oracle_text
        if self.image_url:
            result["image_url"] = self.image_url
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CardNode:
        """Create from dict."""
        return cls(
            name=data["name"],
            game=data.get("game"),
            first_seen=datetime.fromisoformat(data["first_seen"]),
            last_seen=datetime.fromisoformat(data["last_seen"]),
            total_decks=data.get("total_decks", 0),
            attributes=data.get("attributes"),
            oracle_text=data.get("oracle_text"),
            image_url=data.get("image_url"),
        )


@dataclass
class Edge:
    """Edge in the card co-occurrence graph."""

    card1: str
    card2: str
    game: str | None = None  # "MTG", "PKM", "YGO", or None
    weight: float = 1.0
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    deck_sources: list[str] | None = None  # Optional: track which decks contributed
    metadata: dict[str, Any] | None = (
        None  # Format, placement, event_date, archetype, partition, similarity scores
    )
    source_type: str = (
        "co_occurrence"  # co_occurrence, ppmi, oracle_text, annotation, propagated, card_set
    )

    # Enhanced temporal distribution (new)
    monthly_counts: dict[str, int] | None = None  # "2024-01" -> 12 (month -> count)
    format_periods: dict[str, dict[str, int]] | None = (
        None  # "Standard_2024-2025" -> {"2024-01": 10, ...}
    )
    temporal_stats: dict[str, Any] | None = None  # Cached temporal statistics

    def __post_init__(self):
        if self.first_seen is None:
            self.first_seen = datetime.now()
        if self.last_seen is None:
            self.last_seen = datetime.now()
        if self.deck_sources is None:
            self.deck_sources = []
        if self.metadata is None:
            self.metadata = {}
        if self.monthly_counts is None:
            self.monthly_counts = {}
        if self.format_periods is None:
            self.format_periods = {}

    def update_temporal(self, timestamp: datetime, format: str | None = None) -> None:
        """
        Update temporal distribution with new occurrence.

        Args:
            timestamp: When this co-occurrence happened
            format: Format name (e.g., "Standard", "Modern") if available

        Raises:
            ValueError: If timestamp is None or invalid
        """
        if timestamp is None:
            raise ValueError("timestamp cannot be None")

        if not isinstance(timestamp, datetime):
            raise TypeError(f"timestamp must be datetime, got {type(timestamp)}")

        # Update monthly counts
        month_key = timestamp.strftime("%Y-%m")
        self.monthly_counts[month_key] = self.monthly_counts.get(month_key, 0) + 1

        # Update format-specific counts if format provided (and not empty)
        if format and format.strip():
            format_period_key = self._get_format_period_key(format.strip(), timestamp)
            if format_period_key not in self.format_periods:
                self.format_periods[format_period_key] = {}
            self.format_periods[format_period_key][month_key] = (
                self.format_periods[format_period_key].get(month_key, 0) + 1
            )

        # Invalidate cached stats
        self.temporal_stats = None

    def _get_format_period_key(self, format: str, timestamp: datetime) -> str:
        """
        Get format period key for temporal tracking.

        Args:
            format: Format name (must be non-empty)
            timestamp: Date for period determination

        Returns:
            Format period key string

        Examples:
        - "Standard_2024-2025" (MTG rotation period)
        - "Standard_G" (Pokémon regulation mark)
        - "Advanced_2025-Q4" (Yu-Gi-Oh ban list period)
        """
        if not format or not format.strip():
            # Fallback to year if format is empty
            return f"Unknown_{timestamp.year}"

        format = format.strip()

        try:
            from ml.data.format_events import get_format_period_key

            # Use game if available, otherwise fallback to year
            if self.game:
                return get_format_period_key(self.game, format, timestamp)
        except (ImportError, Exception):
            # Fallback on any error (ImportError, AttributeError, etc.)
            pass

        # Fallback to year-based periods
        year = timestamp.year
        return f"{format}_{year}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        result = {
            "card1": self.card1,
            "card2": self.card2,
            "weight": self.weight,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "deck_sources": self.deck_sources,
            "source_type": self.source_type,
        }
        if self.game:
            result["game"] = self.game
        if self.metadata:
            result["metadata"] = self.metadata
        if self.monthly_counts:
            result["monthly_counts"] = self.monthly_counts
        if self.format_periods:
            result["format_periods"] = self.format_periods
        if self.temporal_stats:
            result["temporal_stats"] = self.temporal_stats
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Edge:
        """
        Create Edge from dict (deserialization).

        Args:
            data: Dictionary with edge data (from to_dict())

        Returns:
            Edge object

        Raises:
            KeyError: If required fields (card1, card2) are missing
            ValueError: If date strings cannot be parsed
        """
        # Validate required fields
        if "card1" not in data or "card2" not in data:
            raise KeyError("Edge dict must contain 'card1' and 'card2'")

        # Parse dates with error handling
        try:
            first_seen = datetime.fromisoformat(data["first_seen"])
        except (KeyError, ValueError) as e:
            raise ValueError(f"Invalid first_seen date: {e}") from e

        try:
            last_seen = datetime.fromisoformat(data["last_seen"])
        except (KeyError, ValueError) as e:
            raise ValueError(f"Invalid last_seen date: {e}") from e

        return cls(
            card1=data["card1"],
            card2=data["card2"],
            game=data.get("game"),
            weight=data.get("weight", 1),
            first_seen=first_seen,
            last_seen=last_seen,
            deck_sources=data.get("deck_sources", []),
            metadata=data.get("metadata") or {},
            source_type=data.get("source_type", "co_occurrence"),
            monthly_counts=cls._validate_monthly_counts(data.get("monthly_counts") or {}),
            format_periods=cls._validate_format_periods(data.get("format_periods") or {}),
            temporal_stats=data.get("temporal_stats"),
        )

    @staticmethod
    def _validate_monthly_counts(value: Any) -> dict[str, int]:
        """
        Validate and normalize monthly_counts structure.

        Args:
            value: Value to validate (may be dict, str, bytes, or None)

        Returns:
            Valid dict[str, int] mapping "YYYY-MM" -> count
        """
        if not value:
            return {}

        if isinstance(value, dict):
            # Validate structure and types
            result = {}
            for month_key, count in value.items():
                if isinstance(month_key, str) and isinstance(count, (int, float)):
                    # Validate month format
                    try:
                        datetime.strptime(month_key, "%Y-%m")
                        result[month_key] = int(count)
                    except (ValueError, TypeError):
                        continue  # Skip invalid month keys
            return result

        return {}

    @staticmethod
    def _validate_format_periods(value: Any) -> dict[str, dict[str, int]]:
        """
        Validate and normalize format_periods structure.

        Args:
            value: Value to validate (may be dict, str, bytes, or None)

        Returns:
            Valid dict[str, dict[str, int]] mapping period_key -> {month_key -> count}
        """
        if not value:
            return {}

        if isinstance(value, dict):
            result = {}
            for period_key, period_data in value.items():
                if isinstance(period_key, str) and isinstance(period_data, dict):
                    # Validate period data structure
                    validated_period = {}
                    for month_key, count in period_data.items():
                        if isinstance(month_key, str) and isinstance(count, (int, float)):
                            try:
                                datetime.strptime(month_key, "%Y-%m")
                                validated_period[month_key] = int(count)
                            except (ValueError, TypeError):
                                continue
                    if validated_period:
                        result[period_key] = validated_period
            return result

        return {}


@dataclass
class CardSet:
    """Hyperedge: a set of 3+ cards that frequently co-occur in decks.

    Represents card packages, combos, engine cores, and archetype staples
    that go beyond pairwise co-occurrence.
    """

    cards: frozenset[str]
    game: str | None = None
    support: int = 0  # Number of decks containing all cards
    total_decks: int = 0  # Total deck count at extraction time
    lift: float = 0.0  # Lift = P(all) / prod(P(each))
    archetype: str | None = None
    metadata: dict[str, Any] | None = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    @property
    def size(self) -> int:
        return len(self.cards)

    @property
    def support_pct(self) -> float:
        if self.total_decks == 0:
            return 0.0
        return self.support / self.total_decks * 100

    def to_dict(self) -> dict[str, Any]:
        result = {
            "cards": sorted(self.cards),
            "size": self.size,
            "support": self.support,
            "total_decks": self.total_decks,
            "lift": round(self.lift, 3),
            "support_pct": round(self.support_pct, 1),
        }
        if self.game:
            result["game"] = self.game
        if self.archetype:
            result["archetype"] = self.archetype
        if self.metadata:
            result["metadata"] = self.metadata
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CardSet:
        return cls(
            cards=frozenset(data["cards"]),
            game=data.get("game"),
            support=data.get("support", 0),
            total_decks=data.get("total_decks", 0),
            lift=data.get("lift", 0.0),
            archetype=data.get("archetype"),
            metadata=data.get("metadata"),
        )

    @classmethod
    def load_from_jsonl(cls, path: str | Path) -> list[CardSet]:
        """Load card sets from extract_card_sets.py output."""
        results = []
        with open(path) as f:
            for line in f:
                data = json.loads(line)
                if data.get("_meta"):
                    continue
                results.append(cls.from_dict(data))
        return results


class IncrementalCardGraph:
    """
    Continuously updated graph database for card co-occurrence.

    Maintains nodes (cards) and edges (co-occurrences) with temporal tracking.
    Supports incremental updates from new deck data.
    """

    @staticmethod
    def _safe_json_load(value: Any, default: Any = None) -> Any:
        """
        Safely load JSON from string/bytes, with fallback to default.

        Args:
            value: Value to parse (may be str, bytes, dict, list, or None)
            default: Default value if parsing fails or value is None

        Returns:
            Parsed JSON object or default
        """
        if value is None:
            return default

        if isinstance(value, (dict, list)):
            return value

        if isinstance(value, (str, bytes)):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return default

        return default

    def __init__(
        self,
        graph_path: Path | str | None = None,
        card_attributes: dict[str, dict[str, Any]] | None = None,
        use_sqlite: bool = False,  # Default False for backward compatibility
    ):
        """
        Initialize graph database.

        Args:
            graph_path: Path to save/load graph state (JSON or SQLite)
            card_attributes: Optional dict mapping card name -> attributes dict
                           (power, toughness, oracle_text, keywords, etc.)
            use_sqlite: Use SQLite for storage (default: False for backward compatibility)
        """
        self.graph_path = Path(graph_path) if graph_path else None
        self.use_sqlite = use_sqlite
        self.nodes: dict[str, CardNode] = {}
        self.edges: dict[tuple[str, str, str], Edge] = {}
        self.last_update: datetime | None = None
        self.total_decks_processed: int = 0
        self._card_attributes: dict[str, dict[str, Any]] = card_attributes or {}
        self._deck_metadata_cache: dict[str, dict[str, Any]] = {}  # Cache for deck metadata
        self._card_db = None  # Lazy-loaded card database
        self._db_conn: sqlite3.Connection | None = None  # SQLite connection

        # Initialize SQLite if enabled
        if self.use_sqlite and self.graph_path:
            self._init_sqlite()

        # Load existing graph
        if self.graph_path and self.graph_path.exists():
            # Auto-detect SQLite from .db extension
            if self.graph_path.suffix == ".db" or (
                self.use_sqlite and self.graph_path.suffix == ".db"
            ):
                self.load_sqlite(self.graph_path)
            else:
                self.load_json(self.graph_path)

        # Enrich nodes with card attributes if provided
        if self._card_attributes:
            self._enrich_nodes_with_attributes()

    def add_deck(
        self,
        deck: dict[str, Any],
        timestamp: datetime | None = None,
        deck_id: str | None = None,
    ) -> None:
        """
        Add a deck to the graph incrementally.

        Args:
            deck: Deck dict with 'cards' or 'partitions' structure
            timestamp: When this deck was collected (default: now)
            deck_id: Optional deck identifier for tracking
        """
        if timestamp is None:
            timestamp = datetime.now()

        # Extract cards with metadata (name, count, partition, game)
        card_metadata = self._extract_cards_with_metadata(deck)
        if not card_metadata:
            return

        # Build card list with counts (for edge weighting)
        cards_with_counts: list[tuple[str, int, str, str | None]] = []
        for card_name, count, partition, game in card_metadata:
            # Expand by count (4-of = 4 entries)
            cards_with_counts.extend([(card_name, count, partition, game)] * count)

        # Add/update nodes
        for card_name, _count, _partition, game in card_metadata:
            if card_name not in self.nodes:
                # Load card attributes if available
                attrs = self._card_attributes.get(card_name, {})
                self.nodes[card_name] = CardNode(
                    name=card_name,
                    game=game,
                    first_seen=timestamp,
                    last_seen=timestamp,
                    total_decks=1,
                    attributes=attrs if attrs else None,
                )
            else:
                self.nodes[card_name].last_seen = timestamp
                self.nodes[card_name].total_decks += 1
                # Update game if not set
                if not self.nodes[card_name].game and game:
                    self.nodes[card_name].game = game
                # Update attributes if new ones available
                if card_name in self._card_attributes:
                    if self.nodes[card_name].attributes is None:
                        self.nodes[card_name].attributes = {}
                    self.nodes[card_name].attributes.update(self._card_attributes[card_name])

        # Add/update edges (all pairs within deck, weighted by counts)
        for i, (card1, count1, partition1, game1) in enumerate(cards_with_counts):
            for card2, count2, partition2, game2 in cards_with_counts[i + 1 :]:
                # Use sorted tuple for undirected edges
                sorted_pair = sorted([card1, card2])
                edge_key = (sorted_pair[0], sorted_pair[1], "co_occurrence")

                # Determine edge game (should be same for both cards)
                edge_game = game1 or game2

                # Weight by card counts (4-of + 4-of = higher weight)
                # Also weight by partition (mainboard > sideboard)
                weight = count1 * count2
                if partition1 == "Sideboard" or partition2 == "Sideboard":
                    weight = int(weight * 0.5)  # Sideboard co-occurrence is weaker

                # Extract format from deck metadata if available
                deck_format = None
                if deck_id and hasattr(self, "_deck_metadata_cache"):
                    deck_meta = self._deck_metadata_cache.get(deck_id, {})
                    deck_format = deck_meta.get("format")

                if edge_key not in self.edges:
                    edge = Edge(
                        card1=edge_key[0],
                        card2=edge_key[1],
                        game=edge_game,
                        weight=weight,
                        first_seen=timestamp,
                        last_seen=timestamp,
                        deck_sources=[deck_id] if deck_id else [],
                        metadata={
                            "partitions": [partition1, partition2],
                        },
                    )
                    # Initialize temporal distribution
                    edge.update_temporal(timestamp, deck_format)
                    self.edges[edge_key] = edge
                else:
                    self.edges[edge_key].weight += weight
                    self.edges[edge_key].last_seen = timestamp
                    if deck_id and deck_id not in self.edges[edge_key].deck_sources:
                        self.edges[edge_key].deck_sources.append(deck_id)
                    # Update game if not set
                    if not self.edges[edge_key].game and edge_game:
                        self.edges[edge_key].game = edge_game
                    # Update temporal distribution
                    self.edges[edge_key].update_temporal(timestamp, deck_format)

                # Store deck metadata in edge if provided
                if deck_id and hasattr(self, "_deck_metadata_cache"):
                    deck_meta = self._deck_metadata_cache.get(deck_id, {})
                    if deck_meta:
                        edge = self.edges[edge_key]
                        # Aggregate metadata (format, placement, etc.)
                        if "format" in deck_meta:
                            formats = edge.metadata.get("formats", set())
                            if isinstance(formats, list):
                                formats = set(formats)
                            formats.add(deck_meta["format"])
                            edge.metadata["formats"] = list(formats)
                        if "placement" in deck_meta:
                            placements = edge.metadata.get("placements", [])
                            placements.append(deck_meta["placement"])
                            edge.metadata["placements"] = placements
                        if "event_date" in deck_meta:
                            dates = edge.metadata.get("event_dates", [])
                            dates.append(deck_meta["event_date"])
                            edge.metadata["event_dates"] = dates
                        if "archetype" in deck_meta:
                            archetypes = edge.metadata.get("archetypes", set())
                            if isinstance(archetypes, list):
                                archetypes = set(archetypes)
                            archetypes.add(deck_meta["archetype"])
                            edge.metadata["archetypes"] = list(archetypes)

        self.last_update = timestamp
        self.total_decks_processed += 1

    def _enrich_nodes_with_attributes(self) -> None:
        """Enrich existing nodes with card attributes."""
        for card_name, attrs in self._card_attributes.items():
            if card_name in self.nodes:
                if self.nodes[card_name].attributes is None:
                    self.nodes[card_name].attributes = {}
                self.nodes[card_name].attributes.update(attrs)

    def set_deck_metadata(self, deck_id: str, metadata: dict[str, Any]) -> None:
        """Set metadata for a deck (format, placement, event_date, etc.)."""
        self._deck_metadata_cache[deck_id] = metadata

    def _get_card_database(self):
        """Lazy-load card database for game detection."""
        if self._card_db is None and HAS_CARD_DB:
            with suppress(Exception):
                self._card_db = get_card_database()
        return self._card_db

    def _detect_game(self, card_name: str, deck: dict[str, Any] | None = None) -> str | None:
        """Detect game for a card."""
        # Try deck metadata first
        if deck:
            game = deck.get("game")
            if game:
                game_map = {"magic": "MTG", "pokemon": "PKM", "yugioh": "YGO"}
                return game_map.get(game.lower())

        # Try card database
        card_db = self._get_card_database()
        if card_db:
            try:
                game = card_db.get_game(card_name)
                if game:
                    game_map = {"magic": "MTG", "pokemon": "PKM", "yugioh": "YGO"}
                    return game_map.get(game.lower())
            except Exception:
                pass

        return None

    def _extract_cards_with_metadata(
        self, deck: dict[str, Any]
    ) -> list[tuple[str, int, str, str | None]]:
        """
        Extract cards with count, partition, and game information.

        Returns:
            List of (card_name, count, partition, game) tuples
        """
        cards = []
        deck_game = None

        # Detect deck game
        game = deck.get("game")
        if game:
            game_map = {"magic": "MTG", "pokemon": "PKM", "yugioh": "YGO"}
            deck_game = game_map.get(game.lower())

        # Try partitions format first
        if "partitions" in deck:
            for partition in deck.get("partitions", []):
                partition_name = partition.get("name", "Main")
                for card_entry in partition.get("cards", []):
                    if isinstance(card_entry, dict):
                        card_name = card_entry.get("name")
                        count = card_entry.get("count", 1)
                    else:
                        card_name = card_entry
                        count = 1

                    if card_name:
                        # Detect game if not already known
                        card_game = deck_game or self._detect_game(card_name, deck)
                        cards.append((str(card_name), count, partition_name, card_game))

        # Try cards format
        elif "cards" in deck:
            for card_entry in deck["cards"]:
                if isinstance(card_entry, dict):
                    card_name = card_entry.get("name")
                    count = card_entry.get("count", 1)
                    partition = card_entry.get("partition", "Main")
                else:
                    card_name = card_entry
                    count = 1
                    partition = "Main"

                if card_name:
                    card_game = deck_game or self._detect_game(card_name, deck)
                    cards.append((str(card_name), count, partition, card_game))

        return cards

    def _extract_cards(self, deck: dict[str, Any]) -> list[str]:
        """Extract card names from deck structure (backward compatibility)."""
        card_metadata = self._extract_cards_with_metadata(deck)
        # Return unique card names (for backward compatibility)
        seen = set()
        unique_cards = []
        for card_name, _, _, _ in card_metadata:
            if card_name not in seen:
                seen.add(card_name)
                unique_cards.append(card_name)
        return unique_cards

    def get_neighbors(
        self,
        card: str,
        min_weight: int = 1,
        game: str | None = None,
    ) -> list[str]:
        """
        Get neighbors of a card (cards it co-occurs with).

        Args:
            card: Card name
            min_weight: Minimum edge weight to include
            game: Filter by game ("MTG", "PKM", "YGO")

        Returns:
            List of neighbor card names
        """
        neighbors = []
        for key, edge in self.edges.items():
            if edge.weight < min_weight:
                continue
            if game and edge.game != game:
                continue
            if edge.card1 == card:
                neighbors.append(edge.card2)
            elif edge.card2 == card:
                neighbors.append(edge.card1)
        return neighbors

    def get_new_cards_since(self, since: datetime) -> list[str]:
        """Get cards added since a timestamp."""
        return [node.name for node in self.nodes.values() if node.first_seen >= since]

    def export_parquet(self, output_dir: Path | str) -> dict[str, Path]:
        """
        Export graph to Parquet format for training.

        Args:
            output_dir: Directory to save Parquet files

        Returns:
            Dict mapping "nodes" and "edges" to file paths
        """
        if not HAS_PARQUET:
            raise ImportError("pyarrow is required for Parquet export")
        if not HAS_PANDAS:
            raise ImportError("pandas is required for Parquet export")

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Export nodes
        nodes_data = []
        for node in self.nodes.values():
            nodes_data.append(
                {
                    "name": node.name,
                    "game": node.game or "",
                    "first_seen": node.first_seen.isoformat(),
                    "last_seen": node.last_seen.isoformat(),
                    "total_decks": node.total_decks,
                    "attributes": json.dumps(node.attributes) if node.attributes else "",
                }
            )

        nodes_df = pd.DataFrame(nodes_data)
        nodes_path = output_dir / "nodes.parquet"
        nodes_df.to_parquet(nodes_path, compression="snappy")

        # Export edges
        edges_data = []
        for edge in self.edges.values():
            edges_data.append(
                {
                    "card1": edge.card1,
                    "card2": edge.card2,
                    "game": edge.game or "",
                    "weight": edge.weight,
                    "first_seen": edge.first_seen.isoformat(),
                    "last_seen": edge.last_seen.isoformat(),
                    "deck_sources": json.dumps(edge.deck_sources),
                    "metadata": json.dumps(edge.metadata),
                }
            )

        edges_df = pd.DataFrame(edges_data)
        edges_path = output_dir / "edges.parquet"
        edges_df.to_parquet(edges_path, compression="snappy")

        return {"nodes": nodes_path, "edges": edges_path}

    def export_edgelist(
        self,
        output_path: Path | str,
        min_weight: int = 2,
        format: str = "edgelist",
        game: str | None = None,
    ) -> Path:
        """
        Export graph to edgelist format for GNN training.

        Args:
            output_path: Output file path
            min_weight: Minimum edge weight to include
            format: "edgelist" (space-separated) or "tsv" (tab-separated)

        Returns:
            Path to exported file
        """
        output_path = Path(output_path)
        sep = "\t" if format == "tsv" else " "

        with open(output_path, "w") as f:
            # Write header
            if format == "tsv":
                f.write("card1\tcard2\tweight\n")

            # Write edges
            for key, edge in sorted(self.edges.items()):
                if edge.weight >= min_weight:
                    if game and edge.game != game:
                        continue
                    f.write(f"{edge.card1}{sep}{edge.card2}{sep}{edge.weight}\n")

        return output_path

    def compute_lift(
        self,
        game: str | None = None,
        min_weight: int = 2,
    ) -> dict[tuple[str, str], float]:
        """
        Compute Lift for all edges: Lift(A,B) = P(A,B) / [P(A) * P(B)].

        Lift > 1 means the cards co-occur more than expected by chance.
        This controls for card popularity (Sol Ring gets ~1.0 against everything).
        Based on EDHREC's methodology.

        Args:
            game: Filter by game ("MTG", "PKM", "YGO")
            min_weight: Minimum raw co-occurrence to include

        Returns:
            Dict mapping (card1, card2) -> lift value
        """
        total_decks = max(self.total_decks_processed, 1)

        # P(card) = card.total_decks / total_decks
        card_prob = {name: node.total_decks / total_decks for name, node in self.nodes.items()}

        lift_values: dict[tuple[str, str], float] = {}
        for key, edge in self.edges.items():
            if edge.weight < min_weight:
                continue
            if game and edge.game != game:
                continue

            p_a = card_prob.get(edge.card1, 0)
            p_b = card_prob.get(edge.card2, 0)
            if p_a == 0 or p_b == 0:
                continue

            # P(A,B) approximated by co-occurrence count / total_decks
            p_ab = edge.weight / total_decks
            lift = p_ab / (p_a * p_b)
            lift_values[(edge.card1, edge.card2)] = lift

        return lift_values

    def export_edgelist_lift(
        self,
        output_path: Path | str,
        game: str | None = None,
        min_weight: int = 2,
        min_lift: float = 1.0,
    ) -> Path:
        """
        Export edgelist weighted by Lift instead of raw co-occurrence count.

        Lift-weighted edges control for card popularity: staples that appear
        in many decks get normalized down, while cards that specifically
        co-occur get amplified. Based on EDHREC's methodology.

        Args:
            output_path: Output file path
            game: Filter by game
            min_weight: Minimum raw co-occurrence to include
            min_lift: Minimum Lift value to include (default 1.0 = above chance)

        Returns:
            Path to exported file
        """
        output_path = Path(output_path)
        lift_values = self.compute_lift(game=game, min_weight=min_weight)

        with open(output_path, "w") as f:
            for (card1, card2), lift in sorted(lift_values.items()):
                if lift >= min_lift:
                    f.write(f"{card1}\t{card2}\t{lift:.4f}\n")

        return output_path

    def add_edge(
        self,
        card1: str,
        card2: str,
        weight: float,
        source_type: str,
        game: str | None = None,
    ) -> None:
        """
        Add or update a single edge with a specific source type.

        Used by build_unified_graph to ingest edges from various sources
        (PPMI, oracle text, annotations, propagated labels).

        Args:
            card1: First card name
            card2: Second card name
            weight: Edge weight
            source_type: Edge source (ppmi, oracle_text, annotation, propagated, etc.)
            game: Game identifier (MTG, PKM, YGO)
        """
        c1, c2 = sorted([card1, card2])
        key = (c1, c2, source_type)
        now = datetime.now()

        if key in self.edges:
            self.edges[key].weight = max(self.edges[key].weight, weight)
            self.edges[key].last_seen = now
        else:
            self.edges[key] = Edge(
                card1=c1,
                card2=c2,
                game=game,
                weight=weight,
                first_seen=now,
                last_seen=now,
                source_type=source_type,
            )

        # Ensure nodes exist
        for name in (c1, c2):
            if name not in self.nodes:
                self.nodes[name] = CardNode(name=name, game=game, first_seen=now, last_seen=now)

    def export_edgelist_filtered(
        self,
        output_path: Path | str,
        game: str | None = None,
        source_types: list[str] | None = None,
        weights: dict[str, float] | None = None,
        min_weight: float = 0.0,
    ) -> Path:
        """
        Export a merged edgelist filtered by source_type with per-source weight multipliers.

        Replaces the manual multi-file merge step. For each card pair, sums
        weight * multiplier across all matching source types.

        Args:
            output_path: Output .edg file path
            game: Filter edges by game (MTG, PKM, YGO)
            source_types: Which source types to include (default: all)
            weights: Per-source-type weight multipliers (default: 1.0 for all)
            min_weight: Minimum merged weight to include in output

        Returns:
            Path to exported file
        """
        output_path = Path(output_path)
        weights = weights or {}

        # Accumulate merged weights per card pair
        merged: dict[tuple[str, str], float] = {}
        source_counts: dict[str, int] = {}

        for key, edge in self.edges.items():
            if game and edge.game != game:
                continue
            if source_types and edge.source_type not in source_types:
                continue

            multiplier = weights.get(edge.source_type, 1.0)
            pair = (edge.card1, edge.card2)
            merged[pair] = merged.get(pair, 0.0) + edge.weight * multiplier
            source_counts[edge.source_type] = source_counts.get(edge.source_type, 0) + 1

        # Filter by min_weight and write
        output_path.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with open(output_path, "w") as f:
            for (c1, c2), w in sorted(merged.items()):
                if w >= min_weight:
                    f.write(f"{c1}\t{c2}\t{w:.4f}\n")
                    count += 1

        print(f"Exported {count:,} edges to {output_path}")
        for st, n in sorted(source_counts.items()):
            mult = weights.get(st, 1.0)
            print(f"  {st}: {n:,} edges (x{mult})")

        return output_path

    def get_node_image_urls(self, game: str | None = None) -> dict[str, str]:
        """Return card name -> image_url mapping for nodes that have image URLs."""
        result = {}
        for node in self.nodes.values():
            if game and node.game != game:
                continue
            if node.image_url:
                result[node.name] = node.image_url
        return result

    def edges_to_adj_dict(self, min_weight: int = 1) -> dict[str, set[str]]:
        """
        Convert graph edges to adjacency dictionary for Jaccard similarity.

        Args:
            min_weight: Minimum edge weight to include

        Returns:
            Dict mapping card -> set of neighbor cards
        """
        adj: dict[str, set[str]] = {}

        for key, edge in self.edges.items():
            if edge.weight < min_weight:
                continue

            if edge.card1 not in adj:
                adj[edge.card1] = set()
            if edge.card2 not in adj:
                adj[edge.card2] = set()

            adj[edge.card1].add(edge.card2)
            adj[edge.card2].add(edge.card1)

        return adj

    def query_edges(
        self,
        game: str | None = None,
        min_weight: int = 1,
        format: str | None = None,
        since: datetime | None = None,
    ) -> list[Edge]:
        """
        Query edges with filters.

        Args:
            game: Filter by game ("MTG", "PKM", "YGO")
            min_weight: Minimum edge weight
            format: Filter by format (checks metadata)
            since: Filter by last_seen >= since

        Returns:
            List of matching edges
        """
        results = []
        for edge in self.edges.values():
            if edge.weight < min_weight:
                continue
            if game and edge.game != game:
                continue
            if format and edge.metadata.get("formats") and format not in edge.metadata["formats"]:
                continue
            if since and edge.last_seen < since:
                continue
            results.append(edge)
        return results

    def get_statistics(self) -> dict[str, Any]:
        """Get graph statistics."""
        node_degrees = {}
        for key, edge in self.edges.items():
            node_degrees[edge.card1] = node_degrees.get(edge.card1, 0) + 1
            node_degrees[edge.card2] = node_degrees.get(edge.card2, 0) + 1

        degrees = list(node_degrees.values()) if node_degrees else [0]
        edge_weights = [edge.weight for edge in self.edges.values()]

        # Game distribution
        game_counts = {}
        for node in self.nodes.values():
            game = node.game or "Unknown"
            game_counts[game] = game_counts.get(game, 0) + 1

        return {
            "num_nodes": len(self.nodes),
            "num_edges": len(self.edges),
            "total_decks_processed": self.total_decks_processed,
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "avg_degree": float(np.mean(degrees)) if degrees else 0.0,
            "max_degree": max(degrees) if degrees else 0,
            "avg_edge_weight": float(np.mean(edge_weights)) if edge_weights else 0.0,
            "max_edge_weight": max(edge_weights) if edge_weights else 0,
            "game_distribution": game_counts,
        }

    def _init_sqlite(self) -> None:
        """Initialize SQLite database schema with error handling."""
        if not self.graph_path:
            return

        db_path = self.graph_path
        if db_path.suffix != ".db":
            db_path = db_path.with_suffix(".db")

        try:
            # Ensure parent directory exists
            db_path.parent.mkdir(parents=True, exist_ok=True)

            # Connect with timeout and error handling
            self._db_conn = sqlite3.connect(
                str(db_path),
                timeout=30.0,  # 30 second timeout for locked database
                check_same_thread=False,  # Allow use from multiple threads if needed
            )

            # Enable WAL mode for better concurrency
            self._db_conn.execute("PRAGMA journal_mode=WAL")

            # Create tables with error handling
            self._db_conn.execute("""
                CREATE TABLE IF NOT EXISTS nodes (
                    name TEXT PRIMARY KEY,
                    game TEXT,
                    first_seen TEXT,
                    last_seen TEXT,
                    total_decks INTEGER,
                    attributes TEXT,
                    oracle_text TEXT,
                    image_url TEXT
                )
            """)

            self._db_conn.execute("""
                CREATE TABLE IF NOT EXISTS edges (
                    card1 TEXT,
                    card2 TEXT,
                    game TEXT,
                    weight REAL,
                    first_seen TEXT,
                    last_seen TEXT,
                    deck_sources TEXT,
                    metadata TEXT,
                    monthly_counts TEXT,
                    format_periods TEXT,
                    source_type TEXT DEFAULT 'co_occurrence',
                    PRIMARY KEY (card1, card2, source_type)
                )
            """)

            # Migrate existing databases: add columns if they don't exist
            with suppress(sqlite3.OperationalError):
                self._db_conn.execute("ALTER TABLE edges ADD COLUMN monthly_counts TEXT")

            with suppress(sqlite3.OperationalError):
                self._db_conn.execute("ALTER TABLE edges ADD COLUMN format_periods TEXT")

            with suppress(sqlite3.OperationalError):
                self._db_conn.execute(
                    "ALTER TABLE edges ADD COLUMN source_type TEXT DEFAULT 'co_occurrence'"
                )

            with suppress(sqlite3.OperationalError):
                self._db_conn.execute("ALTER TABLE nodes ADD COLUMN oracle_text TEXT")

            with suppress(sqlite3.OperationalError):
                self._db_conn.execute("ALTER TABLE nodes ADD COLUMN image_url TEXT")

            # Indexes for common queries
            self._db_conn.execute("CREATE INDEX IF NOT EXISTS idx_nodes_game ON nodes(game)")
            self._db_conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_card1 ON edges(card1)")
            self._db_conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_card2 ON edges(card2)")
            self._db_conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_game ON edges(game)")
            self._db_conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_weight ON edges(weight)")
            self._db_conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_edges_source_type ON edges(source_type)"
            )

            self._db_conn.commit()

        except sqlite3.OperationalError as e:
            error_msg = str(e)
            if "database is locked" in error_msg.lower():
                raise RuntimeError(
                    f"Database {db_path} is locked. Another process may be using it. "
                    "Wait for it to finish or close other connections."
                ) from e
            elif "database disk image is malformed" in error_msg.lower():
                raise RuntimeError(
                    f"Database {db_path} appears corrupted. "
                    "Try restoring from backup or rebuilding the graph."
                ) from e
            else:
                raise RuntimeError(
                    f"Failed to initialize SQLite database at {db_path}: {error_msg}"
                ) from e
        except Exception as e:
            raise RuntimeError(
                f"Unexpected error initializing SQLite database at {db_path}: {e}"
            ) from e

    def save_sqlite(self, path: Path | str | None = None) -> None:
        """Save graph to SQLite database with error handling."""
        if not self._db_conn:
            self._init_sqlite()

        if not self._db_conn:
            raise ValueError("SQLite connection not available")

        try:
            # Clear existing data
            self._db_conn.execute("DELETE FROM nodes")
            self._db_conn.execute("DELETE FROM edges")

            # Insert nodes in batch for better performance
            nodes_data = [
                (
                    node.name,
                    node.game,
                    node.first_seen.isoformat(),
                    node.last_seen.isoformat(),
                    node.total_decks,
                    json.dumps(node.attributes) if node.attributes else None,
                    node.oracle_text,
                    node.image_url,
                )
                for node in self.nodes.values()
            ]
            self._db_conn.executemany(
                """
                INSERT INTO nodes (name, game, first_seen, last_seen, total_decks, attributes, oracle_text, image_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                nodes_data,
            )

            # Insert edges in batch
            edges_data = [
                (
                    edge.card1,
                    edge.card2,
                    edge.game,
                    edge.weight,
                    edge.first_seen.isoformat(),
                    edge.last_seen.isoformat(),
                    json.dumps(edge.deck_sources),
                    json.dumps(edge.metadata),
                    json.dumps(edge.monthly_counts) if edge.monthly_counts else None,
                    json.dumps(edge.format_periods) if edge.format_periods else None,
                    edge.source_type,
                )
                for edge in self.edges.values()
            ]
            self._db_conn.executemany(
                """
                INSERT INTO edges (card1, card2, game, weight, first_seen, last_seen, deck_sources, metadata, monthly_counts, format_periods, source_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                edges_data,
            )

            self._db_conn.commit()

        except sqlite3.OperationalError as e:
            error_msg = str(e)
            if "database is locked" in error_msg.lower():
                raise RuntimeError(
                    "Database is locked during save. Another process may be using it. "
                    "Wait for it to finish or close other connections."
                ) from e
            elif "database disk image is malformed" in error_msg.lower():
                raise RuntimeError(
                    "Database appears corrupted during save. "
                    "Try restoring from backup or rebuilding the graph."
                ) from e
            else:
                raise RuntimeError(f"Failed to save to SQLite database: {error_msg}") from e
        except Exception as e:
            raise RuntimeError(f"Unexpected error saving to SQLite database: {e}") from e

    def load_sqlite(self, path: Path | str) -> None:
        """Load graph from SQLite database with error handling."""
        path = Path(path)
        if path.suffix != ".db":
            path = path.with_suffix(".db")

        if not path.exists():
            return

        try:
            self._db_conn = sqlite3.connect(str(path), timeout=30.0, check_same_thread=False)

            # Load nodes (handle old schema without oracle_text/image_url)
            try:
                node_cursor = self._db_conn.execute(
                    "SELECT name, game, first_seen, last_seen, total_decks, attributes, oracle_text, image_url FROM nodes"
                )
            except sqlite3.OperationalError:
                node_cursor = self._db_conn.execute(
                    "SELECT name, game, first_seen, last_seen, total_decks, attributes FROM nodes"
                )
            for row in node_cursor:
                name, game, first_seen, last_seen, total_decks, attributes = row[:6]
                oracle_text = row[6] if len(row) > 6 else None
                image_url = row[7] if len(row) > 7 else None
                self.nodes[name] = CardNode(
                    name=name,
                    game=game,
                    first_seen=datetime.fromisoformat(first_seen),
                    last_seen=datetime.fromisoformat(last_seen),
                    total_decks=total_decks,
                    attributes=json.loads(attributes) if attributes else None,
                    oracle_text=oracle_text,
                    image_url=image_url,
                )

            # OPTIMIZATION: Load edges in batches with fetchall() for better performance
            # Handle missing columns for backward compatibility
            try:
                cursor = self._db_conn.execute(
                    "SELECT card1, card2, game, weight, first_seen, last_seen, deck_sources, metadata, monthly_counts, format_periods, source_type FROM edges"
                )
            except sqlite3.OperationalError:
                try:
                    cursor = self._db_conn.execute(
                        "SELECT card1, card2, game, weight, first_seen, last_seen, deck_sources, metadata, monthly_counts, format_periods FROM edges"
                    )
                except sqlite3.OperationalError:
                    # Fallback for old schema without temporal columns
                    cursor = self._db_conn.execute(
                        "SELECT card1, card2, game, weight, first_seen, last_seen, deck_sources, metadata FROM edges"
                    )

            rows = cursor.fetchall()

            # Process in chunks to reduce memory pressure for very large graphs
            chunk_size = 100000
            for i in range(0, len(rows), chunk_size):
                chunk = rows[i : i + chunk_size]
                for row in chunk:
                    card1, card2 = row[0], row[1]
                    game = row[2]
                    weight = row[3]
                    first_seen = row[4]
                    last_seen = row[5]
                    deck_sources = row[6]
                    metadata = row[7]
                    monthly_counts = row[8] if len(row) > 8 else None
                    format_periods = row[9] if len(row) > 9 else None
                    source_type = row[10] if len(row) > 10 else "co_occurrence"

                    # Edge key includes source_type to allow multiple edge types per pair
                    edge_key = (min(card1, card2), max(card1, card2), source_type)
                    self.edges[edge_key] = Edge(
                        card1=card1,
                        card2=card2,
                        game=game,
                        weight=float(weight) if isinstance(weight, (int, float)) else weight,
                        first_seen=datetime.fromisoformat(first_seen)
                        if isinstance(first_seen, str)
                        else first_seen,
                        last_seen=datetime.fromisoformat(last_seen)
                        if isinstance(last_seen, str)
                        else last_seen,
                        deck_sources=self._safe_json_load(deck_sources, default=[]),
                        metadata=self._safe_json_load(metadata, default={}),
                        source_type=source_type or "co_occurrence",
                        monthly_counts=Edge._validate_monthly_counts(
                            IncrementalCardGraph._safe_json_load(monthly_counts, default={})
                        ),
                        format_periods=Edge._validate_format_periods(
                            IncrementalCardGraph._safe_json_load(format_periods, default={})
                        ),
                    )

            self.last_update = datetime.now()

        except sqlite3.OperationalError as e:
            error_msg = str(e)
            if "database is locked" in error_msg.lower():
                raise RuntimeError(
                    f"Database {path} is locked. Another process may be using it. "
                    "Wait for it to finish or close other connections."
                ) from e
            elif "database disk image is malformed" in error_msg.lower():
                raise RuntimeError(
                    f"Database {path} appears corrupted. "
                    "Try restoring from backup or rebuilding the graph."
                ) from e
            elif "no such table" in error_msg.lower():
                # Database exists but schema is wrong - try to initialize
                self._init_sqlite()
                return
            else:
                raise RuntimeError(
                    f"Failed to load from SQLite database {path}: {error_msg}"
                ) from e
        except Exception as e:
            raise RuntimeError(f"Unexpected error loading from SQLite database {path}: {e}") from e

    def save_json(self, path: Path | str | None = None) -> None:
        """Save graph to JSON (backward compatibility)."""
        path = Path(path) if path else self.graph_path
        if not path:
            raise ValueError("No path provided for saving")

        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "nodes": {name: node.to_dict() for name, node in self.nodes.items()},
            "edges": {
                f"{edge.card1}|||{edge.card2}|||{edge.source_type}": edge.to_dict()
                for edge in self.edges.values()
            },
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "total_decks_processed": self.total_decks_processed,
        }

        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def load_json(self, path: Path | str) -> None:
        """Load graph from JSON (backward compatibility)."""
        path = Path(path)
        if not path.exists():
            return

        with open(path) as f:
            data = json.load(f)

        # Load nodes
        self.nodes = {
            name: CardNode.from_dict(node_data) for name, node_data in data.get("nodes", {}).items()
        }

        # Load edges (handle old 2-part keys and new 3-part keys)
        self.edges = {}
        for edge_key, edge_data in data.get("edges", {}).items():
            parts = edge_key.split("|||")
            card1, card2 = parts[0], parts[1]
            source_type = (
                parts[2] if len(parts) > 2 else edge_data.get("source_type", "co_occurrence")
            )
            edge = Edge.from_dict(edge_data)
            self.edges[(card1, card2, source_type)] = edge

        self.last_update = (
            datetime.fromisoformat(data["last_update"]) if data.get("last_update") else None
        )
        self.total_decks_processed = data.get("total_decks_processed", 0)

    def save(self, path: Path | str | None = None) -> None:
        """Save graph (uses SQLite if enabled, otherwise JSON)."""
        if self.use_sqlite:
            self.save_sqlite(path)
        else:
            self.save_json(path)

    def load(self, path: Path | str) -> None:
        """Load graph (auto-detects format)."""
        path = Path(path)
        if path.suffix == ".db" or (self.use_sqlite and path.with_suffix(".db").exists()):
            self.load_sqlite(path)
        else:
            self.load_json(path)

    def rebuild_from_decks(self, decks: list[dict[str, Any]]) -> None:
        """
        Rebuild graph from scratch from deck list.

        Useful for monthly full rebuilds.
        """
        self.nodes = {}
        self.edges = {}
        self.total_decks_processed = 0

        for deck in decks:
            deck_id = deck.get("deck_id") or deck.get("id")
            timestamp = datetime.fromisoformat(deck.get("timestamp", datetime.now().isoformat()))
            self.add_deck(deck, timestamp=timestamp, deck_id=deck_id)
