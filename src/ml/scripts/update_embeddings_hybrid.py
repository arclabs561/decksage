#!/usr/bin/env python3
"""
Hybrid Embedding Update Pipeline

Updates all embedding types:
1. Co-occurrence embeddings (Node2Vec) - weekly retraining
2. Instruction-tuned embeddings (E5) - no retraining needed (zero-shot)
3. GNN embeddings (GraphSAGE) - incremental updates + weekly retraining

Supports daily/weekly/monthly update schedules.
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path

from ..data.incremental_graph import IncrementalCardGraph
from ..similarity.gnn_embeddings import CardGNNEmbedder
from ..similarity.instruction_tuned_embeddings import InstructionTunedCardEmbedder
from ..utils.paths import PATHS
from ..utils.logging_config import setup_script_logging

logger = setup_script_logging()


def update_gnn_embeddings(
    graph: IncrementalCardGraph,
    gnn_model_path: Path,
    new_cards: list[str] | None = None,
    retrain: bool = False,
    text_embedder: InstructionTunedCardEmbedder | None = None,
) -> CardGNNEmbedder:
    """
    Update GNN embeddings with new cards or retrain.
    
    Args:
        graph: Incremental graph database
        gnn_model_path: Path to GNN model
        new_cards: List of new cards to add incrementally
        retrain: Whether to retrain on full graph
        text_embedder: Fallback embedder for isolated cards
    
    Returns:
        Updated GNN embedder
    """
    # Load or create embedder
    if gnn_model_path.exists():
        logger.info(f"Loading existing GNN model: {gnn_model_path}")
        embedder = CardGNNEmbedder(model_path=gnn_model_path)
    else:
        logger.info("Creating new GNN embedder")
        embedder = CardGNNEmbedder(model_type="GraphSAGE", hidden_dim=128, num_layers=2)
    
    if retrain:
        # Full retraining on updated graph
        logger.info("Retraining GNN on full graph...")
        edgelist_path = graph.export_edgelist(
            PATHS.data / "graphs" / "temp_edgelist.edg",
            min_weight=2,
        )
        embedder.train(
            edgelist_path,
            epochs=100,
            output_path=gnn_model_path,
        )
        logger.info("✓ GNN retrained")
    elif new_cards:
        # Incremental update for new cards
        logger.info(f"Adding {len(new_cards)} new cards incrementally...")
        embedder.add_new_cards(new_cards, graph, fallback_embedder=text_embedder)
        embedder.save(gnn_model_path)
        logger.info("✓ New cards added")
    
    return embedder


def update_all_embeddings(
    graph_path: Path,
    schedule: str = "daily",
    gnn_model_path: Path | None = None,
    instruction_model_path: Path | None = None,
) -> dict[str, Any]:
    """
    Update all embedding types based on schedule.
    
    Args:
        graph_path: Path to incremental graph
        schedule: "daily", "weekly", or "monthly"
        gnn_model_path: Path to GNN model
        instruction_model_path: Path to instruction-tuned model (for caching)
    
    Returns:
        Update summary
    """
    logger.info(f"Updating embeddings ({schedule} schedule)...")
    
    # Load graph
    graph = IncrementalCardGraph(graph_path)
    stats = graph.get_statistics()
    logger.info(f"Graph: {stats['num_nodes']} nodes, {stats['num_edges']} edges")
    
    # Initialize instruction-tuned embedder (no retraining needed)
    logger.info("Initializing instruction-tuned embedder...")
    text_embedder = InstructionTunedCardEmbedder()
    logger.info("✓ Instruction-tuned embedder ready (zero-shot, no retraining needed)")
    
    # Update GNN embeddings
    if gnn_model_path is None:
        gnn_model_path = PATHS.embeddings / "gnn_graphsage.json"
    
    gnn_embedder = None
    if schedule in ["weekly", "monthly"]:
        # Retrain GNN
        logger.info(f"Retraining GNN ({schedule} schedule)...")
        gnn_embedder = update_gnn_embeddings(
            graph=graph,
            gnn_model_path=gnn_model_path,
            retrain=True,
            text_embedder=text_embedder,
        )
    elif schedule == "daily":
        # Incremental update
        since = datetime.now() - timedelta(days=1)
        new_cards = graph.get_new_cards_since(since)
        if new_cards:
            logger.info(f"Updating GNN with {len(new_cards)} new cards...")
            gnn_embedder = update_gnn_embeddings(
                graph=graph,
                gnn_model_path=gnn_model_path,
                new_cards=new_cards,
                text_embedder=text_embedder,
            )
        else:
            logger.info("No new cards, skipping GNN update")
    
    # Co-occurrence embeddings (Node2Vec) - only retrain weekly/monthly
    cooccurrence_updated = False
    if schedule in ["weekly", "monthly"]:
        logger.info("Co-occurrence embeddings require manual retraining")
        logger.info("  Run: python -m ml.scripts.train_embeddings_pecanpy")
        cooccurrence_updated = False
    
    return {
        "schedule": schedule,
        "graph_nodes": stats["num_nodes"],
        "graph_edges": stats["num_edges"],
        "gnn_updated": gnn_embedder is not None,
        "instruction_ready": True,  # Always ready (zero-shot)
        "cooccurrence_updated": cooccurrence_updated,
        "timestamp": datetime.now().isoformat(),
    }


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Update all embedding types (hybrid approach)"
    )
    parser.add_argument(
        "--graph-path",
        type=Path,
        default=PATHS.data / "graphs" / "incremental_graph.db",
        help="Path to incremental graph database",
    )
    parser.add_argument(
        "--schedule",
        choices=["daily", "weekly", "monthly"],
        default="daily",
        help="Update schedule",
    )
    parser.add_argument(
        "--gnn-model",
        type=Path,
        help="Path to GNN model (default: data/embeddings/gnn_graphsage.json)",
    )
    
    args = parser.parse_args()
    
    summary = update_all_embeddings(
        graph_path=args.graph_path,
        schedule=args.schedule,
        gnn_model_path=args.gnn_model,
    )
    
    logger.info("\n" + "="*60)
    logger.info("Update Summary")
    logger.info("="*60)
    for key, value in summary.items():
        logger.info(f"  {key}: {value}")
    
    return 0


if __name__ == "__main__":
    exit(main())

