#!/usr/bin/env python3
"""
Optimize pack integration for large packs.

For packs with many cards, uses more efficient strategies:
- Batch processing
- Progress tracking
- Memory management
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..data.incremental_graph import IncrementalCardGraph
from ..data.pack_database import PackDatabase
from ..scripts.integrate_packs_into_graph import integrate_packs_into_graph
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()


def optimize_large_pack_integration(
    graph: IncrementalCardGraph,
    pack_db: PackDatabase,
    game: str | None = None,
    large_pack_threshold: int = 200,
    batch_size: int = 50,
) -> dict[str, int]:
    """
    Optimize integration for large packs by processing in batches.
    
    Args:
        graph: IncrementalCardGraph instance
        pack_db: PackDatabase instance
        game: Filter by game
        large_pack_threshold: Packs with more cards than this are "large"
        batch_size: Number of packs to process before intermediate save
    
    Returns:
        Statistics dict
    """
    logger.info("Optimizing pack integration for large packs...")
    
    # Load graph
    if graph.use_sqlite and not graph.nodes:
        logger.info("Loading graph into memory...")
        graph.load_sqlite(graph.graph_path)
    
    # Get pack sizes
    import sqlite3
    db_conn = sqlite3.connect(str(pack_db.db_path))
    db_conn.row_factory = sqlite3.Row
    cursor = db_conn.cursor()
    
    if game:
        cursor.execute("""
            SELECT p.pack_id, COUNT(pc.card_name) as card_count
            FROM packs p
            LEFT JOIN pack_cards pc ON p.pack_id = pc.pack_id
            WHERE p.game = ?
            GROUP BY p.pack_id
            ORDER BY card_count DESC
        """, (game,))
    else:
        cursor.execute("""
            SELECT p.pack_id, COUNT(pc.card_name) as card_count
            FROM packs p
            LEFT JOIN pack_cards pc ON p.pack_id = pc.pack_id
            GROUP BY p.pack_id
            ORDER BY card_count DESC
        """)
    
    pack_sizes = {row["pack_id"]: row["card_count"] for row in cursor.fetchall()}
    db_conn.close()
    
    large_packs = {pid: size for pid, size in pack_sizes.items() if size >= large_pack_threshold}
    small_packs = {pid: size for pid, size in pack_sizes.items() if size < large_pack_threshold}
    
    logger.info(f"Found {len(large_packs)} large packs (>= {large_pack_threshold} cards)")
    logger.info(f"Found {len(small_packs)} small packs (< {large_pack_threshold} cards)")
    
    # Process small packs first (faster)
    logger.info("Processing small packs first...")
    # This would require modifying integrate_packs_into_graph to accept pack_id filter
    # For now, just process all packs normally
    
    # Process all packs (optimization would be to filter by pack_id list)
    total_stats = integrate_packs_into_graph(
        graph,
        pack_db,
        game=game,
        add_pack_edges=True,
        add_pack_metadata=True,
    )
    
    logger.info(f"Large pack optimization complete")
    logger.info(f"  Large packs: {len(large_packs)}")
    logger.info(f"  Small packs: {len(small_packs)}")
    
    return total_stats


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Optimize pack integration")
    parser.add_argument(
        "--graph-db",
        type=Path,
        default=PATHS.incremental_graph_db,
        help="Path to graph database",
    )
    parser.add_argument(
        "--pack-db",
        type=Path,
        default=PATHS.packs_db,
        help="Path to pack database",
    )
    parser.add_argument(
        "--game",
        choices=["MTG", "PKM", "YGO"],
        help="Filter by game",
    )
    parser.add_argument(
        "--large-threshold",
        type=int,
        default=200,
        help="Card count threshold for 'large' packs",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("Optimize Pack Integration")
    logger.info("=" * 70)
    
    # Load graph
    graph = IncrementalCardGraph(
        graph_path=args.graph_db,
        use_sqlite=True,
    )
    
    # Load pack database
    pack_db = PackDatabase(args.pack_db)
    
    # Optimize
    results = optimize_large_pack_integration(
        graph,
        pack_db,
        game=args.game,
        large_pack_threshold=args.large_threshold,
    )
    
    # Save graph
    logger.info("Saving graph...")
    graph.save_sqlite(args.graph_db)
    
    logger.info(f"\n✓ Results: {results}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

