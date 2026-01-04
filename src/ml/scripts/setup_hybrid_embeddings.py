#!/usr/bin/env python3
"""
Setup Hybrid Embedding System

Initializes and configures the three-layer embedding system:
1. Co-occurrence embeddings (Node2Vec)
2. Instruction-tuned embeddings (E5-base-instruct)
3. GNN embeddings (GraphSAGE)

Creates initial models and configuration.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from ..data.incremental_graph import IncrementalCardGraph
from ..similarity.gnn_embeddings import CardGNNEmbedder
from ..similarity.instruction_tuned_embeddings import InstructionTunedCardEmbedder
from ..utils.paths import PATHS
from ..utils.logging_config import setup_script_logging

logger = setup_script_logging()


def setup_instruction_tuned_embeddings(
    model_name: str = "intfloat/e5-base-instruct-v2",
) -> InstructionTunedCardEmbedder:
    """Initialize instruction-tuned embedder."""
    logger.info("Setting up instruction-tuned embeddings...")
    logger.info(f"  Model: {model_name}")
    embedder = InstructionTunedCardEmbedder(model_name=model_name)
    logger.info("✓ Instruction-tuned embedder ready")
    return embedder


def setup_gnn_embeddings(
    graph_path: Path,
    gnn_model_path: Path,
    model_type: str = "GraphSAGE",
    hidden_dim: int = 128,
    num_layers: int = 2,
) -> CardGNNEmbedder | None:
    """Initialize GNN embedder from graph."""
    logger.info("Setting up GNN embeddings...")
    
    if not graph_path.exists():
        logger.warning(f"Graph not found: {graph_path}")
        logger.warning("  Run update_graph_incremental.py first")
        return None
    
    graph = IncrementalCardGraph(graph_path)
    if len(graph.nodes) == 0:
        logger.warning("Graph is empty")
        return None
    
    logger.info(f"  Graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges")
    logger.info(f"  Model type: {model_type}")
    
    # Export edgelist
    edgelist_path = graph.export_edgelist(
        PATHS.data / "graphs" / "temp_edgelist.edg",
        min_weight=2,
    )
    
    # Train GNN
    embedder = CardGNNEmbedder(
        model_type=model_type,
        hidden_dim=hidden_dim,
        num_layers=num_layers,
    )
    
    logger.info("Training GNN (this may take a while)...")
    embedder.train(
        edgelist_path,
        epochs=100,
        output_path=gnn_model_path,
    )
    
    logger.info("✓ GNN embedder ready")
    return embedder


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Setup hybrid embedding system"
    )
    parser.add_argument(
        "--graph-path",
        type=Path,
        default=PATHS.data / "graphs" / "incremental_graph.db",
        help="Path to incremental graph",
    )
    parser.add_argument(
        "--gnn-model",
        type=Path,
        default=PATHS.embeddings / "gnn_graphsage.json",
        help="Path to save GNN model",
    )
    parser.add_argument(
        "--instruction-model",
        type=str,
        default="intfloat/e5-base-v2",
        help="Instruction-tuned model name",
    )
    parser.add_argument(
        "--skip-gnn",
        action="store_true",
        help="Skip GNN setup (use existing or setup later)",
    )
    
    args = parser.parse_args()
    
    logger.info("="*60)
    logger.info("Setting up Hybrid Embedding System")
    logger.info("="*60)
    
    # 1. Instruction-tuned embeddings (always setup - zero-shot)
    instruction_embedder = setup_instruction_tuned_embeddings(
        model_name=args.instruction_model,
    )
    
    # 2. GNN embeddings (optional, requires graph)
    gnn_embedder = None
    if not args.skip_gnn:
        gnn_embedder = setup_gnn_embeddings(
            graph_path=args.graph_path,
            gnn_model_path=args.gnn_model,
        )
    
    logger.info("\n" + "="*60)
    logger.info("Setup Complete")
    logger.info("="*60)
    logger.info("✓ Instruction-tuned embeddings: Ready (zero-shot)")
    if gnn_embedder:
        logger.info("✓ GNN embeddings: Ready")
    else:
        logger.info("⚠ GNN embeddings: Not setup (use --skip-gnn to skip)")
    logger.info("\nNext steps:")
    logger.info("  1. Use update_graph_incremental.py to add new decks")
    logger.info("  2. Use update_embeddings_hybrid.py for daily/weekly updates")
    logger.info("  3. Integrate into fusion system via API")
    
    return 0


if __name__ == "__main__":
    exit(main())

