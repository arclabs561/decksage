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
Improved training with validation and early stopping.

Based on research:
- Validation during training is critical
- Early stopping prevents overfitting
- Learning rate scheduling helps
- Multiple epochs improve quality

Features:
- Train/validation split
- Early stopping
- Learning rate scheduling
- Evaluation during training
- Best model saving
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def split_walks(walks: list[list[str]], val_ratio: float = 0.1) -> tuple[list[list[str]], list[list[str]]]:
    """Split walks into train and validation."""
    np.random.shuffle(walks)
    split_idx = int(len(walks) * (1 - val_ratio))
    return walks[:split_idx], walks[split_idx:]


def evaluate_walks(model: Word2Vec, val_walks: list[list[str]]) -> float:
    """Evaluate model on validation walks (reconstruction loss)."""
    total_loss = 0.0
    count = 0
    
    for walk in val_walks:
        for i in range(len(walk) - 1):
            try:
                # Calculate similarity (higher is better)
                sim = model.wv.similarity(walk[i], walk[i + 1])
                loss = 1.0 - sim  # Convert to loss (lower is better)
                total_loss += loss
                count += 1
            except KeyError:
                continue
    
    return total_loss / count if count > 0 else float('inf')


def train_with_validation(
    edgelist_file: Path,
    output_file: Path,
    test_set: dict[str, dict[str, Any]] | None = None,
    name_mapper: dict[str, str] | None = None,
    dim: int = 128,
    walk_length: int = 80,
    num_walks: int = 10,
    window_size: int = 10,
    p: float = 1.0,
    q: float = 1.0,
    epochs: int = 10,
    val_ratio: float = 0.1,
    early_stopping_patience: int = 3,
    learning_rate: float = 0.025,
    min_learning_rate: float = 0.0001,
    workers: int = 4,
) -> dict[str, Any]:
    """Train with validation and early stopping."""
    logger.info("Loading graph...")
    g = SparseOTF(p=p, q=q, workers=workers, verbose=False, extend=True)
    g.read_edg(str(edgelist_file), weighted=True, directed=False)
    
    logger.info("Generating walks...")
    walks = g.simulate_walks(num_walks=num_walks, walk_length=walk_length)
    
    # Split walks
    train_walks, val_walks = split_walks(walks, val_ratio)
    logger.info(f"Split: {len(train_walks)} train, {len(val_walks)} validation walks")
    
    # Initialize model
    model = Word2Vec(
        train_walks,
        vector_size=dim,
        window=window_size,
        min_count=0,
        sg=1,
        workers=workers,
        epochs=1,  # Will train incrementally
        alpha=learning_rate,
        min_alpha=min_learning_rate,
    )
    
    # Training with validation
    best_val_loss = float('inf')
    best_model = None
    patience_counter = 0
    training_history = []
    
    logger.info("Training with validation...")
    for epoch in range(epochs):
        # Train for one epoch
        model.train(train_walks, total_examples=len(train_walks), epochs=1)
        
        # Evaluate on validation
        val_loss = evaluate_walks(model, val_walks)
        
        # Evaluate on test set if provided
        test_p10 = None
        if test_set:
            # Import evaluate_embedding function
            import sys
            from pathlib import Path
            script_dir = Path(__file__).parent
            if str(script_dir.parent.parent) not in sys.path:
                sys.path.insert(0, str(script_dir.parent.parent))
            from ml.scripts.improve_embeddings_hyperparameter_search import evaluate_embedding
            test_metrics = evaluate_embedding(model.wv, test_set, name_mapper)
            test_p10 = test_metrics.get("p@10", 0.0)
        
        training_history.append({
            "epoch": epoch + 1,
            "val_loss": val_loss,
            "test_p10": test_p10,
        })
        
        logger.info(f"Epoch {epoch + 1}/{epochs}: val_loss={val_loss:.4f}, test_p10={test_p10:.4f if test_p10 else 'N/A'}")
        
        # Early stopping
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_model = model.wv.copy()
            patience_counter = 0
            logger.info(f"  ✓ New best model (val_loss={val_loss:.4f})")
        else:
            patience_counter += 1
            if patience_counter >= early_stopping_patience:
                logger.info(f"  Early stopping at epoch {epoch + 1}")
                break
        
        # Learning rate decay
        model.alpha = max(min_learning_rate, model.alpha * 0.95)
        model.min_alpha = model.alpha
    
    # Use best model
    if best_model:
        model.wv = best_model
        logger.info(f"Using best model (val_loss={best_val_loss:.4f})")
    
    # Save
    model.wv.save(str(output_file))
    logger.info(f"Saved to {output_file}")
    
    return {
        "best_val_loss": best_val_loss,
        "training_history": training_history,
        "final_epoch": len(training_history),
    }


def main() -> int:
    """Train with validation and early stopping."""
    parser = argparse.ArgumentParser(description="Train embeddings with validation")
    parser.add_argument("--input", type=str, required=True, help="Edgelist file")
    parser.add_argument("--output", type=str, required=True, help="Output embeddings")
    parser.add_argument("--test-set", type=str, help="Test set for evaluation")
    parser.add_argument("--name-mapping", type=str, help="Name mapping JSON")
    parser.add_argument("--dim", type=int, default=128, help="Embedding dimension")
    parser.add_argument("--walk-length", type=int, default=80, help="Walk length")
    parser.add_argument("--num-walks", type=int, default=10, help="Number of walks")
    parser.add_argument("--window", type=int, default=10, help="Window size")
    parser.add_argument("--p", type=float, default=1.0, help="Return parameter")
    parser.add_argument("--q", type=float, default=1.0, help="In-out parameter")
    parser.add_argument("--epochs", type=int, default=10, help="Max epochs")
    parser.add_argument("--val-ratio", type=float, default=0.1, help="Validation ratio")
    parser.add_argument("--patience", type=int, default=3, help="Early stopping patience")
    parser.add_argument("--lr", type=float, default=0.025, help="Learning rate")
    parser.add_argument("--min-lr", type=float, default=0.0001, help="Min learning rate")
    
    args = parser.parse_args()
    
    if not HAS_DEPS:
        logger.error("Missing dependencies")
        return 1
    
    # Load test set if provided
    test_set = None
    if args.test_set:
        with open(args.test_set) as f:
            test_data = json.load(f)
            test_set = test_data.get("queries", test_data)
    
    # Load name mapping if provided
    name_mapper = None
    if args.name_mapping:
        with open(args.name_mapping) as f:
            mapping_data = json.load(f)
            name_mapper = mapping_data.get("mapping", {})
    
    # Train
    results = train_with_validation(
        Path(args.input),
        Path(args.output),
        test_set,
        name_mapper,
        dim=args.dim,
        walk_length=args.walk_length,
        num_walks=args.num_walks,
        window_size=args.window,
        p=args.p,
        q=args.q,
        epochs=args.epochs,
        val_ratio=args.val_ratio,
        early_stopping_patience=args.patience,
        learning_rate=args.lr,
        min_learning_rate=args.min_lr,
    )
    
    # Save training history
    history_file = Path(args.output).parent / f"{Path(args.output).stem}_history.json"
    with open(history_file, "w") as f:
        json.dump(results, f, indent=2)
    
    logger.info(f"✅ Training complete!")
    logger.info(f"📊 Training history: {history_file}")
    logger.info(f"📈 Best val_loss: {results['best_val_loss']:.4f}")
    logger.info(f"📈 Final epoch: {results['final_epoch']}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

