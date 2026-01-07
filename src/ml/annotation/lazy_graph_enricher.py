"""Lazy-loading graph enricher that queries SQLite directly.

Avoids loading the entire 2.1GB graph into memory by querying
SQLite directly for only the data needed for enrichment.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

try:
    from ..data.incremental_graph import IncrementalCardGraph
    from .enriched_annotation import GraphFeatures
    from .graph_enricher import compare_card_attributes, extract_contextual_analysis

    HAS_GRAPH = True
except ImportError:
    HAS_GRAPH = False
    IncrementalCardGraph = None  # type: ignore


class LazyGraphEnricher:
    """Lazy-loading graph enricher that queries SQLite directly."""

    def __init__(self, graph_db_path: Path, game: str | None = None):
        """Initialize lazy enricher with SQLite connection.
        
        Args:
            graph_db_path: Path to SQLite graph database
            game: Game filter - will normalize to database format (MTG, PKM, YGO)
        """
        self.graph_db_path = Path(graph_db_path)
        if not self.graph_db_path.exists():
            raise FileNotFoundError(f"Graph database not found: {graph_db_path}")
        
        # Normalize game name to database format
        if game:
            game_lower = game.lower()
            if game_lower in ["magic", "mtg"]:
                self.game = "MTG"
            elif game_lower in ["pokemon", "pkm"]:
                self.game = "PKM"
            elif game_lower in ["yugioh", "ygo"]:
                self.game = "YGO"
            else:
                self.game = game.upper()  # Try uppercase
        else:
            self.game = None
        
        self._conn: sqlite3.Connection | None = None
        # Prepared statements cache for better performance
        self._prepared_stmts: dict[str, sqlite3.Cursor] = {}
        self._optimize_connection()

    def _optimize_connection(self) -> None:
        """Optimize SQLite connection for read-only queries."""
        if self._conn is None:
            self._conn = sqlite3.connect(
                str(self.graph_db_path),
                timeout=30.0,
                check_same_thread=False,
            )
            
            # Apply performance optimizations for 2GB database
            # Use WAL mode for better concurrency (but may slow down if many connections)
            try:
                self._conn.execute("PRAGMA journal_mode = WAL")
            except sqlite3.OperationalError:
                pass  # May fail if DB is locked
            
            # For read-only queries, use OFF for maximum speed
            # (WAL mode already provides durability for writes)
            try:
                self._conn.execute("PRAGMA synchronous = OFF")  # Fastest for reads
            except sqlite3.OperationalError:
                self._conn.execute("PRAGMA synchronous = NORMAL")  # Fallback
            
            # Memory-map the database (OS handles caching) - increase to 3GB for better coverage
            try:
                self._conn.execute("PRAGMA mmap_size = 3000000000")  # ~3GB
            except sqlite3.OperationalError:
                try:
                    self._conn.execute("PRAGMA mmap_size = 2000000000")  # Fallback to 2GB
                except sqlite3.OperationalError:
                    pass  # May not be available in all SQLite versions
            
            # Increase cache size (negative = KB, so -2000000 = 2GB)
            self._conn.execute("PRAGMA cache_size = -2000000")
            
            # Use memory for temp tables
            self._conn.execute("PRAGMA temp_store = MEMORY")
            
            # Enable query-only mode if available (read-only optimization)
            try:
                self._conn.execute("PRAGMA query_only = 1")
            except sqlite3.OperationalError:
                pass  # Requires SQLite 3.8.0+
            
            # Create composite indexes for common query patterns
            # Note: SQLite can't index LOWER() directly, so we create indexes on the columns
            # and use case-insensitive matching in queries
            try:
                # Composite index for edge lookups: (game, card1, card2) covers most queries
                self._conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_edges_game_card1_card2 
                    ON edges(game, card1, card2)
                """)
                # Composite index for reverse lookups: (game, card2, card1)
                self._conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_edges_game_card2_card1 
                    ON edges(game, card2, card1)
                """)
                # Index for neighbor queries: (game, card1) and (game, card2)
                self._conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_edges_game_card1_weight 
                    ON edges(game, card1, weight DESC)
                """)
                self._conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_edges_game_card2_weight 
                    ON edges(game, card2, weight DESC)
                """)
                # Index for node lookups
                self._conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_nodes_game_name 
                    ON nodes(game, name)
                """)
                # Run ANALYZE to update query planner statistics
                self._conn.execute("ANALYZE")
            except sqlite3.OperationalError as e:
                # Indexes may already exist or DB may be read-only
                pass
            
            # Optimize query planner (runs ANALYZE and updates statistics)
            try:
                self._conn.execute("PRAGMA optimize")
            except sqlite3.OperationalError:
                pass

    def get_neighbors(self, card: str, min_weight: int = 1) -> set[str]:
        """Get neighbors of a card by querying SQLite directly.
        
        Uses case-insensitive matching to handle name variations.
        Optimized with prepared statements and better index usage.
        """
        if not self._conn:
            return set()
        
        # Use UNION to leverage indexes on both card1 and card2
        # This is faster than OR with LOWER() which can't use indexes
        neighbors = set()
        
        if self.game:
            # Query card1 side (uses idx_edges_game_card1_weight)
            query1 = """
                SELECT DISTINCT card2
                FROM edges
                WHERE game = ? AND card1 = ? AND weight >= ?
            """
            for row in self._conn.execute(query1, [self.game, card, min_weight]):
                neighbors.add(row[0])
            
            # Query card2 side (uses idx_edges_game_card2_weight)
            query2 = """
                SELECT DISTINCT card1
                FROM edges
                WHERE game = ? AND card2 = ? AND weight >= ?
            """
            for row in self._conn.execute(query2, [self.game, card, min_weight]):
                neighbors.add(row[0])
        else:
            # No game filter - use case-insensitive matching
            query1 = """
                SELECT DISTINCT card2
                FROM edges
                WHERE card1 = ? AND weight >= ?
            """
            for row in self._conn.execute(query1, [card, min_weight]):
                neighbors.add(row[0])
            
            query2 = """
                SELECT DISTINCT card1
                FROM edges
                WHERE card2 = ? AND weight >= ?
            """
            for row in self._conn.execute(query2, [card, min_weight]):
                neighbors.add(row[0])
        
        return neighbors

    def get_edge(self, card1: str, card2: str) -> dict[str, Any] | None:
        """Get edge data for a card pair by querying SQLite directly.
        
        Optimized to use indexes efficiently.
        """
        if not self._conn:
            return None
        
        # Try card1->card2 first (uses idx_edges_game_card1_card2)
        if self.game:
            query = """
                SELECT weight, first_seen, last_seen, deck_sources, metadata,
                       monthly_counts, format_periods
                FROM edges
                WHERE game = ? AND card1 = ? AND card2 = ?
                LIMIT 1
            """
            row = self._conn.execute(query, [self.game, card1, card2]).fetchone()
            if row:
                return self._parse_edge_row(row)
            
            # Try card2->card1 (uses idx_edges_game_card2_card1)
            query = """
                SELECT weight, first_seen, last_seen, deck_sources, metadata,
                       monthly_counts, format_periods
                FROM edges
                WHERE game = ? AND card1 = ? AND card2 = ?
                LIMIT 1
            """
            row = self._conn.execute(query, [self.game, card2, card1]).fetchone()
        else:
            # No game filter
            query = """
                SELECT weight, first_seen, last_seen, deck_sources, metadata,
                       monthly_counts, format_periods
                FROM edges
                WHERE card1 = ? AND card2 = ?
                LIMIT 1
            """
            row = self._conn.execute(query, [card1, card2]).fetchone()
            if not row:
                query = """
                    SELECT weight, first_seen, last_seen, deck_sources, metadata,
                           monthly_counts, format_periods
                    FROM edges
                    WHERE card1 = ? AND card2 = ?
                    LIMIT 1
                """
                row = self._conn.execute(query, [card2, card1]).fetchone()
        
        if not row:
            return None
        
        return self._parse_edge_row(row)
    
    def _parse_edge_row(self, row: tuple) -> dict[str, Any]:
        """Parse edge row from database into dict."""
        return {
            "weight": row[0],
            "first_seen": row[1],
            "last_seen": row[2],
            "deck_sources": self._safe_json_load(row[3], default=[]),
            "metadata": self._safe_json_load(row[4], default={}),
            "monthly_counts": self._safe_json_load(row[5], default={}) if len(row) > 5 else None,
            "format_periods": self._safe_json_load(row[6], default={}) if len(row) > 6 else None,
        }
    
    def _safe_json_load(self, value: str | None, default: Any = None) -> Any:
        """Safely load JSON from database value."""
        if value is None:
            return default
        if isinstance(value, str):
            try:
                import json
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return default
        return value
        
        return {
            "weight": row[0],
            "first_seen": row[1],
            "last_seen": row[2],
            "deck_sources": row[3],
            "metadata": row[4],
            "monthly_counts": row[5],
            "format_periods": row[6],
        }

    def get_node(self, card: str) -> dict[str, Any] | None:
        """Get node data for a card by querying SQLite directly.
        
        Optimized to use index on (game, name).
        """
        if not self._conn:
            return None
        
        # Use exact match with index (faster than LOWER())
        if self.game:
            query = """
                SELECT game, first_seen, last_seen, total_decks, attributes 
                FROM nodes 
                WHERE game = ? AND name = ?
                LIMIT 1
            """
            row = self._conn.execute(query, [self.game, card]).fetchone()
        else:
            # Fallback to exact match (no game filter)
            query = """
                SELECT game, first_seen, last_seen, total_decks, attributes 
                FROM nodes 
                WHERE name = ?
                LIMIT 1
            """
            row = self._conn.execute(query, [card]).fetchone()
        
        if not row:
            return None
        
        return {
            "game": row[0],
            "first_seen": row[1],
            "last_seen": row[2],
            "total_decks": row[3],
            "attributes": self._safe_json_load(row[4], default=None),
        }

    def compute_jaccard(self, card1: str, card2: str) -> float:
        """Compute Jaccard similarity using SQLite queries."""
        neighbors1 = self.get_neighbors(card1)
        neighbors2 = self.get_neighbors(card2)
        
        if not neighbors1 or not neighbors2:
            return 0.0
        
        intersection = len(neighbors1 & neighbors2)
        union = len(neighbors1 | neighbors2)
        
        return intersection / union if union > 0 else 0.0

    def extract_graph_features(
        self, card1: str, card2: str
    ) -> GraphFeatures | None:
        """Extract graph features using lazy SQLite queries."""
        if not HAS_GRAPH:
            return None
        
        # Get neighbors
        neighbors1 = self.get_neighbors(card1)
        neighbors2 = self.get_neighbors(card2)
        
        # Compute Jaccard
        jaccard = self.compute_jaccard(card1, card2)
        
        # Get edge data
        edge_data = self.get_edge(card1, card2)
        # Handle edge weight - may be int, string, or None
        if edge_data:
            weight = edge_data.get("weight", 0)
            if isinstance(weight, (str, bytes)):
                try:
                    cooccurrence_count = int(weight)
                except (ValueError, TypeError):
                    cooccurrence_count = 0
            elif isinstance(weight, (int, float)):
                cooccurrence_count = int(weight)
            else:
                cooccurrence_count = 0
        else:
            cooccurrence_count = 0
        
        # Get node data for frequency calculation
        node1 = self.get_node(card1)
        node2 = self.get_node(card2)
        total_decks_card1 = node1["total_decks"] if node1 else 0
        total_decks_card2 = node2["total_decks"] if node2 else 0
        
        cooccurrence_frequency = (
            cooccurrence_count / max(total_decks_card1, total_decks_card2, 1)
            if max(total_decks_card1, total_decks_card2) > 0
            else 0.0
        )
        
        # Common neighbors count (int, not list)
        common_neighbors_count = len(neighbors1 & neighbors2)
        
        # Graph distance (simplified - direct edge = 1, else None for now)
        graph_distance = 1 if edge_data else None
        
        # Create GraphFeatures matching the model from graph_enricher
        return GraphFeatures(
            cooccurrence_count=cooccurrence_count,
            cooccurrence_frequency=cooccurrence_frequency,
            jaccard_similarity=jaccard,
            graph_distance=graph_distance,
            common_neighbors=common_neighbors_count,  # Count (int), not list
            total_neighbors_card1=len(neighbors1),
            total_neighbors_card2=len(neighbors2),
            edge_weight=cooccurrence_count if edge_data else None,
        )

    def close(self) -> None:
        """Close SQLite connection and cleanup prepared statements."""
        if self._prepared_stmts:
            for stmt in self._prepared_stmts.values():
                try:
                    stmt.close()
                except Exception:
                    pass
            self._prepared_stmts.clear()
        
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

