#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
# "torch>=2.0.0",
# "torch-geometric>=2.4.0",
# "gensim>=4.3.0",
# "numpy",
# "pandas",
# "sentence-transformers",
# ]
# ///
"""
Train Hybrid Embeddings from Pairs CSV

Alternative training pipeline that works with pairs_large.csv
when decks_all_final.jsonl is not available locally.

Builds graph from pairs, then trains GNN and sets up instruction-tuned.

Designed for use with runctl:
- Local: For testing
- AWS: For full training (recommended, 4-8x faster)
- Uses S3 paths for cloud training (--data-s3, --output-s3)
- Supports checkpointing for long runs (--checkpoint-interval)
- Can resume from checkpoints (--resume-from)

Primary training data: pairs_large.csv (7.5M pairs)

All progress is shown (no tail/head piping per cursor rules).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from ..data.incremental_graph import IncrementalCardGraph
from ..similarity.gnn_embeddings import CardGNNEmbedder
from ..similarity.instruction_tuned_embeddings import InstructionTunedCardEmbedder
from ..utils.logging_config import log_exception, setup_script_logging
from ..utils.paths import PATHS


logger = setup_script_logging()


def build_graph_from_pairs(
    pairs_path: Path,
    graph_path: Path,
    use_temporal_split: bool = True,
    decks_path: Path | None = None,
) -> IncrementalCardGraph:
    """
    Build incremental graph from pairs CSV.

    Args:
        pairs_path: Path to pairs CSV
        graph_path: Path to save graph
        use_temporal_split: If True, filter pairs by timestamp (requires decks_path)
        decks_path: Path to decks JSONL (to determine split point)
    """
    logger.info("=" * 70)
    logger.info("Building Graph from Pairs CSV")
    logger.info("=" * 70)

    logger.info(f"Loading pairs from {pairs_path}...")
    if not pairs_path.exists():
        raise FileNotFoundError(f"Pairs file not found: {pairs_path}")

    # Check if pairs should be filtered by timestamp
    if use_temporal_split:
        if not decks_path or not decks_path.exists():
            logger.warning("Warning: WARNING: Temporal split requested but decks_path not provided")
            logger.warning(" Pairs may include test period → potential data leakage")
            logger.warning(
                " Recommendation: Use filter_pairs_by_timestamp.py first, or provide --decks-path"
            )
    else:
        logger.info("Warning: NOTE: Pairs CSV should be pre-filtered by timestamp")
        logger.info(" Run: uv run python -m ml.scripts.filter_pairs_by_timestamp")
        logger.info(" Or pairs will include test period → potential leakage")

    # Load pairs in chunks
    # Pass card_database for game detection
    try:
        from ml.data.card_database import get_card_database

        card_db = get_card_database()
    except ImportError:
        card_db = None
        logger.warning("CardDatabase not available - game detection may be less accurate")

    use_sqlite = graph_path.suffix == ".db" if graph_path else False
    graph = IncrementalCardGraph(graph_path, use_sqlite=use_sqlite)

    chunk_size = 100000
    pair_count = 0

    logger.info("Processing pairs (optimized with vectorized operations)...")
    # OPTIMIZATION: Use vectorized operations instead of iterrows() (60-200x faster)
    from datetime import datetime

    import numpy as np

    for chunk in pd.read_csv(pairs_path, chunksize=chunk_size):
        # OPTIMIZATION: Vectorized filtering and processing
        # Get column names (handle different CSV formats)
        col0 = chunk.columns[0]
        col1 = chunk.columns[1] if len(chunk.columns) > 1 else None
        col2 = chunk.columns[2] if len(chunk.columns) > 2 else None

        # Vectorized filtering: remove invalid rows
        if col1:
            # Filter out rows with empty/invalid card names
            valid_mask = chunk[col0].notna() & chunk[col1].notna()
            valid_mask = valid_mask & (chunk[col0].astype(str).str.strip() != "")
            valid_mask = valid_mask & (chunk[col1].astype(str).str.strip() != "")
            # Filter out self-loops
            valid_mask = valid_mask & (
                chunk[col0].astype(str).str.strip() != chunk[col1].astype(str).str.strip()
            )

            filtered_chunk = chunk[valid_mask].copy()
        else:
            filtered_chunk = chunk

        if len(filtered_chunk) == 0:
            continue

        # Vectorized extraction of card names and weights
        card1s = filtered_chunk[col0].astype(str).str.strip().values
        card2s = filtered_chunk[col1].astype(str).str.strip().values if col1 else None

        if col2:
            weights = (
                pd.to_numeric(filtered_chunk[col2], errors="coerce").fillna(1).astype(int).values
            )
        else:
            weights = np.ones(len(filtered_chunk), dtype=int)

        # Process in batch (still need to call add_deck for each, but vectorized prep)
        timestamp = datetime.now()
        for i in range(len(filtered_chunk)):
            card1 = card1s[i]
            card2 = card2s[i] if card2s is not None else None
            weight = weights[i]

            if not card1 or (card2s is not None and (not card2 or card1 == card2)):
                continue

            # Create a minimal deck structure for graph.add_deck
            deck = {
                "cards": [
                    {"name": card1, "count": weight},
                    {"name": card2, "count": weight},
                ]
            }

            graph.add_deck(deck, timestamp=timestamp)
            pair_count += 1

            if pair_count % 100000 == 0:
                logger.info(f" Processed {pair_count:,} pairs...")

    logger.info(f"Processed {pair_count:,} pairs")
    graph.save()

    logger.info(f"✓ Graph built: {len(graph.nodes):,} nodes, {len(graph.edges):,} edges")
    return graph


def main() -> int:
    """Main training pipeline from pairs."""
    parser = argparse.ArgumentParser(description="Train hybrid embeddings from pairs CSV")
    parser.add_argument(
        "--pairs-path",
        type=Path,
        default=PATHS.pairs_large,
        help="Path to pairs CSV file",
    )
    parser.add_argument(
        "--graph-path",
        type=Path,
        default=PATHS.graphs / "incremental_graph.db",
        help="Path to incremental graph (SQLite .db or JSON .json)",
    )
    parser.add_argument(
        "--use-sqlite",
        action="store_true",
        default=None,  # Auto-detect from extension
        help="Use SQLite storage (auto-detected from .db extension)",
    )
    parser.add_argument(
        "--game",
        type=str,
        choices=["MTG", "PKM", "YGO"],
        default=None,
        help="Filter graph by game for training",
    )
    parser.add_argument(
        "--gnn-output",
        type=Path,
        default=PATHS.embeddings / "gnn_graphsage.json",
        help="Output path for GNN embeddings",
    )
    parser.add_argument(
        "--skip-gnn",
        action="store_true",
        help="Skip GNN training",
    )
    parser.add_argument(
        "--gnn-epochs",
        type=int,
        default=50,
        help="Number of GNN training epochs",
    )
    parser.add_argument(
        "--gnn-lr",
        type=float,
        default=0.01,
        help="GNN learning rate",
    )
    parser.add_argument(
        "--checkpoint-interval",
        type=int,
        help="Save checkpoint every N epochs (for long runs)",
    )
    parser.add_argument(
        "--resume-from",
        type=Path,
        help="Resume GNN training from checkpoint",
    )
    parser.add_argument(
        "--use-temporal-split",
        action="store_true",
        default=True,
        help="Use temporal split to prevent data leakage (default: True)",
    )
    parser.add_argument(
        "--output-version",
        type=str,
        help="Version tag for output files (e.g., 'v2024-W52' or 'v2024-12-31'). If provided, outputs will be versioned (gnn_graphsage_v{version}.json). If not provided, uses default unversioned paths.",
    )
    parser.add_argument(
        "--progress-dir",
        type=Path,
        help="Directory to save training progress (metrics, checkpoints, summaries)",
    )
    parser.add_argument(
        "--no-temporal-split",
        dest="use_temporal_split",
        action="store_false",
        help="Disable temporal split (WARNING: may cause data leakage)",
    )
    parser.add_argument(
        "--decks-path",
        type=Path,
        default=PATHS.decks_all_final,
        help="Path to decks JSONL (for temporal split validation)",
    )

    args = parser.parse_args()

    # Apply versioning to output paths if --output-version provided
    if args.output_version:
        # Use centralized path resolution for versioning
        from ..utils.path_resolution import version_path

        args.gnn_output = version_path(args.gnn_output, args.output_version)
        logger.info(f"Versioning enabled: GNN output will be {args.gnn_output}")

    try:
        # Build graph from pairs
        graph = build_graph_from_pairs(
            args.pairs_path,
            args.graph_path,
            use_temporal_split=args.use_temporal_split,
            decks_path=args.decks_path if args.use_temporal_split else None,
        )

        # Setup instruction embeddings
        logger.info("=" * 70)
        logger.info("Setting Up Instruction-Tuned Embeddings")
        logger.info("=" * 70)
        instruction_embedder = InstructionTunedCardEmbedder()
        logger.info("✓ Instruction-tuned embeddings ready")

        # Train GNN
        if not args.skip_gnn:
            logger.info("=" * 70)
            logger.info("Training GNN Embeddings")
            logger.info("=" * 70)

            edgelist_path = PATHS.graphs / "hybrid_training_edgelist.edg"
            graph.export_edgelist(edgelist_path, min_weight=2)

            gnn_embedder = CardGNNEmbedder(
                model_type="GraphSAGE",
                text_embedder=instruction_embedder,
            )

            if args.resume_from and args.resume_from.exists():
                logger.info(f"Resuming from checkpoint: {args.resume_from}")
                gnn_embedder.load(args.resume_from)

            if args.checkpoint_interval:
                logger.info(f"Checkpointing every {args.checkpoint_interval} epochs")

            gnn_embedder.train(
                edgelist_path,
                epochs=args.gnn_epochs,
                lr=args.gnn_lr,
                output_path=args.gnn_output,
                checkpoint_interval=args.checkpoint_interval,
                resume_from=args.resume_from,
            )
            logger.info("✓ GNN embeddings trained")
        else:
            logger.info("Skipping GNN training (--skip-gnn)")

        logger.info("")
        logger.info("=" * 70)
        logger.info("TRAINING COMPLETE")
        logger.info("=" * 70)
        return 0

    except Exception as e:
        log_exception(logger, "Training failed", e, include_context=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
