#!/usr/bin/env python3
"""
Integrate format legality relationships into the graph.

Cards that are legal in the same formats get edges.
This helps GNNs understand format-specific relationships.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from ..data.incremental_graph import IncrementalCardGraph
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()


def integrate_format_legality(
    graph: IncrementalCardGraph,
    game: str | None = None,
    format_edge_weight: int = 1,
) -> dict[str, int]:
    """
    Integrate format legality relationships into the graph.
    
    Cards that appear together in the same formats get edges.
    
    Args:
        graph: IncrementalCardGraph instance
        game: Filter by game
        format_edge_weight: Weight to add for shared format legality
    
    Returns:
        Statistics dict
    """
    logger.info("Integrating format legality relationships...")
    
    # Ensure graph is loaded
    if graph.use_sqlite and not graph.nodes:
        logger.info("Loading graph into memory...")
        graph.load_sqlite(graph.graph_path)
    
    stats = {
        "formats_processed": 0,
        "format_edges_updated": 0,
        "format_edges_created": 0,
    }
    
    # Get format co-occurrence from edge metadata
    cards_by_format: dict[str, set[str]] = defaultdict(set)
    
    for edge_key, edge in graph.edges.items():
        # Filter by game
        if game and edge.game != game:
            continue
        
        # Get formats from metadata - handle both list and single value
        if edge.metadata:
            formats = edge.metadata.get("formats") or edge.metadata.get("format")
            if formats:
                if isinstance(formats, list):
                    for format_name in formats:
                        if format_name and isinstance(format_name, str):
                            cards_by_format[format_name].add(edge.card1)
                            cards_by_format[format_name].add(edge.card2)
                elif isinstance(formats, str):
                    cards_by_format[formats].add(edge.card1)
                    cards_by_format[formats].add(edge.card2)
    
    logger.info(f"Found {len(cards_by_format)} formats")
    
    # For each format, create edges between cards in that format
    from ..data.incremental_graph import Edge
    
    for format_name, cards in cards_by_format.items():
        if len(cards) < 2:
            continue
        
        card_list = list(cards)
        
        # Create edges for all pairs in the format
        for i, card1 in enumerate(card_list):
            for card2 in card_list[i + 1:]:
                edge_key = tuple(sorted([card1, card2]))
                
                # Get or create edge
                if edge_key in graph.edges:
                    edge = graph.edges[edge_key]
                    is_new = False
                else:
                    edge = Edge(
                        card1=edge_key[0],
                        card2=edge_key[1],
                        game=game or graph.nodes[card1].game if card1 in graph.nodes else None,
                        weight=0,
                    )
                    graph.edges[edge_key] = edge
                    is_new = True
                
                # Add format weight
                edge.weight += format_edge_weight
                
                # Add format metadata
                if edge.metadata is None:
                    edge.metadata = {}
                
                if "format_legality" not in edge.metadata:
                    edge.metadata["format_legality"] = []
                
                # Check if this format already recorded
                existing_formats = {
                    f.get("format") for f in edge.metadata["format_legality"]
                }
                if format_name not in existing_formats:
                    edge.metadata["format_legality"].append({
                        "format": format_name,
                        "weight": format_edge_weight,
                    })
                    
                    if is_new:
                        stats["format_edges_created"] += 1
                    else:
                        stats["format_edges_updated"] += 1
        
        stats["formats_processed"] += 1
    
    logger.info(f"Processed {stats['formats_processed']} formats")
    logger.info(f"Created {stats['format_edges_created']} new format edges")
    logger.info(f"Updated {stats['format_edges_updated']} existing edges with format info")
    
    return stats


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Integrate format legality")
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
        "--format-weight",
        type=int,
        default=1,
        help="Weight to add for shared format legality",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("Integrate Format Legality")
    logger.info("=" * 70)
    
    # Load graph
    graph = IncrementalCardGraph(
        graph_path=args.graph_db,
        use_sqlite=True,
    )
    
    # Integrate
    results = integrate_format_legality(
        graph,
        game=args.game,
        format_edge_weight=args.format_weight,
    )
    
    # Save graph
    logger.info("Saving graph...")
    graph.save_sqlite(args.graph_db)
    
    logger.info(f"\n✓ Results: {results}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

