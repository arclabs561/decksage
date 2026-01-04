#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "torch>=2.0.0",
#     "torch-geometric>=2.4.0",
# ]
# ///
"""
Train GNN embeddings using runctl (local or AWS).

Supports:
- Local training
- AWS training with S3 data/output
- Checkpointing and resume
- Fast training with GPU
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from ..similarity.gnn_embeddings import CardGNNEmbedder
from ..utils.paths import PATHS
from ..utils.logging_config import setup_script_logging, log_exception

logger = setup_script_logging()


def train_gnn(
    edgelist_path: Path | str,
    output_path: Path | str,
    model_type: str = "GraphSAGE",
    hidden_dim: int = 128,
    num_layers: int = 2,
    epochs: int = 100,
    learning_rate: float = 0.01,
    checkpoint_interval: int | None = None,
    resume_from: Path | str | None = None,
) -> int:
    """
    Train GNN embeddings.
    
    Args:
        edgelist_path: Path to edgelist file (local or s3://)
        output_path: Path to save model (local or s3://)
        model_type: GNN model type (GraphSAGE, GCN, GAT)
        hidden_dim: Hidden dimension
        num_layers: Number of layers
        epochs: Training epochs
        learning_rate: Learning rate
        checkpoint_interval: Save checkpoint every N epochs
        resume_from: Resume from checkpoint
    
    Returns:
        Exit code
    """
    edgelist_path = Path(edgelist_path)
    output_path = Path(output_path)
    
    # Handle S3 paths (runctl should handle this, but check)
    if str(edgelist_path).startswith("s3://"):
        logger.info(f"Using S3 edgelist: {edgelist_path}")
        # runctl should sync this, but we'll note it
        edgelist_path = Path("/tmp/edgelist.edg")  # runctl syncs here
    
    if str(output_path).startswith("s3://"):
        logger.info(f"Output will be synced to S3: {output_path}")
        output_path = Path("/tmp/gnn_model.json")  # runctl syncs from here
    
    # Create embedder
    logger.info(f"Creating {model_type} embedder...")
    embedder = CardGNNEmbedder(
        model_type=model_type,
        hidden_dim=hidden_dim,
        num_layers=num_layers,
    )
    
    # Resume from checkpoint if provided
    if resume_from:
        resume_path = Path(resume_from)
        if resume_path.exists():
            logger.info(f"Resuming from checkpoint: {resume_path}")
            embedder.load(resume_path)
        else:
            logger.warning(f"Checkpoint not found: {resume_path}, starting fresh")
    
    # Train
    logger.info(f"Training on: {edgelist_path}")
    logger.info(f"  Model: {model_type}")
    logger.info(f"  Hidden dim: {hidden_dim}")
    logger.info(f"  Layers: {num_layers}")
    logger.info(f"  Epochs: {epochs}")
    
    try:
        embedder.train(
            edgelist_path,
            epochs=epochs,
            lr=learning_rate,
            output_path=output_path,
            checkpoint_interval=checkpoint_interval,
            resume_from=resume_from,
        )
        
        logger.info(f"✓ Training complete: {output_path}")
        
        # Save metadata
        metadata = {
            "model_type": model_type,
            "hidden_dim": hidden_dim,
            "num_layers": num_layers,
            "epochs": epochs,
            "learning_rate": learning_rate,
            "edgelist_path": str(edgelist_path),
        }
        
        metadata_path = output_path.parent / f"{output_path.stem}_metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)
        
        return 0
        
    except Exception as e:
        log_exception(logger, "Training failed", e, include_context=True)
        return 1


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Train GNN embeddings with runctl")
    parser.add_argument(
        "--edgelist",
        type=Path,
        required=True,
        help="Path to edgelist file (local or s3://)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output path for model (local or s3://)",
    )
    parser.add_argument(
        "--model-type",
        choices=["GraphSAGE", "GCN", "GAT"],
        default="GraphSAGE",
        help="GNN model type",
    )
    parser.add_argument(
        "--hidden-dim",
        type=int,
        default=128,
        help="Hidden dimension",
    )
    parser.add_argument(
        "--num-layers",
        type=int,
        default=2,
        help="Number of layers",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=100,
        help="Training epochs",
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=0.01,
        help="Learning rate",
    )
    parser.add_argument(
        "--checkpoint-interval",
        type=int,
        help="Save checkpoint every N epochs",
    )
    parser.add_argument(
        "--resume-from",
        type=Path,
        help="Resume from checkpoint",
    )
    
    args = parser.parse_args()
    
    return train_gnn(
        edgelist_path=args.edgelist,
        output_path=args.output,
        model_type=args.model_type,
        hidden_dim=args.hidden_dim,
        num_layers=args.num_layers,
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        checkpoint_interval=args.checkpoint_interval,
        resume_from=args.resume_from,
    )


if __name__ == "__main__":
    sys.exit(main())

