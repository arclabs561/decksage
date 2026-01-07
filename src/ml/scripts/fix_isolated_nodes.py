#!/usr/bin/env python3
"""
Fix isolated nodes (nodes with no edges).

Isolated nodes may indicate:
- Cards that were added but never co-occurred with others
- Data quality issues
- Cards that should be removed or investigated
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()


def analyze_isolated_nodes(graph_db: Path) -> dict[str, any]:
    """Analyze isolated nodes."""
    logger.info("Analyzing isolated nodes...")
    
    conn = sqlite3.connect(str(graph_db))
    conn.row_factory = sqlite3.Row
    
    isolated = conn.execute("""
        SELECT 
            n.name,
            n.game,
            n.total_decks,
            n.first_seen,
            n.last_seen
        FROM nodes n
        LEFT JOIN edges e1 ON e1.card1 = n.name
        LEFT JOIN edges e2 ON e2.card2 = n.name
        WHERE e1.card1 IS NULL AND e2.card2 IS NULL
        ORDER BY n.total_decks DESC
    """).fetchall()
    
    logger.info(f"Found {len(isolated)} isolated nodes")
    
    # Categorize
    by_game = {}
    for node in isolated:
        game = node["game"] or "Unknown"
        if game not in by_game:
            by_game[game] = []
        by_game[game].append(node)
    
    logger.info("Isolated nodes by game:")
    for game, nodes in sorted(by_game.items()):
        logger.info(f"  {game}: {len(nodes)} nodes")
        if nodes:
            logger.info(f"    Top 5 by deck count:")
            for node in nodes[:5]:
                logger.info(f"      {node['name']}: {node['total_decks']} decks")
    
    conn.close()
    
    return {
        "total_isolated": len(isolated),
        "by_game": {k: len(v) for k, v in by_game.items()},
        "high_frequency": [n["name"] for n in isolated if n["total_decks"] >= 50],
    }


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Analyze isolated nodes")
    parser.add_argument(
        "--graph-db",
        type=Path,
        default=PATHS.incremental_graph_db,
        help="Path to graph database",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("Isolated Nodes Analysis")
    logger.info("=" * 70)
    
    results = analyze_isolated_nodes(args.graph_db)
    
    logger.info(f"\n✓ Analysis complete: {results['total_isolated']} isolated nodes found")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

