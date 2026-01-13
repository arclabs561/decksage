#!/usr/bin/env python3
"""
Integrate Sideboard Relationships into Graph

Creates edges for cards that appear together in sideboards.
Sideboard co-occurrence is a strong signal for meta-specific synergies.
"""

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from ..data.incremental_graph import Edge, IncrementalCardGraph
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS


logger = logging.getLogger(__name__)


def integrate_sideboard_relationships(
    graph: IncrementalCardGraph,
    sideboard_data_path: Path | str | None = None,
    game: str | None = None,
    min_cooccurrence: int = 2,
    sideboard_edge_weight: float = 0.5,
) -> dict[str, Any]:
    """
    Integrate sideboard co-occurrence relationships into graph.

    Args:
        graph: IncrementalCardGraph instance
        sideboard_data_path: Path to sideboard co-occurrence JSON file
        game: Filter by game (None = all games)
        min_cooccurrence: Minimum co-occurrence count to create edge
        sideboard_edge_weight: Weight to add for sideboard edges

    Returns:
        Statistics dict
    """
    logger.info("Integrating sideboard relationships into graph...")

    stats = {
        "sideboard_edges_created": 0,
        "sideboard_edges_updated": 0,
        "cards_with_sideboard_data": 0,
        "total_sideboard_pairs": 0,
    }

    # Load sideboard data
    if sideboard_data_path is None:
        # Try multiple possible locations
        possible_paths = [
            PATHS.experiments / "signals" / "sideboard_cooccurrence.json",
            PATHS.data / "signals" / "sideboard_cooccurrence.json",
            Path("data/signals/sideboard_cooccurrence.json"),
        ]
        sideboard_data_path = None
        for path in possible_paths:
            if Path(path).exists():
                sideboard_data_path = path
                break
        if sideboard_data_path is None:
            logger.warning(f"Sideboard data not found in any of: {possible_paths}")
            return stats
    elif isinstance(sideboard_data_path, str):
        sideboard_data_path = Path(sideboard_data_path)

    if not sideboard_data_path.exists():
        logger.warning(f"Sideboard data not found: {sideboard_data_path}")
        return stats

    with open(sideboard_data_path) as f:
        sideboard_data = json.load(f)

    logger.info(f"Loaded sideboard data for {len(sideboard_data):,} cards")

    # Filter by game if specified
    if game:
        # Filter cards to only those in graph with matching game
        filtered_data = {}
        for card_name, cooccurrences in sideboard_data.items():
            if card_name in graph.nodes:
                node = graph.nodes[card_name]
                if node.game == game:
                    # Also filter co-occurrences by game
                    filtered_cooccurrences = {
                        other: count
                        for other, count in cooccurrences.items()
                        if other in graph.nodes and graph.nodes[other].game == game
                    }
                    if filtered_cooccurrences:
                        filtered_data[card_name] = filtered_cooccurrences
        sideboard_data = filtered_data
        logger.info(f"Filtered to {len(sideboard_data):,} cards for game {game}")

    # Create/update edges for sideboard co-occurrence

    for card1, cooccurrences in sideboard_data.items():
        if card1 not in graph.nodes:
            continue

        stats["cards_with_sideboard_data"] += 1

        for card2, count in cooccurrences.items():
            if card2 not in graph.nodes:
                continue

            if count < min_cooccurrence:
                continue

            stats["total_sideboard_pairs"] += 1

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
                    game=game or graph.nodes[card1].game,
                    weight=0,
                )
                graph.edges[edge_key] = edge
                is_new = True

            # Add sideboard weight (reduced compared to mainboard)
            edge.weight += sideboard_edge_weight * count

            # Add sideboard metadata
            if edge.metadata is None:
                edge.metadata = {}

            if "sideboard_co_occurrences" not in edge.metadata:
                edge.metadata["sideboard_co_occurrences"] = []

            edge.metadata["sideboard_co_occurrences"].append(
                {
                    "count": count,
                    "weight": sideboard_edge_weight * count,
                }
            )

            if is_new:
                stats["sideboard_edges_created"] += 1
            else:
                stats["sideboard_edges_updated"] += 1

    logger.info(
        f"Created {stats['sideboard_edges_created']:,} new sideboard edges, "
        f"updated {stats['sideboard_edges_updated']:,} existing edges"
    )
    logger.info(
        f"Processed {stats['cards_with_sideboard_data']:,} cards with sideboard data, "
        f"{stats['total_sideboard_pairs']:,} total pairs"
    )

    return stats


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Integrate sideboard relationships into graph")
    parser.add_argument(
        "--graph-db",
        type=str,
        default=str(PATHS.incremental_graph_db),
        help="Path to graph database",
    )
    parser.add_argument(
        "--sideboard-data",
        type=str,
        default=None,
        help="Path to sideboard co-occurrence JSON file",
    )
    parser.add_argument(
        "--game",
        type=str,
        default=None,
        choices=["MTG", "PKM", "YGO"],
        help="Filter by game (default: all games)",
    )
    parser.add_argument(
        "--min-cooccurrence",
        type=int,
        default=2,
        help="Minimum co-occurrence count to create edge",
    )
    parser.add_argument(
        "--sideboard-weight",
        type=float,
        default=0.5,
        help="Weight to add for sideboard edges",
    )

    args = parser.parse_args()

    setup_script_logging()

    logger.info("=" * 70)
    logger.info("Integrate Sideboard Relationships")
    logger.info("=" * 70)

    # Load graph
    graph = IncrementalCardGraph(
        graph_path=args.graph_db,
        use_sqlite=True,
    )
    graph.load_sqlite(args.graph_db)

    logger.info(f"Loaded graph: {len(graph.nodes):,} nodes, {len(graph.edges):,} edges")

    # Integrate sideboard relationships
    results = integrate_sideboard_relationships(
        graph,
        sideboard_data_path=args.sideboard_data,
        game=args.game,
        min_cooccurrence=args.min_cooccurrence,
        sideboard_edge_weight=args.sideboard_weight,
    )

    # Save graph
    logger.info("Saving graph...")
    graph.save_sqlite(args.graph_db)

    logger.info("")
    logger.info("✓ Results: %s", results)


if __name__ == "__main__":
    main()
