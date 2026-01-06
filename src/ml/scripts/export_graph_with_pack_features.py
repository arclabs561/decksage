#!/usr/bin/env python3
"""
Export graph with pack features for GNN training.

Exports edgelist with pack co-occurrence metadata as edge features.
This allows GNN to use pack information during training.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..data.incremental_graph import IncrementalCardGraph
from ..data.pack_database import PackDatabase
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()


def export_graph_with_pack_features(
    graph: IncrementalCardGraph,
    pack_db: PackDatabase,
    output_path: Path,
    game: str | None = None,
    min_weight: int = 1,
    include_pack_metadata: bool = True,
) -> dict[str, int]:
    """
    Export graph edgelist with pack features.
    
    Args:
        graph: IncrementalCardGraph instance
        pack_db: PackDatabase instance
        output_path: Path to output edgelist file
        game: Filter by game
        min_weight: Minimum edge weight to include
        include_pack_metadata: Include pack co-occurrence metadata
    
    Returns:
        Statistics dict
    """
    logger.info("Exporting graph with pack features...")
    
    # Ensure graph is loaded
    if graph.use_sqlite and not graph.nodes:
        logger.info("Loading graph into memory...")
        graph.load_sqlite(graph.graph_path)
    
    stats = {
        "edges_exported": 0,
        "edges_with_packs": 0,
        "edges_without_packs": 0,
    }
    
    # Export edgelist with pack features
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w") as f:
        for edge_key, edge in graph.edges.items():
            # Filter by game
            if game and edge.game != game:
                continue
            
            # Filter by weight
            if edge.weight < min_weight:
                continue
            
            # Get pack co-occurrence info
            pack_info = None
            if include_pack_metadata and edge.metadata:
                pack_co_occs = edge.metadata.get("pack_co_occurrences", [])
                if pack_co_occs:
                    pack_info = {
                        "pack_count": len(pack_co_occs),
                        "pack_types": list(set(p.get("pack_type") for p in pack_co_occs if p.get("pack_type"))),
                        "latest_release": max(
                            (p.get("release_date") for p in pack_co_occs if p.get("release_date")),
                            default=None
                        ),
                    }
                    stats["edges_with_packs"] += 1
                else:
                    stats["edges_without_packs"] += 1
            else:
                stats["edges_without_packs"] += 1
            
            # Write edge in edgelist format
            # Format: card1 card2 weight [pack_features]
            line_parts = [edge.card1, edge.card2, str(edge.weight)]
            
            if pack_info:
                # Add pack features as JSON string
                pack_features = json.dumps(pack_info)
                line_parts.append(pack_features)
            
            f.write("\t".join(line_parts) + "\n")
            stats["edges_exported"] += 1
    
    logger.info(f"Exported {stats['edges_exported']} edges")
    logger.info(f"  With pack features: {stats['edges_with_packs']}")
    logger.info(f"  Without pack features: {stats['edges_without_packs']}")
    
    return stats


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Export graph with pack features")
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
        "--output",
        type=Path,
        default=PATHS.graphs / "graph_with_packs.edg",
        help="Path to output edgelist",
    )
    parser.add_argument(
        "--game",
        choices=["MTG", "PKM", "YGO"],
        help="Filter by game",
    )
    parser.add_argument(
        "--min-weight",
        type=int,
        default=1,
        help="Minimum edge weight to include",
    )
    parser.add_argument(
        "--no-pack-metadata",
        action="store_true",
        help="Don't include pack metadata",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("Export Graph with Pack Features")
    logger.info("=" * 70)
    
    # Load graph
    logger.info(f"Loading graph from {args.graph_db}...")
    graph = IncrementalCardGraph(
        graph_path=args.graph_db,
        use_sqlite=True,
    )
    
    # Load pack database (for validation, not used in export)
    pack_db = PackDatabase(args.pack_db)
    
    # Export
    results = export_graph_with_pack_features(
        graph,
        pack_db,
        output_path=args.output,
        game=args.game,
        min_weight=args.min_weight,
        include_pack_metadata=not args.no_pack_metadata,
    )
    
    logger.info(f"\n✓ Exported to {args.output}")
    logger.info(f"✓ Results: {results}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

