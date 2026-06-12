#!/usr/bin/env python3
"""
Integrate Meta Share Relationships into Graph

Creates edges for cards with similar meta share (popularity).
Cards with similar meta share are likely to be in similar deck types.
"""

import argparse
import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any

from ..data.incremental_graph import Edge, IncrementalCardGraph
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS


logger = logging.getLogger(__name__)


def compute_meta_share(
    decks_path: Path | str,
    game: str | None = None,
    min_decks: int = 5,
) -> dict[str, float]:
    """
    Compute meta share (popularity) for each card.

    Args:
        decks_path: Path to decks JSONL file
        game: Filter by game (None = all games)
        min_decks: Minimum deck count to include card

    Returns:
        Dict mapping card_name -> meta_share (0-1)
    """
    logger.info("Computing meta share from deck data...")

    card_deck_counts: Counter = Counter()
    total_decks = 0

    with open(decks_path) as f:
        for line in f:
            deck = json.loads(line)

            # Filter by game if specified
            deck_game = deck.get("game")
            if game and deck_game != game:
                continue

            total_decks += 1
            cards = deck.get("cards", [])

            # Count unique cards per deck (mainboard only)
            unique_cards = set()
            for card_entry in cards:
                partition = card_entry.get("partition", "").lower()
                if partition != "sideboard":
                    unique_cards.add(card_entry["name"])

            card_deck_counts.update(unique_cards)

    if total_decks == 0:
        logger.warning("No decks found")
        return {}

    # Compute meta share (percentage of decks containing card)
    meta_share: dict[str, float] = {}
    for card, count in card_deck_counts.items():
        if count >= min_decks:
            meta_share[card] = count / total_decks

    logger.info(f"Computed meta share for {len(meta_share):,} cards (from {total_decks:,} decks)")

    return meta_share


def integrate_meta_share_relationships(
    graph: IncrementalCardGraph,
    decks_path: Path | str | None = None,
    game: str | None = None,
    min_decks: int = 5,
    similarity_threshold: float = 0.05,
    meta_share_edge_weight: float = 0.2,
) -> dict[str, Any]:
    """
    Integrate meta share relationships into graph.

    Args:
        graph: IncrementalCardGraph instance
        decks_path: Path to decks JSONL file
        game: Filter by game (None = all games)
        min_decks: Minimum deck count to include card
        similarity_threshold: Minimum meta share difference to create edge
        meta_share_edge_weight: Weight to add for meta share edges

    Returns:
        Statistics dict
    """
    logger.info("Integrating meta share relationships into graph...")

    stats = {
        "cards_with_meta_share": 0,
        "meta_share_edges_created": 0,
        "meta_share_edges_updated": 0,
        "total_similar_pairs": 0,
    }

    # Load or compute meta share
    if decks_path is None:
        decks_path = PATHS.decks_with_metadata
    elif isinstance(decks_path, str):
        decks_path = Path(decks_path)

    if not decks_path.exists():
        logger.warning(f"Decks file not found: {decks_path}")
        return stats

    meta_share = compute_meta_share(decks_path, game=game, min_decks=min_decks)

    if not meta_share:
        logger.warning("No meta share data computed")
        return stats

    # Filter to cards in graph
    graph_meta_share = {
        card: share
        for card, share in meta_share.items()
        if card in graph.nodes and (not game or graph.nodes[card].game == game)
    }

    stats["cards_with_meta_share"] = len(graph_meta_share)

    # Create edges for cards with similar meta share

    cards_list = list(graph_meta_share.items())
    for i, (card1, share1) in enumerate(cards_list):
        for card2, share2 in cards_list[i + 1 :]:
            # Check similarity threshold
            share_diff = abs(share1 - share2)
            if share_diff > similarity_threshold:
                continue

            stats["total_similar_pairs"] += 1

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

            # Add meta share weight (based on similarity)
            similarity_weight = meta_share_edge_weight * (1.0 - share_diff / similarity_threshold)
            edge.weight += similarity_weight

            # Add meta share metadata
            if edge.metadata is None:
                edge.metadata = {}

            if "meta_share_relationship" not in edge.metadata:
                edge.metadata["meta_share_relationship"] = {
                    "card1_share": share1,
                    "card2_share": share2,
                    "similarity": 1.0 - share_diff / similarity_threshold,
                    "weight": similarity_weight,
                }

            if is_new:
                stats["meta_share_edges_created"] += 1
            else:
                stats["meta_share_edges_updated"] += 1

    logger.info(
        f"Created {stats['meta_share_edges_created']:,} new meta share edges, "
        f"updated {stats['meta_share_edges_updated']:,} existing edges"
    )
    logger.info(
        f"Processed {stats['cards_with_meta_share']:,} cards with meta share, "
        f"{stats['total_similar_pairs']:,} similar pairs"
    )

    return stats


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Integrate meta share relationships into graph")
    parser.add_argument(
        "--graph-db",
        type=str,
        default=str(PATHS.incremental_graph_db),
        help="Path to graph database",
    )
    parser.add_argument(
        "--decks-path",
        type=str,
        default=None,
        help="Path to decks JSONL file",
    )
    parser.add_argument(
        "--game",
        type=str,
        default=None,
        choices=["MTG", "PKM", "YGO"],
        help="Filter by game (default: all games)",
    )
    parser.add_argument(
        "--min-decks",
        type=int,
        default=5,
        help="Minimum deck count to include card",
    )
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.05,
        help="Maximum meta share difference to create edge",
    )
    parser.add_argument(
        "--meta-weight",
        type=float,
        default=0.2,
        help="Weight to add for meta share edges",
    )

    args = parser.parse_args()

    setup_script_logging()

    logger.info("=" * 70)
    logger.info("Integrate Meta Share Relationships")
    logger.info("=" * 70)

    # Load graph
    graph = IncrementalCardGraph(
        graph_path=args.graph_db,
        use_sqlite=True,
    )
    graph.load_sqlite(args.graph_db)

    logger.info(f"Loaded graph: {len(graph.nodes):,} nodes, {len(graph.edges):,} edges")

    # Integrate meta share relationships
    results = integrate_meta_share_relationships(
        graph,
        decks_path=args.decks_path,
        game=args.game,
        min_decks=args.min_decks,
        similarity_threshold=args.similarity_threshold,
        meta_share_edge_weight=args.meta_weight,
    )

    # Save graph
    logger.info("Saving graph...")
    graph.save_sqlite(args.graph_db)

    logger.info("")
    logger.info("✓ Results: %s", results)


if __name__ == "__main__":
    main()
