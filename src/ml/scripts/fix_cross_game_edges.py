#!/usr/bin/env python3
"""
Fix cross-game edges by setting game = NULL for legitimate cross-game connections.

When two nodes are from different games, the edge connecting them should have
game = NULL (not try to match one game or the other).
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()


def fix_cross_game_edges(graph_db: Path) -> dict[str, int]:
    """Fix cross-game edges by setting game = NULL."""
    logger.info("Fixing cross-game edges...")
    
    conn = sqlite3.connect(str(graph_db))
    conn.row_factory = sqlite3.Row
    
    # Find edges where nodes are from different games
    cross_game = conn.execute("""
        SELECT COUNT(*) 
        FROM edges e
        JOIN nodes n1 ON e.card1 = n1.name
        JOIN nodes n2 ON e.card2 = n2.name
        WHERE n1.game IS NOT NULL 
          AND n2.game IS NOT NULL
          AND n1.game != n2.game
          AND e.game IS NOT NULL
    """).fetchone()[0]
    
    logger.info(f"Found {cross_game:,} edges connecting nodes from different games")
    
    if cross_game == 0:
        conn.close()
        return {"fixed": 0}
    
    # Set game = NULL for legitimate cross-game edges
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE edges
        SET game = NULL
        WHERE EXISTS (
            SELECT 1
            FROM nodes n1, nodes n2
            WHERE n1.name = edges.card1
              AND n2.name = edges.card2
              AND n1.game IS NOT NULL
              AND n2.game IS NOT NULL
              AND n1.game != n2.game
        )
        AND edges.game IS NOT NULL
    """)
    
    fixed = cursor.rowcount
    conn.commit()
    conn.close()
    
    logger.info(f"Fixed {fixed:,} cross-game edges (set game = NULL)")
    
    return {"fixed": fixed}


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Fix cross-game edges")
    parser.add_argument(
        "--graph-db",
        type=Path,
        default=PATHS.incremental_graph_db,
        help="Path to graph database",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("Fix Cross-Game Edges")
    logger.info("=" * 70)
    
    results = fix_cross_game_edges(args.graph_db)
    
    logger.info(f"\n✓ Fixed {results['fixed']:,} cross-game edges")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

