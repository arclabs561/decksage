#!/usr/bin/env python3
"""
Unified script to integrate all data sources into the graph.

Orchestrates:
- Pack co-occurrence
- Archetype relationships
- Card attribute relationships
- Tournament performance
- Format legality
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..data.incremental_graph import IncrementalCardGraph
from ..data.pack_database import PackDatabase
from ..scripts.integrate_packs_into_graph import integrate_packs_into_graph
from ..scripts.integrate_archetype_relationships import integrate_archetype_relationships
from ..scripts.integrate_card_attributes_relationships import (
    integrate_attribute_relationships,
    load_card_attributes,
)
from ..scripts.integrate_tournament_performance import integrate_tournament_performance
from ..scripts.integrate_format_legality import integrate_format_legality
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()


def integrate_all_data_sources(
    graph: IncrementalCardGraph,
    pack_db: PackDatabase | None = None,
    game: str | None = None,
    include_packs: bool = True,
    include_archetypes: bool = True,
    include_attributes: bool = True,
    include_tournament: bool = True,
    include_format: bool = True,
) -> dict[str, any]:
    """
    Integrate all data sources into the graph.
    
    Args:
        graph: IncrementalCardGraph instance
        pack_db: PackDatabase instance (required if include_packs=True)
        game: Filter by game
        include_packs: Include pack co-occurrence
        include_archetypes: Include archetype relationships
        include_attributes: Include card attribute relationships
        include_tournament: Include tournament performance
        include_format: Include format legality
    
    Returns:
        Combined statistics dict
    """
    logger.info("=" * 70)
    logger.info("Integrating All Data Sources into Graph")
    logger.info("=" * 70)
    
    all_stats = {}
    
    # 1. Pack co-occurrence
    if include_packs:
        if not pack_db:
            logger.warning("Pack database not provided, skipping pack integration")
        else:
            logger.info("\n" + "=" * 70)
            logger.info("1. Pack Co-occurrence")
            logger.info("=" * 70)
            pack_stats = integrate_packs_into_graph(
                graph,
                pack_db,
                game=game,
                add_pack_edges=True,
                add_pack_metadata=True,
            )
            all_stats["packs"] = pack_stats
    
    # 2. Archetype relationships
    if include_archetypes:
        logger.info("\n" + "=" * 70)
        logger.info("2. Archetype Relationships")
        logger.info("=" * 70)
        archetype_stats = integrate_archetype_relationships(
            graph,
            game=game,
            archetype_edge_weight=2,
        )
        all_stats["archetypes"] = archetype_stats
    
    # 3. Card attribute relationships
    if include_attributes:
        logger.info("\n" + "=" * 70)
        logger.info("3. Card Attribute Relationships")
        logger.info("=" * 70)
        card_attributes = load_card_attributes()
        if card_attributes:
            attribute_stats = integrate_attribute_relationships(
                graph,
                card_attributes,
                game=game,
                attribute_edge_weight=1,
            )
            all_stats["attributes"] = attribute_stats
        else:
            logger.warning("No card attributes loaded, skipping attribute integration")
    
    # 4. Tournament performance
    if include_tournament:
        logger.info("\n" + "=" * 70)
        logger.info("4. Tournament Performance")
        logger.info("=" * 70)
        tournament_stats = integrate_tournament_performance(
            graph,
            game=game,
            placement_weight_multiplier=1.5,
        )
        all_stats["tournament"] = tournament_stats
    
    # 5. Format legality
    if include_format:
        logger.info("\n" + "=" * 70)
        logger.info("5. Format Legality")
        logger.info("=" * 70)
        format_stats = integrate_format_legality(
            graph,
            game=game,
            format_edge_weight=1,
        )
        all_stats["format"] = format_stats
    
    logger.info("\n" + "=" * 70)
    logger.info("Integration Complete")
    logger.info("=" * 70)
    
    # Summary
    total_edges_created = sum(
        s.get("pack_edges_added", 0) + s.get("archetype_edges_created", 0) +
        s.get("total_edges_created", 0) + s.get("format_edges_created", 0)
        for s in all_stats.values()
    )
    total_edges_updated = sum(
        s.get("pack_edges_updated", 0) + s.get("archetype_edges_updated", 0) +
        s.get("total_edges_updated", 0) + s.get("format_edges_updated", 0) +
        s.get("performance_edges_updated", 0)
        for s in all_stats.values()
    )
    
    logger.info(f"Total edges created: {total_edges_created:,}")
    logger.info(f"Total edges updated: {total_edges_updated:,}")
    
    return all_stats


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Integrate all data sources")
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
        "--no-packs",
        action="store_true",
        help="Skip pack integration",
    )
    parser.add_argument(
        "--no-archetypes",
        action="store_true",
        help="Skip archetype integration",
    )
    parser.add_argument(
        "--no-attributes",
        action="store_true",
        help="Skip attribute integration",
    )
    parser.add_argument(
        "--no-tournament",
        action="store_true",
        help="Skip tournament integration",
    )
    parser.add_argument(
        "--no-format",
        action="store_true",
        help="Skip format integration",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("Integrate All Data Sources")
    logger.info("=" * 70)
    
    # Load graph
    graph = IncrementalCardGraph(
        graph_path=args.graph_db,
        use_sqlite=True,
    )
    
    # Load pack database if needed
    pack_db = None
    if not args.no_packs:
        pack_db = PackDatabase(args.pack_db)
    
    # Integrate all sources
    results = integrate_all_data_sources(
        graph,
        pack_db=pack_db,
        game=args.game,
        include_packs=not args.no_packs,
        include_archetypes=not args.no_archetypes,
        include_attributes=not args.no_attributes,
        include_tournament=not args.no_tournament,
        include_format=not args.no_format,
    )
    
    # Save graph
    logger.info("\nSaving graph...")
    graph.save_sqlite(args.graph_db)
    
    logger.info(f"\n✓ All integrations complete")
    logger.info(f"✓ Results: {results}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

