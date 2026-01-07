#!/usr/bin/env python3
"""
Validate pack data quality and coverage.

Checks:
- Pack coverage (how many cards in graph are in packs)
- Pack completeness (packs with missing cards)
- Edge coverage (how many edges have pack co-occurrence)
- Data quality issues
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from ..data.incremental_graph import IncrementalCardGraph
from ..data.pack_database import PackDatabase
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()


def validate_pack_data(
    graph: IncrementalCardGraph,
    pack_db: PackDatabase,
    game: str | None = None,
) -> dict[str, any]:
    """
    Validate pack data quality and coverage.
    
    Args:
        graph: IncrementalCardGraph instance
        pack_db: PackDatabase instance
        game: Filter by game
    
    Returns:
        Validation report dict
    """
    logger.info("Validating pack data quality and coverage...")
    
    # Ensure graph is loaded
    if graph.use_sqlite and not graph.nodes:
        logger.info("Loading graph into memory...")
        graph.load_sqlite(graph.graph_path)
    
    report = {
        "pack_stats": {},
        "card_coverage": {},
        "edge_coverage": {},
        "data_quality": {},
    }
    
    # Get pack statistics
    pack_stats = pack_db.get_statistics()
    report["pack_stats"] = pack_stats
    
    # Filter by game if specified
    import sqlite3
    db_conn = sqlite3.connect(str(pack_db.db_path))
    db_conn.row_factory = sqlite3.Row
    cursor = db_conn.cursor()
    
    if game:
        cursor.execute("SELECT COUNT(DISTINCT card_name) FROM pack_cards pc JOIN packs p ON pc.pack_id = p.pack_id WHERE p.game = ?", (game,))
    else:
        cursor.execute("SELECT COUNT(DISTINCT card_name) FROM pack_cards")
    
    unique_pack_cards = cursor.fetchone()[0]
    
    # Get cards in graph (filtered by game)
    if game:
        graph_cards = {name for name, node in graph.nodes.items() if node.game == game}
    else:
        graph_cards = set(graph.nodes.keys())
    
    # Calculate card coverage
    pack_card_names = set()
    if game:
        cursor.execute("""
            SELECT DISTINCT pc.card_name
            FROM pack_cards pc
            JOIN packs p ON pc.pack_id = p.pack_id
            WHERE p.game = ?
        """, (game,))
    else:
        cursor.execute("SELECT DISTINCT card_name FROM pack_cards")
    
    for row in cursor.fetchall():
        pack_card_names.add(row["card_name"])
    
    cards_in_both = graph_cards & pack_card_names
    cards_only_in_graph = graph_cards - pack_card_names
    cards_only_in_packs = pack_card_names - graph_cards
    
    report["card_coverage"] = {
        "total_graph_cards": len(graph_cards),
        "total_pack_cards": len(pack_card_names),
        "cards_in_both": len(cards_in_both),
        "cards_only_in_graph": len(cards_only_in_graph),
        "cards_only_in_packs": len(cards_only_in_packs),
        "coverage_percent": (len(cards_in_both) / len(graph_cards) * 100) if graph_cards else 0,
    }
    
    # Calculate edge coverage (edges with pack co-occurrence)
    edges_with_packs = 0
    edges_without_packs = 0
    
    for edge_key, edge in graph.edges.items():
        if game and edge.game != game:
            continue
        
        if edge.metadata and "pack_co_occurrences" in edge.metadata:
            pack_co_occs = edge.metadata["pack_co_occurrences"]
            if pack_co_occs:
                edges_with_packs += 1
            else:
                edges_without_packs += 1
        else:
            edges_without_packs += 1
    
    total_edges = edges_with_packs + edges_without_packs
    report["edge_coverage"] = {
        "total_edges": total_edges,
        "edges_with_packs": edges_with_packs,
        "edges_without_packs": edges_without_packs,
        "coverage_percent": (edges_with_packs / total_edges * 100) if total_edges else 0,
    }
    
    # Data quality checks
    quality_issues = []
    
    # Check for packs with very few cards (might be incomplete)
    if game:
        cursor.execute("""
            SELECT p.pack_id, p.pack_name, COUNT(pc.card_name) as card_count
            FROM packs p
            LEFT JOIN pack_cards pc ON p.pack_id = pc.pack_id
            WHERE p.game = ?
            GROUP BY p.pack_id
            HAVING card_count < 5
        """, (game,))
    else:
        cursor.execute("""
            SELECT p.pack_id, p.pack_name, COUNT(pc.card_name) as card_count
            FROM packs p
            LEFT JOIN pack_cards pc ON p.pack_id = pc.pack_id
            GROUP BY p.pack_id
            HAVING card_count < 5
        """)
    
    small_packs = cursor.fetchall()
    if small_packs:
        quality_issues.append({
            "type": "small_packs",
            "count": len(small_packs),
            "description": f"{len(small_packs)} packs have fewer than 5 cards (might be incomplete)",
        })
    
    # Check for packs with no release date
    if game:
        cursor.execute("""
            SELECT COUNT(*) FROM packs
            WHERE game = ? AND release_date IS NULL
        """, (game,))
    else:
        cursor.execute("SELECT COUNT(*) FROM packs WHERE release_date IS NULL")
    
    packs_no_date = cursor.fetchone()[0]
    if packs_no_date > 0:
        quality_issues.append({
            "type": "missing_release_dates",
            "count": packs_no_date,
            "description": f"{packs_no_date} packs missing release dates",
        })
    
    report["data_quality"] = {
        "issues": quality_issues,
        "total_issues": len(quality_issues),
    }
    
    db_conn.close()
    
    return report


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Validate pack data quality")
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
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("Validate Pack Data Quality")
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
    
    # Validate
    report = validate_pack_data(graph, pack_db, game=args.game)
    
    # Print report
    logger.info("\n" + "=" * 70)
    logger.info("Pack Statistics")
    logger.info("=" * 70)
    logger.info(f"Total packs: {report['pack_stats']['total_packs']}")
    logger.info(f"Packs by game: {report['pack_stats']['packs_by_game']}")
    logger.info(f"Packs by type: {report['pack_stats']['packs_by_type']}")
    logger.info(f"Total pack-card relationships: {report['pack_stats']['total_pack_cards']}")
    logger.info(f"Unique cards in packs: {report['pack_stats']['unique_cards']}")
    
    logger.info("\n" + "=" * 70)
    logger.info("Card Coverage")
    logger.info("=" * 70)
    coverage = report["card_coverage"]
    logger.info(f"Graph cards: {coverage['total_graph_cards']:,}")
    logger.info(f"Pack cards: {coverage['total_pack_cards']:,}")
    logger.info(f"Cards in both: {coverage['cards_in_both']:,}")
    logger.info(f"Coverage: {coverage['coverage_percent']:.1f}%")
    if coverage["cards_only_in_packs"] > 0:
        logger.info(f"Cards only in packs (not in graph): {coverage['cards_only_in_packs']:,}")
    
    logger.info("\n" + "=" * 70)
    logger.info("Edge Coverage")
    logger.info("=" * 70)
    edge_cov = report["edge_coverage"]
    logger.info(f"Total edges: {edge_cov['total_edges']:,}")
    logger.info(f"Edges with pack co-occurrence: {edge_cov['edges_with_packs']:,}")
    logger.info(f"Coverage: {edge_cov['coverage_percent']:.1f}%")
    
    logger.info("\n" + "=" * 70)
    logger.info("Data Quality")
    logger.info("=" * 70)
    quality = report["data_quality"]
    if quality["total_issues"] == 0:
        logger.info("✓ No quality issues found")
    else:
        logger.info(f"Found {quality['total_issues']} quality issue(s):")
        for issue in quality["issues"]:
            logger.info(f"  • {issue['description']}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

