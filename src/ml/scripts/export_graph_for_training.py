#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas", "numpy", "pyarrow"]
# ///
"""
Export graph to Parquet format for training workloads.

This script exports the incremental graph to Parquet files that can be
efficiently loaded for training embeddings or GNN models.
"""

import argparse
import logging
import sys
from pathlib import Path
from ml.utils.logging_config import setup_script_logging

# Add src to path for local imports
script_dir = Path(__file__).parent
src_dir = script_dir.parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

logger = setup_script_logging()


def export_graph_for_training(
    graph_path: Path,
    output_dir: Path,
    game: str | None = None,
    min_weight: int = 2,
    use_sqlite: bool = True,
) -> int:
    """
    Export graph to Parquet format for training.
    
    Args:
        graph_path: Path to graph (JSON or SQLite)
        output_dir: Directory to save Parquet files
        game: Filter by game ("MTG", "PKM", "YGO")
        min_weight: Minimum edge weight to include
        use_sqlite: Whether graph is stored in SQLite
    """
    from ml.data.incremental_graph import IncrementalCardGraph
    
    logger.info(f"Loading graph from {graph_path}...")
    
    # Load graph
    if use_sqlite and graph_path.suffix == ".db":
        graph = IncrementalCardGraph(graph_path=graph_path, use_sqlite=True)
    else:
        graph = IncrementalCardGraph(graph_path=graph_path, use_sqlite=False)
    
    logger.info(f"Loaded: {len(graph.nodes):,} nodes, {len(graph.edges):,} edges")
    
    # Filter edges if needed
    if game or min_weight > 1:
        logger.info(f"Filtering edges: game={game}, min_weight={min_weight}")
        filtered_edges = graph.query_edges(game=game, min_weight=min_weight)
        logger.info(f"  Filtered to {len(filtered_edges):,} edges")
        
        # Create temporary graph with filtered edges
        filtered_graph = IncrementalCardGraph(use_sqlite=False)
        filtered_graph.nodes = graph.nodes.copy()
        for edge in filtered_edges:
            edge_key = tuple(sorted([edge.card1, edge.card2]))
            filtered_graph.edges[edge_key] = edge
        graph = filtered_graph
    
    # Export to Parquet
    logger.info(f"Exporting to Parquet: {output_dir}...")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    paths = graph.export_parquet(output_dir)
    
    logger.info("Export complete!")
    logger.info(f"  Nodes: {paths['nodes']}")
    logger.info(f"  Edges: {paths['edges']}")
    
    # Print file sizes
    for name, path in paths.items():
        if path.exists():
            size_mb = path.stat().st_size / (1024 * 1024)
            logger.info(f"  {name}: {size_mb:.2f} MB")
    
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Export graph to Parquet for training")
    from ml.utils.paths import PATHS
    
    parser.add_argument(
        "--graph-path",
        type=Path,
        default=PATHS.incremental_graph_db,
        help="Path to graph file (JSON or SQLite)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PATHS.graphs / "parquet_export",
        help="Directory to save Parquet files",
    )
    parser.add_argument(
        "--game",
        type=str,
        choices=["MTG", "PKM", "YGO"],
        help="Filter by game",
    )
    parser.add_argument(
        "--min-weight",
        type=int,
        default=2,
        help="Minimum edge weight to include",
    )
    parser.add_argument(
        "--use-sqlite",
        action="store_true",
        default=True,
        help="Use SQLite storage (default: True)",
    )
    parser.add_argument(
        "--no-sqlite",
        dest="use_sqlite",
        action="store_false",
        help="Use JSON storage instead of SQLite",
    )
    
    args = parser.parse_args()
    
    if not args.graph_path.exists():
        logger.error(f"Graph file not found: {args.graph_path}")
        return 1
    
    return export_graph_for_training(
        graph_path=args.graph_path,
        output_dir=args.output_dir,
        game=args.game,
        min_weight=args.min_weight,
        use_sqlite=args.use_sqlite,
    )


if __name__ == "__main__":
    sys.exit(main())
