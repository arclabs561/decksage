#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
#     "numpy<2.0.0",
#     "pecanpy>=2.0.0",
#     "gensim>=4.3.0",
# ]
# ///
"""
Enhanced embedding training with validation, early stopping, and learning rate scheduling.

Based on research:
- Validation split prevents overfitting
- Early stopping saves compute
- Learning rate scheduling improves convergence
- Checkpointing enables resume from failures
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

try:
    import pandas as pd
    import numpy as np
    from gensim.models import Word2Vec, KeyedVectors
    from pecanpy.pecanpy import SparseOTF
    
    HAS_DEPS = True
except ImportError as e:
    HAS_DEPS = False
    print(f"Missing dependencies: {e}")

try:
    from ml.utils.aim_helpers import create_training_run, track_training_metrics
    HAS_AIM = True
except ImportError:
    HAS_AIM = False
    create_training_run = None
    track_training_metrics = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def prepare_edgelist_with_split(
    csv_file: Path,
    train_edg: Path,
    val_edg: Path,
    test_edg: Path,
    train_ratio: float = 0.8,
    val_ratio: float = 0.1,
    min_cooccurrence: int = 2,
) -> tuple[int, int, int]:
    """Split edgelist into train/val/test."""
    df = pd.read_csv(csv_file)
    df = df[df["COUNT_SET"] >= min_cooccurrence]
    
    # Shuffle
    df = df.sample(frac=1, random_state=42).reset_index(drop=True)
    
    # Split
    n = len(df)
    train_end = int(n * train_ratio)
    val_end = train_end + int(n * val_ratio)
    
    train_df = df[:train_end]
    val_df = df[train_end:val_end]
    test_df = df[val_end:]
    
    # Write splits
    for split_df, split_path in [(train_df, train_edg), (val_df, val_edg), (test_df, test_edg)]:
        with open(split_path, "w") as f:
            for _, row in split_df.iterrows():
                f.write(f"{row['NAME_1']}\t{row['NAME_2']}\t{row['COUNT_MULTISET']}\n")
    
    num_nodes = len(set(df["NAME_1"]) | set(df["NAME_2"]))
    return len(train_df), len(val_df), len(test_df)


def train_with_validation(
    train_edg: Path,
    val_edg: Path,
    dim: int,
    walk_length: int,
    num_walks: int,
    window_size: int,
    p: float,
    q: float,
    epochs: int,
    workers: int = 4,
    early_stopping_patience: int = 3,
    lr_initial: float = 0.025,
    lr_decay: float = 0.95,
    checkpoint_dir: Path | None = None,
    checkpoint_interval: int = 1,
    val_test_set: dict[str, dict[str, Any]] | None = None,
    val_test_set_path: Path | None = None,
) -> KeyedVectors:
    """
    Train embedding with validation and early stopping.
    
    Now validates on similarity task (not just node overlap) if val_test_set provided.
    """
    # Load validation graph for evaluation (still used for graph structure)
    val_graph = SparseOTF(p=p, q=q, workers=workers, verbose=False, extend=True)
    val_graph.read_edg(str(val_edg), weighted=True, directed=False)
    
    # Train graph
    train_graph = SparseOTF(p=p, q=q, workers=workers, verbose=False, extend=True)
    train_graph.read_edg(str(train_edg), weighted=True, directed=False)
    
    # Load validation test set if provided
    if val_test_set is None and val_test_set_path and val_test_set_path.exists():
        import json
        with open(val_test_set_path) as f:
            data = json.load(f)
        val_test_set = data.get("queries", data) if isinstance(data, dict) else data
        logger.info(f"Loaded validation test set: {len(val_test_set)} queries")
    
    best_score = -1.0
    best_wv = None
    patience_counter = 0
    current_lr = lr_initial
    
    # Initialize Aim tracking
    aim_run = None
    if HAS_AIM and create_training_run:
        aim_run = create_training_run(
            experiment_name="embedding_training",
            hparams={
                "dim": dim,
                "walk_length": walk_length,
                "num_walks": num_walks,
                "window_size": window_size,
                "p": p,
                "q": q,
                "epochs": epochs,
                "patience": early_stopping_patience,
                "lr_initial": lr_initial,
                "lr_decay": lr_decay if 'lr_decay' in locals() else 1.0,
            },
            tags=["training", "node2vec", "validation"],
        )
    
    logger.info(f"Training with validation (patience={early_stopping_patience})...")
    
    for epoch in range(epochs):
        logger.info(f"Epoch {epoch + 1}/{epochs} (lr={current_lr:.4f})...")
        
        # Generate walks
        walks = train_graph.simulate_walks(num_walks=num_walks, walk_length=walk_length)
        
        # Train model
        model = Word2Vec(
            walks,
            vector_size=dim,
            window=window_size,
            min_count=0,
            sg=1,
            workers=workers,
            epochs=1,  # One epoch per iteration
            alpha=current_lr,
        )
        
        # Evaluate on validation set
        # Option 1: Use similarity task if test set provided (BETTER)
        # Option 2: Fall back to node overlap (LEGACY)
        if val_test_set:
            # Validate on similarity task (what we actually care about)
            try:
                # Fix import path for runctl execution
                import sys
                from pathlib import Path as P
                script_dir = P(__file__).parent
                src_dir = script_dir.parent.parent
                if str(src_dir) not in sys.path:
                    sys.path.insert(0, str(src_dir))
                
                from ml.utils.evaluation import evaluate_similarity
                
                def similarity_func(query: str, k: int) -> list[tuple[str, float]]:
                    """Similarity function using current model."""
                    if query not in model.wv:
                        return []
                    similar = model.wv.most_similar(query, topn=k)
                    return similar
                
                val_metrics = evaluate_similarity(val_test_set, similarity_func, top_k=10, verbose=False)
                val_score = val_metrics.get("p@10", 0.0)
                val_mrr = val_metrics.get("mrr@10", 0.0)
                logger.info(f"  Validation score: P@10={val_score:.4f}, MRR={val_mrr:.4f} (similarity task)")
            except Exception as e:
                logger.warning(f"  Failed to evaluate on similarity task: {e}, falling back to node overlap")
                # Fallback to node overlap
                val_nodes = set(val_graph.nodes) if hasattr(val_graph, 'nodes') and isinstance(val_graph.nodes, list) else set()
                train_nodes = set(model.wv.key_to_index.keys())
                overlap = len(val_nodes & train_nodes)
                val_score = overlap / len(val_nodes) if val_nodes else 0.0
                logger.info(f"  Validation score: {val_score:.4f} (overlap: {overlap}/{len(val_nodes)}) [LEGACY]")
        else:
            # Legacy: node overlap (not ideal, but works)
            val_nodes = set(val_graph.nodes) if hasattr(val_graph, 'nodes') and isinstance(val_graph.nodes, list) else set()
            train_nodes = set(model.wv.key_to_index.keys())
            overlap = len(val_nodes & train_nodes)
            val_score = overlap / len(val_nodes) if val_nodes else 0.0
            logger.info(f"  Validation score: {val_score:.4f} (overlap: {overlap}/{len(val_nodes)}) [LEGACY - use --val-test-set for similarity validation]")
        
        # Track metrics in Aim
        if aim_run and track_training_metrics:
            track_training_metrics(
                aim_run,
                epoch=epoch,
                val_loss=None,  # We don't have loss, only overlap score
                val_p10=val_score,
                learning_rate=current_lr,
            )
        
        # Checkpoint (for runctl compatibility)
        if checkpoint_dir and (epoch + 1) % checkpoint_interval == 0:
            checkpoint_dir.mkdir(parents=True, exist_ok=True)
            checkpoint_path = checkpoint_dir / f"checkpoint_epoch_{epoch + 1}.wv"
            model.wv.save(str(checkpoint_path))
            logger.info(f"  💾 Checkpoint saved: {checkpoint_path}")
        
        # Early stopping
        if val_score > best_score:
            best_score = val_score
            best_wv = model.wv
            patience_counter = 0
            logger.info(f"  ✅ New best score: {best_score:.4f}")
        else:
            patience_counter += 1
            logger.info(f"  ⏳ No improvement ({patience_counter}/{early_stopping_patience})")
            
            if patience_counter >= early_stopping_patience:
                logger.info(f"Early stopping at epoch {epoch + 1}")
                break
        
        # Learning rate decay
        current_lr *= lr_decay
    
    if best_wv is None:
        logger.warning("No valid model found, using last model")
        best_wv = model.wv
    
    logger.info(f"✅ Training complete! Best validation score: {best_score:.4f}")
    
    return best_wv


def main() -> int:
    """Train embeddings with validation and early stopping."""
    parser = argparse.ArgumentParser(description="Train embeddings with validation")
    parser.add_argument("--input", type=str, required=True, help="Pairs CSV")
    parser.add_argument("--output", type=str, required=True, help="Output embeddings")
    parser.add_argument("--dim", type=int, default=128, help="Embedding dimension")
    parser.add_argument("--walk-length", type=int, default=80, help="Walk length")
    parser.add_argument("--num-walks", type=int, default=10, help="Number of walks per node")
    parser.add_argument("--window-size", type=int, default=10, help="Window size")
    parser.add_argument("--p", type=float, default=1.0, help="Return parameter")
    parser.add_argument("--q", type=float, default=1.0, help="In-out parameter")
    parser.add_argument("--epochs", type=int, default=10, help="Max epochs")
    parser.add_argument("--patience", type=int, default=3, help="Early stopping patience")
    parser.add_argument("--lr", type=float, default=0.025, help="Initial learning rate")
    parser.add_argument("--lr-decay", type=float, default=0.95, help="Learning rate decay")
    parser.add_argument("--checkpoint-dir", type=str, help="Checkpoint directory (for runctl compatibility)")
    parser.add_argument("--checkpoint-interval", type=int, default=1, help="Save checkpoint every N epochs")
    parser.add_argument("--train-ratio", type=float, default=0.8, help="Train split ratio")
    parser.add_argument("--val-ratio", type=float, default=0.1, help="Validation split ratio")
    parser.add_argument("--val-test-set", type=str, help="Path to test set JSON for similarity-based validation (recommended)")
    
    args = parser.parse_args()
    
    if not HAS_DEPS:
        logger.error("Missing dependencies")
        return 1
    
    input_path = Path(args.input)
    output_path = Path(args.output)
    
    # Prepare splits
    work_dir = Path("/tmp/training_with_validation")
    work_dir.mkdir(exist_ok=True)
    
    train_edg = work_dir / "train.edg"
    val_edg = work_dir / "val.edg"
    test_edg = work_dir / "test.edg"
    
    logger.info("Preparing train/val/test splits...")
    train_size, val_size, test_size = prepare_edgelist_with_split(
        input_path,
        train_edg,
        val_edg,
        test_edg,
        args.train_ratio,
        args.val_ratio,
    )
    logger.info(f"Splits: train={train_size}, val={val_size}, test={test_size}")
    
    # Load validation test set if provided
    val_test_set = None
    val_test_set_path = None
    if args.val_test_set:
        val_test_set_path = Path(args.val_test_set)
        if not val_test_set_path.exists():
            logger.warning(f"Validation test set not found: {val_test_set_path}, using node overlap validation")
        else:
            logger.info(f"Using similarity-based validation with test set: {val_test_set_path}")
    
    # Train with validation
    checkpoint_dir = Path(args.checkpoint_dir) if args.checkpoint_dir else None
    wv = train_with_validation(
        train_edg,
        val_edg,
        args.dim,
        args.walk_length,
        args.num_walks,
        args.window_size,
        args.p,
        args.q,
        args.epochs,
        early_stopping_patience=args.patience,
        lr_initial=args.lr,
        lr_decay=args.lr_decay,
        checkpoint_dir=checkpoint_dir,
        checkpoint_interval=args.checkpoint_interval,
        val_test_set=val_test_set,
        val_test_set_path=val_test_set_path,
    )
    
    # Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wv.save(str(output_path))
    
    logger.info(f"✅ Embeddings saved to {output_path}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

