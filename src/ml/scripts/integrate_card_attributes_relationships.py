#!/usr/bin/env python3
"""
Integrate card attribute relationships into the graph.

Creates edges based on shared attributes:
- Color identity (cards sharing colors)
- Card type (creatures, spells, etc.)
- Mechanics/keywords (cards with same keywords)
- Rarity (cards of similar rarity)
- Set/block (cards from same set/block)
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from ..data.incremental_graph import IncrementalCardGraph
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()


def load_card_attributes(attrs_path: Path | None = None) -> dict[str, dict[str, any]]:
    """Load card attributes from CSV (uses canonical implementation)."""
    from ml.utils.data_loading import load_card_attributes as load_attrs_canonical
    attrs = load_attrs_canonical(attrs_path=attrs_path)
    
    # Post-process for this script's specific needs (parse string fields)
    for card_name, card_attrs in attrs.items():
        # Parse color_identity if it's a string
        color_identity = card_attrs.get("colors") or card_attrs.get("color_identity", [])
        if isinstance(color_identity, str):
            color_identity = [c.strip() for c in color_identity.split(",") if c.strip()]
        elif not isinstance(color_identity, list):
            color_identity = []
        card_attrs["color_identity"] = color_identity
        
        # Parse keywords if it's a string
        keywords = card_attrs.get("keywords", [])
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(",") if k.strip()]
        elif not isinstance(keywords, list):
            keywords = []
        card_attrs["keywords"] = keywords
        
        # Parse subtypes if it's a string
        subtypes = card_attrs.get("subtypes", [])
        if isinstance(subtypes, str):
            subtypes = [s.strip() for s in subtypes.split(",") if s.strip()]
        elif not isinstance(subtypes, list):
            subtypes = []
        card_attrs["subtypes"] = subtypes
        
        # Normalize type field
        if "type" not in card_attrs or not card_attrs["type"]:
            card_attrs["type"] = card_attrs.get("type_line")
    
    return attrs


def integrate_attribute_relationships(
    graph: IncrementalCardGraph,
    card_attributes: dict[str, dict[str, any]],
    game: str | None = None,
    attribute_edge_weight: int = 1,
    min_shared_attributes: int = 1,
) -> dict[str, int]:
    """
    Integrate card attribute relationships into the graph.
    
    Args:
        graph: IncrementalCardGraph instance
        card_attributes: Dict mapping card names to their attributes
        game: Filter by game
        attribute_edge_weight: Weight to add for shared attributes
        min_shared_attributes: Minimum shared attributes to create edge
    
    Returns:
        Statistics dict
    """
    logger.info("Integrating card attribute relationships...")
    
    # Ensure graph is loaded
    if graph.use_sqlite and not graph.nodes:
        logger.info("Loading graph into memory...")
        graph.load_sqlite(graph.graph_path)
    
    stats = {
        "color_edges": 0,
        "type_edges": 0,
        "keyword_edges": 0,
        "set_edges": 0,
        "rarity_edges": 0,
        "total_edges_created": 0,
        "total_edges_updated": 0,
    }
    
    # Filter cards by game
    graph_cards = {
        name: node
        for name, node in graph.nodes.items()
        if not game or node.game == game
    }
    
    # Group cards by attributes
    cards_by_color: dict[tuple, set[str]] = defaultdict(set)
    cards_by_type: dict[str, set[str]] = defaultdict(set)
    cards_by_keyword: dict[str, set[str]] = defaultdict(set)
    cards_by_set: dict[str, set[str]] = defaultdict(set)
    cards_by_rarity: dict[str, set[str]] = defaultdict(set)
    
    for card_name, attrs in card_attributes.items():
        if card_name not in graph_cards:
            continue
        
        # Group by color identity
        if attrs.get("color_identity"):
            color_tuple = tuple(sorted(attrs["color_identity"]))
            cards_by_color[color_tuple].add(card_name)
        
        # Group by type
        card_type_val = attrs.get("type")
        if card_type_val and isinstance(card_type_val, str):
            card_type = card_type_val.split()[0] if " " in card_type_val else card_type_val
            cards_by_type[card_type].add(card_name)
        
        # Group by keywords
        if attrs.get("keywords"):
            for keyword in attrs["keywords"]:
                cards_by_keyword[keyword].add(card_name)
        
        # Group by set
        if attrs.get("set"):
            cards_by_set[attrs["set"]].add(card_name)
        
        # Group by rarity
        if attrs.get("rarity"):
            cards_by_rarity[attrs["rarity"]].add(card_name)
    
    # Create edges for cards sharing attributes
    from ..data.incremental_graph import Edge
    from datetime import datetime
    
    def add_attribute_edge(card1: str, card2: str, attribute_type: str) -> None:
        """Add or update edge for shared attribute."""
        edge_key = tuple(sorted([card1, card2]))
        
        if edge_key in graph.edges:
            edge = graph.edges[edge_key]
            is_new = False
        else:
            edge = Edge(
                card1=edge_key[0],
                card2=edge_key[1],
                game=game or graph_cards[card1].game if card1 in graph_cards else None,
                weight=0,
            )
            graph.edges[edge_key] = edge
            is_new = True
        
        # Add attribute weight
        edge.weight += attribute_edge_weight
        
        # Add attribute metadata
        if edge.metadata is None:
            edge.metadata = {}
        
        if "attribute_relationships" not in edge.metadata:
            edge.metadata["attribute_relationships"] = []
        
        edge.metadata["attribute_relationships"].append({
            "type": attribute_type,
            "weight": attribute_edge_weight,
        })
        
        if is_new:
            stats["total_edges_created"] += 1
        else:
            stats["total_edges_updated"] += 1
    
    # Create edges for shared colors
    logger.info("Creating edges for shared color identity...")
    for color_tuple, cards in cards_by_color.items():
        if len(cards) < 2:
            continue
        card_list = list(cards)
        for i, card1 in enumerate(card_list):
            for card2 in card_list[i + 1:]:
                add_attribute_edge(card1, card2, "color_identity")
                stats["color_edges"] += 1
    
    # Create edges for shared types
    logger.info("Creating edges for shared card types...")
    for card_type, cards in cards_by_type.items():
        if len(cards) < 2:
            continue
        card_list = list(cards)
        for i, card1 in enumerate(card_list):
            for card2 in card_list[i + 1:]:
                add_attribute_edge(card1, card2, "type")
                stats["type_edges"] += 1
    
    # Create edges for shared keywords
    logger.info("Creating edges for shared keywords...")
    for keyword, cards in cards_by_keyword.items():
        if len(cards) < 2:
            continue
        card_list = list(cards)
        for i, card1 in enumerate(card_list):
            for card2 in card_list[i + 1:]:
                add_attribute_edge(card1, card2, "keyword")
                stats["keyword_edges"] += 1
    
    # Create edges for shared sets
    logger.info("Creating edges for shared sets...")
    for set_code, cards in cards_by_set.items():
        if len(cards) < 2:
            continue
        card_list = list(cards)
        for i, card1 in enumerate(card_list):
            for card2 in card_list[i + 1:]:
                add_attribute_edge(card1, card2, "set")
                stats["set_edges"] += 1
    
    # Create edges for shared rarity
    logger.info("Creating edges for shared rarity...")
    for rarity, cards in cards_by_rarity.items():
        if len(cards) < 2:
            continue
        card_list = list(cards)
        for i, card1 in enumerate(card_list):
            for card2 in card_list[i + 1:]:
                add_attribute_edge(card1, card2, "rarity")
                stats["rarity_edges"] += 1
    
    logger.info(f"Created/updated {stats['total_edges_created'] + stats['total_edges_updated']} attribute edges")
    logger.info(f"  Color: {stats['color_edges']}")
    logger.info(f"  Type: {stats['type_edges']}")
    logger.info(f"  Keyword: {stats['keyword_edges']}")
    logger.info(f"  Set: {stats['set_edges']}")
    logger.info(f"  Rarity: {stats['rarity_edges']}")
    
    return stats


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Integrate card attribute relationships")
    parser.add_argument(
        "--graph-db",
        type=Path,
        default=PATHS.incremental_graph_db,
        help="Path to graph database",
    )
    parser.add_argument(
        "--attributes",
        type=Path,
        default=PATHS.card_attributes,
        help="Path to card attributes CSV",
    )
    parser.add_argument(
        "--game",
        choices=["MTG", "PKM", "YGO"],
        help="Filter by game",
    )
    parser.add_argument(
        "--attribute-weight",
        type=int,
        default=1,
        help="Weight to add for shared attributes",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("Integrate Card Attribute Relationships")
    logger.info("=" * 70)
    
    # Load graph
    graph = IncrementalCardGraph(
        graph_path=args.graph_db,
        use_sqlite=True,
    )
    
    # Load card attributes
    card_attributes = load_card_attributes(args.attributes)
    
    if not card_attributes:
        logger.error("No card attributes loaded")
        return 1
    
    # Integrate
    results = integrate_attribute_relationships(
        graph,
        card_attributes,
        game=args.game,
        attribute_edge_weight=args.attribute_weight,
    )
    
    # Save graph
    logger.info("Saving graph...")
    graph.save_sqlite(args.graph_db)
    
    logger.info(f"\n✓ Results: {results}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

