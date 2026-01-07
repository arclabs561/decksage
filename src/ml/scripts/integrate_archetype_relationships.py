#!/usr/bin/env python3
"""
Integrate archetype relationships into the graph.

Cards that appear together in the same archetype get stronger edges.
This creates archetype-based subgraphs that GNNs can learn from.
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


def integrate_archetype_relationships(
    graph: IncrementalCardGraph,
    game: str | None = None,
    archetype_edge_weight: int = 2,
    min_archetype_decks: int = 3,
) -> dict[str, int]:
    """
    Integrate archetype relationships into the graph.
    
    Cards that appear together in the same archetype get stronger edges.
    
    Args:
        graph: IncrementalCardGraph instance
        game: Filter by game
        archetype_edge_weight: Weight to add for archetype co-occurrence
        min_archetype_decks: Minimum decks in archetype to consider
    
    Returns:
        Statistics dict
    """
    logger.info("Integrating archetype relationships into graph...")
    
    # Ensure graph is loaded
    if graph.use_sqlite and not graph.nodes:
        logger.info("Loading graph into memory...")
        graph.load_sqlite(graph.graph_path)
    
    stats = {
        "archetypes_processed": 0,
        "archetype_edges_updated": 0,
        "archetype_edges_created": 0,
        "cards_in_archetypes": 0,
    }
    
    # Get archetype co-occurrence from edge metadata
    archetype_pairs: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    archetype_cards: dict[str, set[str]] = defaultdict(set)
    
    for edge_key, edge in graph.edges.items():
        # Filter by game
        if game and edge.game != game:
            continue
        
        # Get archetypes from metadata - handle both list and single value
        if edge.metadata:
            archetypes = edge.metadata.get("archetypes") or edge.metadata.get("archetype")
            if archetypes:
                if isinstance(archetypes, list):
                    for archetype in archetypes:
                        if archetype and isinstance(archetype, str):
                            archetype_pairs[edge_key][archetype] += edge.weight
                            archetype_cards[archetype].add(edge.card1)
                            archetype_cards[archetype].add(edge.card2)
                elif isinstance(archetypes, str):
                    archetype_pairs[edge_key][archetypes] += edge.weight
                    archetype_cards[archetypes].add(edge.card1)
                    archetype_cards[archetypes].add(edge.card2)
    
    # Filter to archetypes with enough decks
    significant_archetypes = {
        arch: cards
        for arch, cards in archetype_cards.items()
        if len(cards) >= min_archetype_decks
    }
    
    logger.info(f"Found {len(significant_archetypes)} significant archetypes")
    
    # For each archetype, strengthen edges between cards in that archetype
    for archetype, cards in significant_archetypes.items():
        card_list = list(cards)
        
        # Create edges for all pairs in the archetype
        for i, card1 in enumerate(card_list):
            for card2 in card_list[i + 1:]:
                edge_key = tuple(sorted([card1, card2]))
                
                # Get or create edge
                if edge_key in graph.edges:
                    edge = graph.edges[edge_key]
                    is_new = False
                else:
                    # Create new edge
                    from ..data.incremental_graph import Edge
                    from datetime import datetime
                    
                    edge = Edge(
                        card1=edge_key[0],
                        card2=edge_key[1],
                        game=game or graph.nodes[card1].game if card1 in graph.nodes else None,
                        weight=0,
                    )
                    graph.edges[edge_key] = edge
                    is_new = True
                
                # Add archetype weight
                edge.weight += archetype_edge_weight
                
                # Add archetype metadata
                if edge.metadata is None:
                    edge.metadata = {}
                
                if "archetype_co_occurrences" not in edge.metadata:
                    edge.metadata["archetype_co_occurrences"] = []
                
                # Check if this archetype already recorded
                existing_archetypes = {
                    a.get("archetype") for a in edge.metadata["archetype_co_occurrences"]
                }
                if archetype not in existing_archetypes:
                    edge.metadata["archetype_co_occurrences"].append({
                        "archetype": archetype,
                        "weight": archetype_edge_weight,
                    })
                    
                    if is_new:
                        stats["archetype_edges_created"] += 1
                    else:
                        stats["archetype_edges_updated"] += 1
        
        stats["cards_in_archetypes"] += len(cards)
        stats["archetypes_processed"] += 1
    
    logger.info(f"Processed {stats['archetypes_processed']} archetypes")
    logger.info(f"Created {stats['archetype_edges_created']} new archetype edges")
    logger.info(f"Updated {stats['archetype_edges_updated']} existing edges with archetype info")
    logger.info(f"Total cards in archetypes: {stats['cards_in_archetypes']}")
    
    return stats


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Integrate archetype relationships")
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
        "--archetype-weight",
        type=int,
        default=2,
        help="Weight to add for archetype co-occurrence",
    )
    parser.add_argument(
        "--min-decks",
        type=int,
        default=3,
        help="Minimum decks in archetype to consider",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("Integrate Archetype Relationships")
    logger.info("=" * 70)
    
    # Load graph
    graph = IncrementalCardGraph(
        graph_path=args.graph_db,
        use_sqlite=True,
    )
    
    # Integrate
    results = integrate_archetype_relationships(
        graph,
        game=args.game,
        archetype_edge_weight=args.archetype_weight,
        min_archetype_decks=args.min_decks,
    )
    
    # Save graph
    logger.info("Saving graph...")
    graph.save_sqlite(args.graph_db)
    
    logger.info(f"\n✓ Results: {results}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

