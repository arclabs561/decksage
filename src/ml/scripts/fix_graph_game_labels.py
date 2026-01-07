#!/usr/bin/env python3
"""
Fix missing game labels in incremental graph.

Retroactively adds game labels to all nodes using card database,
loads card attributes, and enriches graph with metadata.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ..data.incremental_graph import IncrementalCardGraph
from ..data.card_database import get_card_database
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()


def load_card_attributes(attrs_path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load card attributes from CSV (uses canonical implementation)."""
    from ml.utils.data_loading import load_card_attributes as load_attrs_canonical
    return load_attrs_canonical(attrs_path=attrs_path)


def fix_game_labels(graph: IncrementalCardGraph) -> dict[str, int]:
    """Fix missing game labels using card database."""
    logger.info("Fixing game labels using card database...")
    
    card_db = get_card_database()
    card_db.load()
    
    game_map = {
        "magic": "MTG",
        "pokemon": "PKM",
        "yugioh": "YGO",
        "digimon": "DIG",
        "onepiece": "OP",
        "riftbound": "RFT",
    }
    
    fixed = 0
    already_labeled = 0
    not_found = 0
    game_counts = {}
    
    for card_name, node in graph.nodes.items():
        # Skip if already labeled
        if node.game:
            already_labeled += 1
            game_counts[node.game] = game_counts.get(node.game, 0) + 1
            continue
        
        # Try to detect game (with variant matching for split cards)
        try:
            game = card_db.get_game(card_name, fuzzy=True)  # Enable fuzzy for better matching
            if game:
                game_code = game_map.get(game.lower())
                if game_code:
                    node.game = game_code
                    fixed += 1
                    game_counts[game_code] = game_counts.get(game_code, 0) + 1
                else:
                    not_found += 1
            else:
                not_found += 1
        except Exception as e:
            logger.debug(f"Error detecting game for {card_name}: {e}")
            not_found += 1
    
    logger.info(f"Fixed {fixed:,} game labels")
    logger.info(f"Already labeled: {already_labeled:,}")
    logger.info(f"Not found: {not_found:,}")
    logger.info(f"Game distribution: {game_counts}")
    
    return {"fixed": fixed, "already_labeled": already_labeled, "not_found": not_found, "game_counts": game_counts}


def fix_edge_game_labels(graph: IncrementalCardGraph) -> dict[str, int]:
    """Fix missing game labels on edges based on node games."""
    logger.info("Fixing edge game labels based on node games...")
    
    fixed = 0
    already_labeled = 0
    ambiguous = 0
    
    for (card1, card2), edge in graph.edges.items():
        # Skip if already labeled
        if edge.game:
            already_labeled += 1
            continue
        
        # Get games from nodes
        node1_game = graph.nodes.get(card1)
        node2_game = graph.nodes.get(card2)
        
        game1 = node1_game.game if node1_game else None
        game2 = node2_game.game if node2_game else None
        
        # Set edge game
        if game1 and game2:
            if game1 == game2:
                edge.game = game1
                fixed += 1
            else:
                # Cross-game edge (shouldn't happen, but log it)
                logger.debug(f"Cross-game edge: {card1} ({game1}) <-> {card2} ({game2})")
                ambiguous += 1
        elif game1:
            edge.game = game1
            fixed += 1
        elif game2:
            edge.game = game2
            fixed += 1
    
    logger.info(f"Fixed {fixed:,} edge game labels")
    logger.info(f"Already labeled: {already_labeled:,}")
    logger.info(f"Ambiguous: {ambiguous:,}")
    
    return {"fixed": fixed, "already_labeled": already_labeled, "ambiguous": ambiguous}


def enrich_with_attributes(graph: IncrementalCardGraph, card_attributes: dict[str, dict[str, any]]) -> int:
    """Enrich graph nodes with card attributes."""
    if not card_attributes:
        logger.info("No card attributes to load")
        return 0
    
    logger.info("Enriching nodes with card attributes...")
    enriched = 0
    
    for card_name, attrs in card_attributes.items():
        if card_name in graph.nodes:
            node = graph.nodes[card_name]
            if node.attributes is None:
                node.attributes = {}
            node.attributes.update(attrs)
            enriched += 1
    
    logger.info(f"Enriched {enriched:,} nodes with attributes")
    return enriched


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Fix missing game labels in graph")
    parser.add_argument(
        "--graph-path",
        type=Path,
        default=PATHS.incremental_graph_db,
        help="Path to graph database",
    )
    parser.add_argument(
        "--card-attributes",
        type=Path,
        default=PATHS.card_attributes,
        help="Path to card attributes CSV",
    )
    parser.add_argument(
        "--fix-nodes",
        action="store_true",
        default=True,
        help="Fix node game labels",
    )
    parser.add_argument(
        "--fix-edges",
        action="store_true",
        default=True,
        help="Fix edge game labels",
    )
    parser.add_argument(
        "--enrich-attributes",
        action="store_true",
        default=True,
        help="Enrich nodes with card attributes",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        default=True,
        help="Save graph after fixes",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("Fixing Graph Game Labels and Enriching Metadata")
    logger.info("=" * 70)
    
    # Load graph
    logger.info(f"Loading graph from {args.graph_path}...")
    graph = IncrementalCardGraph(args.graph_path, use_sqlite=True)
    
    stats_before = graph.get_statistics()
    logger.info(f"Before: {stats_before['num_nodes']:,} nodes, {stats_before['num_edges']:,} edges")
    
    # Load card attributes
    card_attributes = {}
    if args.enrich_attributes:
        card_attributes = load_card_attributes(args.card_attributes)
    
    # Fix node game labels
    if args.fix_nodes:
        node_results = fix_game_labels(graph)
    
    # Fix edge game labels
    if args.fix_edges:
        edge_results = fix_edge_game_labels(graph)
    
    # Enrich with attributes
    if args.enrich_attributes and card_attributes:
        enriched = enrich_with_attributes(graph, card_attributes)
    
    # Save graph
    if args.save:
        logger.info(f"Saving graph to {args.graph_path}...")
        graph.save(args.graph_path)
        logger.info("✓ Graph saved")
    
    # Final statistics
    stats_after = graph.get_statistics()
    logger.info("\nFinal Statistics:")
    logger.info(f"  Nodes: {stats_after['num_nodes']:,}")
    logger.info(f"  Edges: {stats_after['num_edges']:,}")
    logger.info(f"  Game distribution: {stats_after['game_distribution']}")
    
    return 0


if __name__ == "__main__":
    exit(main())

