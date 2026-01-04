#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas", "numpy"]
# ///
"""
Migrate existing JSON graph to SQLite format.

Converts data/graphs/incremental_graph.json to data/graphs/incremental_graph.db
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate graph from JSON to SQLite")
    from ml.utils.paths import PATHS
    
    parser.add_argument(
        "--json-path",
        type=Path,
        default=PATHS.incremental_graph_json,
        help="Path to JSON graph file",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=PATHS.incremental_graph_db,
        help="Path to SQLite database file",
    )
    parser.add_argument(
        "--keep-json",
        action="store_true",
        help="Keep JSON file after migration",
    )
    
    args = parser.parse_args()
    
    if not args.json_path.exists():
        logger.error(f"JSON graph not found: {args.json_path}")
        return 1
    
    logger.info(f"Loading graph from {args.json_path}...")
    
    from ml.data.incremental_graph import IncrementalCardGraph
    
    # Load from JSON
    graph = IncrementalCardGraph(graph_path=args.json_path, use_sqlite=False)
    
    logger.info(f"Loaded: {len(graph.nodes):,} nodes, {len(graph.edges):,} edges")
    
    if len(graph.nodes) == 0 and len(graph.edges) == 0:
        logger.warning("Graph is empty. Nothing to migrate.")
        return 0
    
    # Save to SQLite
    logger.info(f"Saving to SQLite: {args.db_path}...")
    db_path = args.db_path
    if db_path.suffix != ".db":
        db_path = db_path.with_suffix(".db")
    
    # Create new graph with SQLite backend
    graph_sqlite = IncrementalCardGraph(graph_path=db_path, use_sqlite=True)
    
    # Copy all nodes and edges
    logger.info("Copying nodes...")
    for name, node in graph.nodes.items():
        graph_sqlite.nodes[name] = node
    
    logger.info("Copying edges...")
    for key, edge in graph.edges.items():
        graph_sqlite.edges[key] = edge
    
    graph_sqlite.last_update = graph.last_update
    graph_sqlite.total_decks_processed = graph.total_decks_processed
    
    # Save to SQLite
    graph_sqlite.save()
    
    logger.info("Migration complete!")
    
    # Verify
    logger.info("Verifying SQLite database...")
    graph2 = IncrementalCardGraph(graph_path=db_path, use_sqlite=True)
    logger.info(f"Verified: {len(graph2.nodes):,} nodes, {len(graph2.edges):,} edges")
    
    if len(graph2.nodes) != len(graph.nodes) or len(graph2.edges) != len(graph.edges):
        logger.error("Migration verification failed: counts don't match")
        return 1
    
    if not args.keep_json:
        logger.info(f"Removing JSON file: {args.json_path}")
        args.json_path.unlink()
    
    logger.info("Migration successful!")
    return 0


if __name__ == "__main__":
    sys.exit(main())

