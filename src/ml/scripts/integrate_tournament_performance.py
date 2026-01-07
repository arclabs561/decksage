#!/usr/bin/env python3
"""
Integrate tournament performance data into the graph.

Cards that appear together in winning decks get stronger edges.
This creates performance-weighted edges that GNNs can learn from.
"""

from __future__ import annotations

import argparse
import sqlite3
from collections import defaultdict
from pathlib import Path

from ..data.incremental_graph import IncrementalCardGraph
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()


def integrate_tournament_performance(
    graph: IncrementalCardGraph,
    game: str | None = None,
    placement_weight_multiplier: float = 1.5,
    min_placement: int = 8,
) -> dict[str, int]:
    """
    Integrate tournament performance data into the graph.
    
    Cards that appear together in top-performing decks get stronger edges.
    
    Args:
        graph: IncrementalCardGraph instance
        game: Filter by game
        placement_weight_multiplier: Multiplier for edges in top decks (1.5 = 50% boost)
        min_placement: Only consider decks with placement <= this (top 8, top 4, etc.)
    
    Returns:
        Statistics dict
    """
    logger.info("Integrating tournament performance data...")
    
    # Ensure graph is loaded
    if graph.use_sqlite and not graph.nodes:
        logger.info("Loading graph into memory...")
        graph.load_sqlite(graph.graph_path)
    
    stats = {
        "top_decks_processed": 0,
        "performance_edges_updated": 0,
        "total_weight_added": 0,
    }
    
    # Query database for edges with placement metadata
    if not graph.use_sqlite:
        logger.warning("Tournament performance integration requires SQLite")
        return stats
    
    conn = sqlite3.connect(str(graph.graph_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get edges with placement data
    if game:
        cursor.execute("""
            SELECT card1, card2, metadata
            FROM edges
            WHERE game = ? AND metadata IS NOT NULL
        """, (game,))
    else:
        cursor.execute("""
            SELECT card1, card2, metadata
            FROM edges
            WHERE metadata IS NOT NULL
        """)
    
    edges_with_metadata = cursor.fetchall()
    conn.close()
    
    # Process edges with placement data
    import json
    
    for row in edges_with_metadata:
        card1 = row["card1"]
        card2 = row["card2"]
        metadata_str = row["metadata"]
        
        try:
            metadata = json.loads(metadata_str) if isinstance(metadata_str, str) else metadata_str
        except (json.JSONDecodeError, TypeError):
            continue
        
        # Check for placement data - handle both list and single value
        placements = metadata.get("placements", [])
        if not placements:
            # Try single placement value
            placement = metadata.get("placement")
            if placement and isinstance(placement, (int, str)):
                try:
                    placement_int = int(placement)
                    placements = [placement_int]
                except (ValueError, TypeError):
                    pass
        
        if not placements:
            continue
        
        # Filter to top placements
        top_placements = []
        for p in placements:
            if isinstance(p, (int, str)):
                try:
                    p_int = int(p)
                    if p_int <= min_placement:
                        top_placements.append(p_int)
                except (ValueError, TypeError):
                    continue
        
        if not top_placements:
            continue
        
        edge_key = tuple(sorted([card1, card2]))
        if edge_key not in graph.edges:
            continue
        
        edge = graph.edges[edge_key]
        
        # Calculate performance weight boost
        # Better placement (lower number) = higher boost
        # 1st place gets max boost, 8th place gets minimal boost
        performance_boost = 0
        for placement in top_placements:
            if placement == 1:
                boost = placement_weight_multiplier * 2.0  # 2x for 1st place
            elif placement <= 4:
                boost = placement_weight_multiplier * 1.5  # 1.5x for top 4
            else:
                boost = placement_weight_multiplier * 1.2  # 1.2x for top 8
        
            performance_boost += int(boost)
        
        # Add performance weight
        edge.weight += performance_boost
        
        # Add performance metadata
        if edge.metadata is None:
            edge.metadata = {}
        
        edge.metadata["tournament_performance"] = {
            "top_placements": top_placements,
            "performance_boost": performance_boost,
            "min_placement": min(top_placements),
        }
        
        stats["performance_edges_updated"] += 1
        stats["total_weight_added"] += performance_boost
        stats["top_decks_processed"] += len(top_placements)
    
    logger.info(f"Processed {stats['top_decks_processed']} top deck placements")
    logger.info(f"Updated {stats['performance_edges_updated']} edges with performance data")
    logger.info(f"Total weight added: {stats['total_weight_added']}")
    
    return stats


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Integrate tournament performance")
    parser.add_argument(
        "--graph-db",
        type=Path,
        default=PATHS.incremental_graph_db,
        help="Path to graph database",
    )
    parser.add_argument(
        "--game",
        choices=["MTG", "PKM", "YGO"],
        help="Filter by game",
    )
    parser.add_argument(
        "--placement-multiplier",
        type=float,
        default=1.5,
        help="Weight multiplier for top placements",
    )
    parser.add_argument(
        "--min-placement",
        type=int,
        default=8,
        help="Minimum placement to consider (top 8, top 4, etc.)",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("Integrate Tournament Performance")
    logger.info("=" * 70)
    
    # Load graph
    graph = IncrementalCardGraph(
        graph_path=args.graph_db,
        use_sqlite=True,
    )
    
    # Integrate
    results = integrate_tournament_performance(
        graph,
        game=args.game,
        placement_weight_multiplier=args.placement_multiplier,
        min_placement=args.min_placement,
    )
    
    # Save graph
    logger.info("Saving graph...")
    graph.save_sqlite(args.graph_db)
    
    logger.info(f"\n✓ Results: {results}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

