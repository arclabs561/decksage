#!/usr/bin/env python3
"""
Integrate Win Rate Relationships into Graph

Creates edges for cards that appear together in winning decks.
Cards in winning decks together have proven synergy.
"""

import argparse
import json
import logging
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ..data.incremental_graph import Edge, IncrementalCardGraph
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS


logger = logging.getLogger(__name__)


def compute_win_rate_cooccurrence(
    decks_path: Path | str,
    game: str | None = None,
    min_wins: int = 3,
) -> dict[str, dict[str, float]]:
    """
    Compute win rate co-occurrence from deck data.

    Args:
        decks_path: Path to decks JSONL file
        game: Filter by game (None = all games)
        min_wins: Minimum wins to consider deck as "winning"

    Returns:
        Dict mapping card1 -> dict of card2 -> win_rate_cooccurrence
    """
    logger.info("Computing win rate co-occurrence from deck data...")

    winning_deck_pairs: defaultdict[str, Counter] = defaultdict(Counter)
    card_win_counts: Counter = Counter()

    with open(decks_path) as f:
        for line in f:
            deck = json.loads(line)

            # Filter by game if specified
            deck_game = deck.get("game")
            if game and deck_game != game:
                continue

            # Check if winning deck (based on placement or win count)
            placement = deck.get("metadata", {}).get("placement")
            wins = deck.get("metadata", {}).get("wins", 0)

            is_winning = False
            if placement:
                # Top 8, Top 4, 1st place, etc.
                placement_str = str(placement).lower()
                is_winning = any(
                    x in placement_str
                    for x in ["top 8", "top 4", "1st", "first", "winner", "champion"]
                )
            elif wins >= min_wins:
                is_winning = True

            if not is_winning:
                continue

            cards = deck.get("cards", [])

            # Extract mainboard cards
            mainboard_cards = [
                c["name"] for c in cards if c.get("partition", "").lower() != "sideboard"
            ]

            if len(mainboard_cards) < 2:
                continue

            # Count co-occurrences in winning decks
            unique_cards = set(mainboard_cards)
            for card in unique_cards:
                card_win_counts[card] += 1
                for other in unique_cards:
                    if card != other:
                        winning_deck_pairs[card][other] += 1

    # Convert to win rate co-occurrence (frequency in winning decks)
    win_rate_cooccurrence: dict[str, dict[str, float]] = {}
    for card, cooccurrences in winning_deck_pairs.items():
        total_wins = card_win_counts[card]
        if total_wins < min_wins:
            continue

        win_rate_cooccurrence[card] = {
            other: count / total_wins
            for other, count in cooccurrences.items()
            if card_win_counts[other] >= min_wins
        }

    logger.info(
        f"Computed win rate co-occurrence for {len(win_rate_cooccurrence):,} cards "
        f"(from {sum(card_win_counts.values()):,} winning deck appearances)"
    )

    return win_rate_cooccurrence


def integrate_win_rate_relationships(
    graph: IncrementalCardGraph,
    decks_path: Path | str | None = None,
    game: str | None = None,
    min_wins: int = 3,
    min_cooccurrence: float = 0.1,
    win_rate_edge_weight: float = 0.4,
) -> dict[str, Any]:
    """
    Integrate win rate relationships into graph.

    Args:
        graph: IncrementalCardGraph instance
        decks_path: Path to decks JSONL file
        game: Filter by game (None = all games)
        min_wins: Minimum wins to consider deck as "winning"
        min_cooccurrence: Minimum co-occurrence frequency to create edge
        win_rate_edge_weight: Base weight to add for win rate edges

    Returns:
        Statistics dict
    """
    logger.info("Integrating win rate relationships into graph...")

    stats = {
        "winning_decks_processed": 0,
        "win_rate_edges_created": 0,
        "win_rate_edges_updated": 0,
        "cards_with_win_data": 0,
        "total_win_pairs": 0,
    }

    # Load or compute win rate co-occurrence
    if decks_path is None:
        decks_path = PATHS.decks_with_metadata
    elif isinstance(decks_path, str):
        decks_path = Path(decks_path)

    if not decks_path.exists():
        logger.warning(f"Decks file not found: {decks_path}")
        return stats

    win_rate_cooccurrence = compute_win_rate_cooccurrence(decks_path, game=game, min_wins=min_wins)

    if not win_rate_cooccurrence:
        logger.warning("No win rate co-occurrence data computed")
        return stats

    # Create/update edges for win rate co-occurrence

    for card1, cooccurrences in win_rate_cooccurrence.items():
        if card1 not in graph.nodes:
            continue

        stats["cards_with_win_data"] += 1

        for card2, frequency in cooccurrences.items():
            if card2 not in graph.nodes:
                continue

            if frequency < min_cooccurrence:
                continue

            stats["total_win_pairs"] += 1

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

            # Add win rate weight (scaled by frequency)
            weight = win_rate_edge_weight * frequency
            edge.weight += weight

            # Add win rate metadata
            if edge.metadata is None:
                edge.metadata = {}

            if "win_rate_co_occurrences" not in edge.metadata:
                edge.metadata["win_rate_co_occurrences"] = []

            edge.metadata["win_rate_co_occurrences"].append(
                {
                    "frequency": frequency,
                    "weight": weight,
                }
            )

            if is_new:
                stats["win_rate_edges_created"] += 1
            else:
                stats["win_rate_edges_updated"] += 1

    logger.info(
        f"Created {stats['win_rate_edges_created']:,} new win rate edges, "
        f"updated {stats['win_rate_edges_updated']:,} existing edges"
    )
    logger.info(
        f"Processed {stats['cards_with_win_data']:,} cards with win data, "
        f"{stats['total_win_pairs']:,} win pairs"
    )

    return stats


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Integrate win rate relationships into graph")
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
        "--min-wins",
        type=int,
        default=3,
        help="Minimum wins to consider deck as winning",
    )
    parser.add_argument(
        "--min-cooccurrence",
        type=float,
        default=0.1,
        help="Minimum co-occurrence frequency to create edge",
    )
    parser.add_argument(
        "--win-weight",
        type=float,
        default=0.4,
        help="Base weight to add for win rate edges",
    )

    args = parser.parse_args()

    setup_script_logging()

    logger.info("=" * 70)
    logger.info("Integrate Win Rate Relationships")
    logger.info("=" * 70)

    # Load graph
    graph = IncrementalCardGraph(
        graph_path=args.graph_db,
        use_sqlite=True,
    )
    graph.load_sqlite(args.graph_db)

    logger.info(f"Loaded graph: {len(graph.nodes):,} nodes, {len(graph.edges):,} edges")

    # Integrate win rate relationships
    results = integrate_win_rate_relationships(
        graph,
        decks_path=args.decks_path,
        game=args.game,
        min_wins=args.min_wins,
        min_cooccurrence=args.min_cooccurrence,
        win_rate_edge_weight=args.win_weight,
    )

    # Save graph
    logger.info("Saving graph...")
    graph.save_sqlite(args.graph_db)

    logger.info("")
    logger.info("✓ Results: %s", results)


if __name__ == "__main__":
    main()
