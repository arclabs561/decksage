#!/usr/bin/env python3
"""
Integrate Ban List Relationships into Graph

Creates edges for cards that are banned together in the same format.
Ban list relationships indicate cards that were problematic together.
"""

import argparse
import logging
from typing import Any

from ..data.incremental_graph import Edge, IncrementalCardGraph
from ..knowledge.game_knowledge_base import GameKnowledgeBase
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS


logger = logging.getLogger(__name__)


def load_ban_lists(game: str | None = None) -> dict[str, list[str]]:
    """
    Load ban lists for all formats.

    Args:
        game: Filter by game (None = all games)

    Returns:
        Dict mapping format_name -> list of banned card names
    """
    logger.info("Loading ban lists...")

    ban_lists: dict[str, list[str]] = {}

    # Load from knowledge base
    knowledge_base = GameKnowledgeBase()

    # Map game codes to knowledge base names
    game_map = {"MTG": "magic", "PKM": "pokemon", "YGO": "yugioh"}

    for game_code in ["MTG", "PKM", "YGO"] if game is None else [game]:
        try:
            game_name = game_map.get(game_code, game_code.lower())
            knowledge = knowledge_base.load_game_knowledge(game_name)
            if knowledge and knowledge.formats:
                for format_def in knowledge.formats:
                    if format_def.ban_list:
                        format_key = f"{game_code}:{format_def.name}"
                        ban_lists[format_key] = format_def.ban_list
                        logger.debug(
                            f"Loaded {len(format_def.ban_list)} banned cards for {format_key}"
                        )
        except Exception as e:
            logger.warning(f"Failed to load ban lists for {game_code}: {e}")

    logger.info(f"Loaded ban lists for {len(ban_lists):,} formats")
    return ban_lists


def integrate_ban_list_relationships(
    graph: IncrementalCardGraph,
    game: str | None = None,
    ban_list_edge_weight: float = 0.3,
) -> dict[str, Any]:
    """
    Integrate ban list relationships into graph.

    Args:
        graph: IncrementalCardGraph instance
        game: Filter by game (None = all games)
        ban_list_edge_weight: Weight to add for ban list edges

    Returns:
        Statistics dict
    """
    logger.info("Integrating ban list relationships into graph...")

    stats = {
        "formats_processed": 0,
        "ban_list_edges_created": 0,
        "ban_list_edges_updated": 0,
        "total_banned_cards": 0,
    }

    # Load ban lists
    ban_lists = load_ban_lists(game=game)

    if not ban_lists:
        logger.warning("No ban lists found")
        return stats

    # Create/update edges for cards banned together

    for format_key, banned_cards in ban_lists.items():
        if len(banned_cards) < 2:
            continue

        stats["formats_processed"] += 1
        stats["total_banned_cards"] += len(banned_cards)

        # Filter to cards in graph
        graph_banned = [card for card in banned_cards if card in graph.nodes]

        if len(graph_banned) < 2:
            continue

        # Create edges for all pairs of banned cards
        for i, card1 in enumerate(graph_banned):
            for card2 in graph_banned[i + 1 :]:
                # Verify both cards are in graph and match game filter
                if card1 not in graph.nodes or card2 not in graph.nodes:
                    continue

                node1 = graph.nodes[card1]
                node2 = graph.nodes[card2]

                if game and (node1.game != game or node2.game != game):
                    continue

                # Create edge key (sorted for consistency)
                edge_key = tuple(sorted([card1, card2]))

                # Get or create edge
                if edge_key in graph.edges:
                    edge = graph.edges[edge_key]
                    is_new = False
                else:
                    edge = Edge(
                        card1=edge_key[0],
                        card2=edge_key[1],
                        game=game or node1.game,
                        weight=0,
                    )
                    graph.edges[edge_key] = edge
                    is_new = True

                # Add ban list weight (lower than mainboard co-occurrence)
                edge.weight += ban_list_edge_weight

                # Add ban list metadata
                if edge.metadata is None:
                    edge.metadata = {}

                if "ban_list_relationships" not in edge.metadata:
                    edge.metadata["ban_list_relationships"] = []

                edge.metadata["ban_list_relationships"].append(
                    {
                        "format": format_key,
                        "weight": ban_list_edge_weight,
                    }
                )

                if is_new:
                    stats["ban_list_edges_created"] += 1
                else:
                    stats["ban_list_edges_updated"] += 1

    logger.info(f"Processed {stats['formats_processed']:,} formats with ban lists")
    logger.info(
        f"Created {stats['ban_list_edges_created']:,} new ban list edges, "
        f"updated {stats['ban_list_edges_updated']:,} existing edges"
    )
    logger.info(f"Total banned cards: {stats['total_banned_cards']:,}")

    return stats


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Integrate ban list relationships into graph")
    parser.add_argument(
        "--graph-db",
        type=str,
        default=str(PATHS.incremental_graph_db),
        help="Path to graph database",
    )
    parser.add_argument(
        "--game",
        type=str,
        default=None,
        choices=["MTG", "PKM", "YGO"],
        help="Filter by game (default: all games)",
    )
    parser.add_argument(
        "--ban-weight",
        type=float,
        default=0.3,
        help="Weight to add for ban list edges",
    )

    args = parser.parse_args()

    setup_script_logging()

    logger.info("=" * 70)
    logger.info("Integrate Ban List Relationships")
    logger.info("=" * 70)

    # Load graph
    graph = IncrementalCardGraph(
        graph_path=args.graph_db,
        use_sqlite=True,
    )
    graph.load_sqlite(args.graph_db)

    logger.info(f"Loaded graph: {len(graph.nodes):,} nodes, {len(graph.edges):,} edges")

    # Integrate ban list relationships
    results = integrate_ban_list_relationships(
        graph,
        game=args.game,
        ban_list_edge_weight=args.ban_weight,
    )

    # Save graph
    logger.info("Saving graph...")
    graph.save_sqlite(args.graph_db)

    logger.info("")
    logger.info("✓ Results: %s", results)


if __name__ == "__main__":
    main()
