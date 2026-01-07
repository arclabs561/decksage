#!/usr/bin/env python3
"""
Integrate pack co-occurrence information into the incremental graph.

This adds pack-based edges and metadata to enhance GNN training:
- Cards in the same pack naturally co-occur (strong signal)
- Pack release dates provide temporal information
- Pack types (starter vs booster) have different patterns
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..data.incremental_graph import IncrementalCardGraph
from ..data.pack_database import PackDatabase
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()


def integrate_packs_into_graph(
    graph: IncrementalCardGraph,
    pack_db: PackDatabase,
    game: str | None = None,
    add_pack_edges: bool = True,
    add_pack_metadata: bool = True,
    pack_edge_weight: int = 1,
) -> dict[str, int]:
    """
    Integrate pack information into the graph.
    
    Args:
        graph: IncrementalCardGraph instance
        pack_db: PackDatabase instance
        game: Filter by game (e.g., "MTG", "PKM", "YGO")
        add_pack_edges: Add pack co-occurrence as edges
        add_pack_metadata: Add pack info to node/edge metadata
        pack_edge_weight: Weight to add for pack co-occurrence edges
    
    Returns:
        Statistics dict
    """
    logger.info("Integrating pack information into graph...")
    
    stats = {
        "packs_processed": 0,
        "pack_edges_added": 0,
        "pack_edges_updated": 0,
        "nodes_enriched": 0,
        "edges_enriched": 0,
        "cards_not_in_graph": 0,
    }
    
    # Ensure graph is loaded into memory (works for both SQLite and JSON)
    # SQLite graphs load into self.nodes and self.edges dicts
    if graph.use_sqlite:
        if not graph.nodes:
            logger.info("Loading graph into memory from SQLite...")
            graph.load_sqlite(graph.graph_path)
        else:
            logger.debug("Graph already loaded in memory")
    
    # Get all packs (filtered by game if specified)
    import sqlite3
    db_conn = sqlite3.connect(str(pack_db.db_path))
    db_conn.row_factory = sqlite3.Row
    cursor = db_conn.cursor()
    
    if game:
        cursor.execute("""
            SELECT pack_id, pack_name, pack_code, pack_type, release_date
            FROM packs
            WHERE game = ?
            ORDER BY release_date DESC
        """, (game,))
    else:
        cursor.execute("""
            SELECT pack_id, pack_name, pack_code, pack_type, release_date
            FROM packs
            ORDER BY release_date DESC
        """)
    
    packs = cursor.fetchall()
    logger.info(f"Found {len(packs)} packs to process")
    
    # Parse release dates for temporal tracking
    from datetime import datetime
    
    for pack_row in packs:
        pack_id = pack_row["pack_id"]
        pack_name = pack_row["pack_name"]
        pack_code = pack_row["pack_code"]
        pack_type = pack_row["pack_type"]
        release_date_str = pack_row["release_date"]
        
        # Parse release date
        release_date = None
        if release_date_str:
            try:
                release_date = datetime.fromisoformat(release_date_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                try:
                    release_date = datetime.strptime(release_date_str, "%Y-%m-%d")
                except (ValueError, AttributeError):
                    logger.debug(f"Could not parse release date: {release_date_str}")
        
        # Get cards in this pack
        pack_cards = pack_db.get_pack_cards(pack_id)
        
        if len(pack_cards) < 2:
            continue  # Need at least 2 cards for co-occurrence
        
        card_names = [card["card_name"] for card in pack_cards]
        
        # Filter to cards that exist in graph
        cards_in_graph = [name for name in card_names if name in graph.nodes]
        if len(cards_in_graph) < 2:
            stats["cards_not_in_graph"] += len(card_names) - len(cards_in_graph)
            continue
        
        # Add pack co-occurrence edges
        if add_pack_edges:
            # Create edges for all pairs in the pack
            for i, card1 in enumerate(cards_in_graph):
                for card2 in cards_in_graph[i + 1:]:
                    edge_key = tuple(sorted([card1, card2]))
                    
                    # Get or create edge
                    if edge_key in graph.edges:
                        edge = graph.edges[edge_key]
                        is_new_edge = False
                    else:
                        # Create new edge
                        from ..data.incremental_graph import Edge
                        
                        edge = Edge(
                            card1=edge_key[0],
                            card2=edge_key[1],
                            game=game or graph.nodes[card1].game or graph.nodes[card2].game,
                            weight=0,
                            first_seen=release_date or datetime.now(),
                            last_seen=release_date or datetime.now(),
                        )
                        graph.edges[edge_key] = edge
                        is_new_edge = True
                    
                    # Add pack weight (pack co-occurrence is strong signal)
                    edge.weight += pack_edge_weight
                    
                    # Add pack metadata to edge
                    if add_pack_metadata:
                        if edge.metadata is None:
                            edge.metadata = {}
                        
                        if "pack_co_occurrences" not in edge.metadata:
                            edge.metadata["pack_co_occurrences"] = []
                        
                        # Check if this pack already recorded (avoid duplicates)
                        existing_pack_ids = {
                            p.get("pack_id") for p in edge.metadata["pack_co_occurrences"]
                        }
                        if pack_id not in existing_pack_ids:
                            edge.metadata["pack_co_occurrences"].append({
                                "pack_id": pack_id,
                                "pack_name": pack_name,
                                "pack_code": pack_code,
                                "pack_type": pack_type,
                                "release_date": release_date_str,
                            })
                            
                            if is_new_edge:
                                stats["pack_edges_added"] += 1
                            else:
                                stats["pack_edges_updated"] += 1
                            stats["edges_enriched"] += 1
                    
                    # Update temporal tracking if release date available
                    if release_date:
                        edge.update_temporal(release_date, format=None)
                        if release_date < edge.first_seen:
                            edge.first_seen = release_date
                        if release_date > edge.last_seen:
                            edge.last_seen = release_date
        
        # Add pack info to node attributes
        if add_pack_metadata:
            for card_name in cards_in_graph:
                if card_name in graph.nodes:
                    node = graph.nodes[card_name]
                    if node.attributes is None:
                        node.attributes = {}
                    
                    if "packs" not in node.attributes:
                        node.attributes["packs"] = []
                    
                    # Check if this pack already recorded
                    existing_pack_ids = {
                        p.get("pack_id") for p in node.attributes["packs"]
                    }
                    if pack_id not in existing_pack_ids:
                        node.attributes["packs"].append({
                            "pack_id": pack_id,
                            "pack_name": pack_name,
                            "pack_code": pack_code,
                            "pack_type": pack_type,
                            "release_date": release_date_str,
                        })
                        stats["nodes_enriched"] += 1
        
        stats["packs_processed"] += 1
        
        # Progress logging with batch commit for SQLite
        if stats["packs_processed"] % 10 == 0:
            logger.info(
                f"  Processed {stats['packs_processed']}/{len(packs)} packs... "
                f"(edges: +{stats['pack_edges_added']}, updated: {stats['pack_edges_updated']})"
            )
            
            # For very large graphs, could commit periodically
            # But since we're working in memory, we'll save once at the end
    
    db_conn.close()
    
    logger.info(f"Processed {stats['packs_processed']} packs")
    logger.info(f"Added {stats['pack_edges_added']} new pack co-occurrence edges")
    logger.info(f"Updated {stats['pack_edges_updated']} existing edges with pack info")
    logger.info(f"Enriched {stats['nodes_enriched']} nodes with pack info")
    logger.info(f"Enriched {stats['edges_enriched']} edges with pack metadata")
    if stats["cards_not_in_graph"] > 0:
        logger.warning(f"{stats['cards_not_in_graph']} pack cards not found in graph")
    
    return stats


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Integrate pack data into graph")
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
        "--no-pack-edges",
        action="store_true",
        help="Don't add pack co-occurrence as edges",
    )
    parser.add_argument(
        "--no-pack-metadata",
        action="store_true",
        help="Don't add pack info to node/edge metadata",
    )
    parser.add_argument(
        "--pack-edge-weight",
        type=int,
        default=1,
        help="Weight to add for pack co-occurrence edges (default: 1)",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("Integrate Pack Data into Graph")
    logger.info("=" * 70)
    
    # Load graph
    logger.info(f"Loading graph from {args.graph_db}...")
    graph = IncrementalCardGraph(
        graph_path=args.graph_db,
        use_sqlite=True,
    )
    
    # Load pack database
    logger.info(f"Loading pack database from {args.pack_db}...")
    pack_db = PackDatabase(args.pack_db)
    
    # Integrate
    results = integrate_packs_into_graph(
        graph,
        pack_db,
        game=args.game,
        add_pack_edges=not args.no_pack_edges,
        add_pack_metadata=not args.no_pack_metadata,
        pack_edge_weight=args.pack_edge_weight,
    )
    
    # Save graph
    logger.info("Saving graph...")
    graph.save_sqlite(args.graph_db)
    
    logger.info(f"\n✓ Results: {results}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

