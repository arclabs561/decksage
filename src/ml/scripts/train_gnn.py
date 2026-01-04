#!/usr/bin/env python3
"""
Train GraphSAGE model for card similarity (based on expert guidance).

Note: For AWS/cloud training, use train_gnn_with_runctl.py instead.
This script is for local-only training.

Uses:
- GraphSAGE (best for co-occurrence graphs)
- Shallow architecture (2 layers)
- Link prediction training objective
- Proper node features (attributes if available)
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from ..similarity.gnn_embeddings import CardGNNEmbedder
from ..utils.paths import PATHS
from ..utils.logging_config import setup_script_logging, log_exception

logger = setup_script_logging()


def main():
    parser = argparse.ArgumentParser(description="Train GraphSAGE for card similarity")
    parser.add_argument(
        "--pairs-csv",
        type=str,
        default=None,
        help="Path to pairs CSV (default: PATHS.pairs_large)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output path for model (default: experiments/signals/gnn_graphsage.json)",
    )
    parser.add_argument(
        "--model-type",
        type=str,
        default="GraphSAGE",
        choices=["GraphSAGE", "GCN", "GAT"],
        help="GNN model type (default: GraphSAGE per expert guidance)",
    )
    parser.add_argument(
        "--hidden-dim",
        type=int,
        default=128,
        help="Hidden dimension (default: 128)",
    )
    parser.add_argument(
        "--num-layers",
        type=int,
        default=2,
        help="Number of layers (default: 2, keep shallow per expert guidance)",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=100,
        help="Training epochs (default: 100)",
    )
    parser.add_argument(
        "--lr",
        type=float,
        default=0.01,
        help="Learning rate (default: 0.01)",
    )

    args = parser.parse_args()

    # Determine input path
    if args.pairs_csv:
        pairs_path = Path(args.pairs_csv)
    else:
        pairs_path = PATHS.pairs_large

    if not pairs_path.exists():
        logger.error(f"Pairs CSV not found: {pairs_path}")
        logger.info("Available paths:")
        logger.info(f"  - {PATHS.pairs_large}")
        logger.info(f"  - {PATHS.pairs_500}")
        return 1

    # Convert CSV to edgelist if needed
    import pandas as pd
    edgelist_path = PATHS.graphs / f"{pairs_path.stem}.edg"
    edgelist_path.parent.mkdir(parents=True, exist_ok=True)
    
    if not edgelist_path.exists():
        logger.info(f"Converting {pairs_path} to edgelist format...")
        df = pd.read_csv(pairs_path)
        with open(edgelist_path, "w") as f:
            for _, row in df.iterrows():
                card1 = row["NAME_1"]
                card2 = row["NAME_2"]
                weight = row.get("COUNT_MULTISET", 1)
                f.write(f"{card1} {card2} {weight}\n")
        logger.info(f"✓ Created edgelist: {edgelist_path}")

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = PATHS.experiments / "signals" / f"gnn_{args.model_type.lower()}.json"
    
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Train model
    logger.info(f"Training {args.model_type} model...")
    logger.info(f"  Input: {edgelist_path}")
    logger.info(f"  Output: {output_path}")
    logger.info(f"  Hidden dim: {args.hidden_dim}")
    logger.info(f"  Layers: {args.num_layers}")
    logger.info(f"  Epochs: {args.epochs}")
    logger.info(f"  Learning rate: {args.lr}")

    embedder = CardGNNEmbedder(
        model_type=args.model_type,
        hidden_dim=args.hidden_dim,
        num_layers=args.num_layers,
    )

    try:
        embedder.train(
            edgelist_path,
            epochs=args.epochs,
            lr=args.lr,
            output_path=output_path,
        )
        logger.info(f"✓ Training complete! Model saved to: {output_path}")
        return 0
    except Exception as e:
        log_exception(logger, "Training failed", e, include_context=True)
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())

