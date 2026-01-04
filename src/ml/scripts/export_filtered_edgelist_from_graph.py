#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas",
# ]
# ///
"""
Export filtered edgelist from incremental graph for Node2Vec/PecanPy training.

Since pairs_large.csv lacks timestamps, we export edges from the graph
(which has first_seen timestamps) and filter by temporal split.

This prevents leakage by only including train/val period edges.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..data.incremental_graph import IncrementalCardGraph
from ..evaluation.cv_ablation import SplitConfig, TemporalSplitter
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS


logger = setup_script_logging()


def export_filtered_edgelist(
    graph_path: Path,
    output_path: Path,
    train_frac: float = 0.7,
    val_frac: float = 0.15,
    min_weight: int = 2,
) -> int:
    """
    Export edgelist from graph, filtered by temporal split.

    Args:
        graph_path: Path to incremental graph JSON
        output_path: Path to save filtered edgelist (.edg format)
        train_frac: Training fraction
        val_frac: Validation fraction
        min_weight: Minimum edge weight to include

    Returns:
        Exit code
    """
    logger.info("=" * 70)
    logger.info("Exporting Filtered Edgelist from Graph")
    logger.info("=" * 70)

    # Load graph
    logger.info(f"Loading graph from {graph_path}...")
    if not graph_path.exists():
        logger.error(f"Graph not found: {graph_path}")
        return 1

    graph = IncrementalCardGraph(graph_path)
    logger.info(f"  Loaded: {len(graph.nodes):,} nodes, {len(graph.edges):,} edges")

    # Apply temporal split
    logger.info("\nApplying temporal split to prevent leakage...")
    splitter = TemporalSplitter(SplitConfig(train_frac=train_frac, val_frac=val_frac))
    train_graph, val_graph, test_graph = splitter.split_graph_edges(graph)

    logger.info(f"  Train graph: {len(train_graph.edges):,} edges")
    logger.info(f"  Val graph:   {len(val_graph.edges):,} edges")
    logger.info(f"  Test graph:  {len(test_graph.edges):,} edges [EXCLUDED]")

    # Combine train + val edges
    train_val_edges = {}
    train_val_edges.update(train_graph.edges)
    train_val_edges.update(val_graph.edges)

    logger.info(f"\nTotal train+val edges: {len(train_val_edges):,}")

    # Filter by min_weight and export
    logger.info(f"\nExporting edgelist (min_weight={min_weight})...")
    exported = 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for (card1, card2), edge in train_val_edges.items():
            if edge.weight >= min_weight:
                f.write(f"{card1}\t{card2}\t{edge.weight}\n")
                exported += 1

                if exported % 100000 == 0:
                    logger.info(f"  Exported {exported:,} edges...")

    logger.info(f"✓ Exported {exported:,} edges to {output_path}")
    logger.info("  Format: node1\\tnode2\\tweight")
    logger.info("  Ready for Node2Vec/PecanPy training")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export filtered edgelist from graph for Node2Vec/PecanPy training"
    )
    parser.add_argument(
        "--graph",
        type=Path,
        default=PATHS.graphs / "incremental_graph.db",
        help="Path to incremental graph JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PATHS.graphs / "train_val_edgelist.edg",
        help="Output path for filtered edgelist",
    )
    parser.add_argument(
        "--train-frac",
        type=float,
        default=0.7,
        help="Training fraction",
    )
    parser.add_argument(
        "--val-frac",
        type=float,
        default=0.15,
        help="Validation fraction",
    )
    parser.add_argument(
        "--min-weight",
        type=int,
        default=2,
        help="Minimum edge weight to include",
    )

    args = parser.parse_args()

    return export_filtered_edgelist(
        args.graph,
        args.output,
        args.train_frac,
        args.val_frac,
        args.min_weight,
    )


if __name__ == "__main__":
    sys.exit(main())
