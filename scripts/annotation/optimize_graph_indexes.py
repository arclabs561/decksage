#!/usr/bin/env python3
"""Optimize graph database indexes for enrichment queries.

Creates composite indexes that match our query patterns for maximum performance.
"""

import sqlite3
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ml.utils.paths import PATHS


def optimize_indexes(db_path: Path) -> None:
    """Create optimized indexes for enrichment queries."""
    if not db_path.exists():
        print(f"Error: Database not found: {db_path}")
        return
    
    print(f"Optimizing indexes in: {db_path}")
    print("=" * 80)
    
    conn = sqlite3.connect(str(db_path))
    
    try:
        # Check existing indexes
        print("\nExisting indexes:")
        for row in conn.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"):
            print(f"  {row[0]}")
        
        print("\nCreating optimized composite indexes...")
        
        # Composite indexes for edge lookups (most common query pattern)
        indexes = [
            # For get_edge: (game, card1, card2) covers most queries
            ("idx_edges_game_card1_card2", """
                CREATE INDEX IF NOT EXISTS idx_edges_game_card1_card2 
                ON edges(game, card1, card2)
            """),
            # For reverse lookups: (game, card2, card1)
            ("idx_edges_game_card2_card1", """
                CREATE INDEX IF NOT EXISTS idx_edges_game_card2_card1 
                ON edges(game, card2, card1)
            """),
            # For neighbor queries: (game, card1, weight DESC) - weight DESC for filtering
            ("idx_edges_game_card1_weight", """
                CREATE INDEX IF NOT EXISTS idx_edges_game_card1_weight 
                ON edges(game, card1, weight DESC)
            """),
            # For neighbor queries: (game, card2, weight DESC)
            ("idx_edges_game_card2_weight", """
                CREATE INDEX IF NOT EXISTS idx_edges_game_card2_weight 
                ON edges(game, card2, weight DESC)
            """),
            # For node lookups: (game, name)
            ("idx_nodes_game_name", """
                CREATE INDEX IF NOT EXISTS idx_nodes_game_name 
                ON nodes(game, name)
            """),
        ]
        
        for name, sql in indexes:
            try:
                conn.execute(sql)
                print(f"  ✓ Created: {name}")
            except sqlite3.OperationalError as e:
                print(f"  ⚠️  {name}: {e}")
        
        conn.commit()
        
        # Run ANALYZE to update query planner statistics
        print("\nRunning ANALYZE to update query planner statistics...")
        try:
            conn.execute("ANALYZE")
            print("  ✓ ANALYZE complete")
        except sqlite3.OperationalError as e:
            print(f"  ⚠️  ANALYZE failed: {e}")
        
        # Show final index count
        index_count = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
        ).fetchone()[0]
        print(f"\nTotal indexes: {index_count}")
        
        # Show index sizes
        print("\nIndex sizes:")
        for row in conn.execute("""
            SELECT name, 
                   (SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name=idx.name) as size
            FROM sqlite_master idx
            WHERE idx.type='index' AND idx.name NOT LIKE 'sqlite_%'
            ORDER BY idx.name
        """):
            print(f"  {row[0]}")
        
    finally:
        conn.close()
    
    print("\n" + "=" * 80)
    print("✅ Index optimization complete")
    print("=" * 80)


if __name__ == "__main__":
    db_path = PATHS.incremental_graph_db
    if not db_path.exists():
        print(f"Error: Graph database not found: {db_path}")
        sys.exit(1)
    
    optimize_indexes(db_path)


