#!/usr/bin/env python3
"""
Analyze pack coverage and identify gaps.

Shows:
- Which high-frequency cards are missing from packs
- Which packs have the most cards in graph
- Coverage by pack type
- Recommendations for improving coverage
"""

from __future__ import annotations

import argparse
import sqlite3
from collections import Counter
from pathlib import Path

from ..data.incremental_graph import IncrementalCardGraph
from ..data.pack_database import PackDatabase
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()


def analyze_pack_coverage(
    graph: IncrementalCardGraph,
    pack_db: PackDatabase,
    game: str | None = None,
    top_n: int = 50,
) -> dict[str, any]:
    """
    Analyze pack coverage and identify gaps.
    
    Args:
        graph: IncrementalCardGraph instance
        pack_db: PackDatabase instance
        game: Filter by game
        top_n: Number of top cards to analyze
    
    Returns:
        Analysis report dict
    """
    logger.info("Analyzing pack coverage...")
    
    # Ensure graph is loaded
    if graph.use_sqlite and not graph.nodes:
        logger.info("Loading graph into memory...")
        graph.load_sqlite(graph.graph_path)
    
    report = {
        "missing_cards": [],
        "top_packs": [],
        "coverage_by_type": {},
        "recommendations": [],
    }
    
    # Get high-frequency cards not in packs
    import sqlite3
    db_conn = sqlite3.connect(str(pack_db.db_path))
    db_conn.row_factory = sqlite3.Row
    cursor = db_conn.cursor()
    
    # Get all pack cards
    if game:
        cursor.execute("""
            SELECT DISTINCT pc.card_name
            FROM pack_cards pc
            JOIN packs p ON pc.pack_id = p.pack_id
            WHERE p.game = ?
        """, (game,))
    else:
        cursor.execute("SELECT DISTINCT card_name FROM pack_cards")
    
    pack_card_names = {row["card_name"] for row in cursor.fetchall()}
    
    # Find high-frequency graph cards not in packs
    graph_cards_by_freq = []
    for name, node in graph.nodes.items():
        if game and node.game != game:
            continue
        if name not in pack_card_names:
            graph_cards_by_freq.append((name, node.total_decks, node.game))
    
    graph_cards_by_freq.sort(key=lambda x: x[1], reverse=True)
    report["missing_cards"] = [
        {"card_name": name, "total_decks": decks, "game": game_code}
        for name, decks, game_code in graph_cards_by_freq[:top_n]
    ]
    
    # Find packs with most cards in graph
    # Note: We can't query graph nodes from pack database, so we'll use graph.nodes
    graph_card_names = {name for name, node in graph.nodes.items() if not game or node.game == game}
    
    if game:
        cursor.execute("""
            SELECT p.pack_id, p.pack_name, p.pack_type, 
                   COUNT(pc.card_name) as total_cards
            FROM packs p
            JOIN pack_cards pc ON p.pack_id = pc.pack_id
            WHERE p.game = ?
            GROUP BY p.pack_id
            ORDER BY total_cards DESC
            LIMIT 20
        """, (game,))
    else:
        # For all games, we'd need to check against all graph cards
        # Simplified: just count total cards per pack
        cursor.execute("""
            SELECT p.pack_id, p.pack_name, p.pack_type,
                   COUNT(pc.card_name) as total_cards
            FROM packs p
            JOIN pack_cards pc ON p.pack_id = pc.pack_id
            GROUP BY p.pack_id
            ORDER BY total_cards DESC
            LIMIT 20
        """)
    
    top_packs = []
    for row in cursor.fetchall():
        # Count cards in graph for this pack
        pack_cards = pack_db.get_pack_cards(row["pack_id"])
        cards_in_graph = sum(1 for card in pack_cards if card["card_name"] in graph_card_names)
        
        top_packs.append({
            "pack_id": row["pack_id"],
            "pack_name": row["pack_name"],
            "pack_type": row["pack_type"],
            "total_cards": row["total_cards"],
            "cards_in_graph": cards_in_graph,
        })
    report["top_packs"] = top_packs
    
    # Coverage by pack type
    if game:
        cursor.execute("""
            SELECT p.pack_type, COUNT(DISTINCT p.pack_id) as pack_count,
                   COUNT(DISTINCT pc.card_name) as unique_cards
            FROM packs p
            LEFT JOIN pack_cards pc ON p.pack_id = pc.pack_id
            WHERE p.game = ? AND p.pack_type IS NOT NULL
            GROUP BY p.pack_type
        """, (game,))
    else:
        cursor.execute("""
            SELECT p.pack_type, COUNT(DISTINCT p.pack_id) as pack_count,
                   COUNT(DISTINCT pc.card_name) as unique_cards
            FROM packs p
            LEFT JOIN pack_cards pc ON p.pack_id = pc.pack_id
            WHERE p.pack_type IS NOT NULL
            GROUP BY p.pack_type
        """)
    
    coverage_by_type = {}
    for row in cursor.fetchall():
        coverage_by_type[row["pack_type"]] = {
            "pack_count": row["pack_count"],
            "unique_cards": row["unique_cards"],
        }
    report["coverage_by_type"] = coverage_by_type
    
    # Generate recommendations
    recommendations = []
    
    if len(report["missing_cards"]) > 0:
        top_missing = report["missing_cards"][:10]
        recommendations.append({
            "type": "high_frequency_missing",
            "description": f"{len(report['missing_cards'])} high-frequency cards not in packs",
            "examples": [c["card_name"] for c in top_missing],
            "action": "Consider scraping additional packs or sets containing these cards",
        })
    
    # Get graph cards count for comparison
    if game:
        graph_cards_count = sum(1 for name, node in graph.nodes.items() if node.game == game)
    else:
        graph_cards_count = len(graph.nodes)
    
    if len(pack_card_names) < graph_cards_count * 0.5:
        recommendations.append({
            "type": "low_coverage",
            "description": f"Only {len(pack_card_names)}/{graph_cards_count} cards in packs",
            "action": "Scrape more packs to improve coverage",
        })
    
    report["recommendations"] = recommendations
    
    db_conn.close()
    
    return report


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Analyze pack coverage")
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
        "--top-n",
        type=int,
        default=50,
        help="Number of top cards to analyze",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("Analyze Pack Coverage")
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
    
    # Analyze
    report = analyze_pack_coverage(graph, pack_db, game=args.game, top_n=args.top_n)
    
    # Print report
    logger.info("\n" + "=" * 70)
    logger.info("Missing High-Frequency Cards (Top 20)")
    logger.info("=" * 70)
    for i, card in enumerate(report["missing_cards"][:20], 1):
        logger.info(f"{i:2d}. {card['card_name']:40s} ({card['game'] or 'Unknown'}, {card['total_decks']:5d} decks)")
    
    logger.info("\n" + "=" * 70)
    logger.info("Top Packs by Card Count")
    logger.info("=" * 70)
    for i, pack in enumerate(report["top_packs"][:10], 1):
        logger.info(
            f"{i:2d}. {pack['pack_name']:40s} "
            f"({pack['pack_type']}, {pack['total_cards']:3d} cards, "
            f"{pack['cards_in_graph']:3d} in graph)"
        )
    
    logger.info("\n" + "=" * 70)
    logger.info("Coverage by Pack Type")
    logger.info("=" * 70)
    for pack_type, stats in sorted(report["coverage_by_type"].items()):
        logger.info(
            f"{pack_type:15s}: {stats['pack_count']:3d} packs, "
            f"{stats['unique_cards']:5d} unique cards"
        )
    
    if report["recommendations"]:
        logger.info("\n" + "=" * 70)
        logger.info("Recommendations")
        logger.info("=" * 70)
        for rec in report["recommendations"]:
            logger.info(f"• {rec['description']}")
            if "examples" in rec:
                logger.info(f"  Examples: {', '.join(rec['examples'][:5])}")
            logger.info(f"  Action: {rec['action']}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

