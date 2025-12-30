#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pandas>=2.0.0",
#   "numpy<2.0.0",
#   "pecanpy>=2.0.0",
#   "gensim>=4.3.0",
# ]
# ///
"""
Refined multi-task embedding training.

Optimizes for multiple objectives simultaneously:
1. Co-occurrence (cards in same decks) - weight: 1.0
2. Functional similarity (substitution pairs) - weight: 5.0
3. Graph structure (Node2Vec walks)

Uses weighted graph edges to combine objectives.
"""

from __future__ import annotations

import argparse
import json
import logging
import tempfile
from collections import Counter, defaultdict
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


def load_substitution_pairs(substitution_path: Path) -> list[tuple[str, str]]:
    """Load substitution pairs from test data."""
    with open(substitution_path) as f:
        data = json.load(f)
    
    if isinstance(data, list):
        # Format: [["card1", "card2"], ...]
        return [tuple(pair) for pair in data]
    elif isinstance(data, dict) and "queries" in data:
        # Format: {"queries": {"query": {"highly_relevant": [...]}}}
        pairs = []
        for query, labels in data["queries"].items():
            for card in labels.get("highly_relevant", []):
                pairs.append((query, card))
        return pairs
    else:
        return []


def create_multitask_edgelist(
    pairs_df: pd.DataFrame,
    substitution_pairs: list[tuple[str, str]],
    cooccurrence_weight: float = 1.0,
    substitution_weight: float = 5.0,
    min_cooccurrence: int = 2,
) -> list[tuple[str, str, float]]:
    """
    Create weighted edgelist for multi-task training.
    
    Edges:
    - Co-occurrence: weight = cooccurrence_weight * normalized_count
    - Substitution: weight = substitution_weight (higher for functional similarity)
    
    Returns list of (node1, node2, weight) tuples.
    """
    edges = []
    edge_counts = Counter()
    
    # Add co-occurrence edges
    logger.info("Adding co-occurrence edges...")
    for _, row in pairs_df.iterrows():
        if row.get("COUNT_SET", 0) < min_cooccurrence:
            continue
        
        n1 = row.get("NAME_1", "")
        n2 = row.get("NAME_2", "")
        count = row.get("COUNT_MULTISET", 1)
        
        if n1 and n2:
            # Normalize count (log scale to reduce impact of outliers)
            normalized = np.log1p(count) / np.log1p(pairs_df["COUNT_MULTISET"].max())
            weight = cooccurrence_weight * normalized
            edges.append((n1, n2, weight))
            edge_counts[(n1, n2)] += count
    
    logger.info(f"  Added {len(edges)} co-occurrence edges")
    
    # Add substitution edges (functional similarity)
    if substitution_pairs:
        logger.info(f"Adding {len(substitution_pairs)} substitution edges...")
        substitution_added = 0
        for original, substitute in substitution_pairs:
            if original and substitute:
                # Check if edge already exists (from co-occurrence)
                if (original, substitute) in edge_counts:
                    # Increase weight for existing edge
                    idx = next(i for i, (n1, n2, _) in enumerate(edges) 
                              if (n1, n2) == (original, substitute) or (n2, n1) == (original, substitute))
                    edges[idx] = (edges[idx][0], edges[idx][1], edges[idx][2] + substitution_weight)
                else:
                    # Add new edge
                    edges.append((original, substitute, substitution_weight))
                    substitution_added += 1
        
        logger.info(f"  Added {substitution_added} new substitution edges")
        logger.info(f"  Enhanced {len(substitution_pairs) - substitution_added} existing edges")
    
    logger.info(f"Total edges: {len(edges)}")
    return edges


def train_multitask_embeddings(
    pairs_csv: Path,
    output_path: Path,
    substitution_pairs_path: Path | None = None,
    dim: int = 128,
    walk_length: int = 80,
    num_walks: int = 10,
    window_size: int = 10,
    p: float = 1.0,
    q: float = 1.0,
    epochs: int = 10,
    cooccurrence_weight: float = 1.0,
    substitution_weight: float = 5.0,
    min_cooccurrence: int = 2,
    workers: int = 4,
) -> KeyedVectors:
    """
    Train embeddings with multi-task optimization.
    
    Creates weighted graph combining:
    - Co-occurrence edges (weight: cooccurrence_weight)
    - Substitution edges (weight: substitution_weight, higher)
    
    Then trains Node2Vec on weighted graph.
    """
    if not HAS_DEPS:
        raise ImportError("pandas, numpy, pecanpy, gensim required")
    
    logger.info("=" * 70)
    logger.info("Multi-Task Embedding Training")
    logger.info("=" * 70)
    logger.info(f"Co-occurrence weight: {cooccurrence_weight}")
    logger.info(f"Substitution weight: {substitution_weight}")
    logger.info(f"Ratio: {substitution_weight / cooccurrence_weight:.1f}x more weight on substitution")
    
    # Load data (full dataset, no sampling)
    logger.info(f"\nLoading pairs from {pairs_csv}...")
    pairs_df = pd.read_csv(pairs_csv)
    logger.info(f"  Loaded {len(pairs_df)} pairs (full dataset)")
    
    # Load substitution pairs
    substitution_pairs = []
    if substitution_pairs_path and substitution_pairs_path.exists():
        logger.info(f"Loading substitution pairs from {substitution_pairs_path}...")
        substitution_pairs = load_substitution_pairs(substitution_pairs_path)
        logger.info(f"  Loaded {len(substitution_pairs)} substitution pairs")
    
    # Create multi-task edgelist
    logger.info("\nCreating multi-task edgelist...")
    edges = create_multitask_edgelist(
        pairs_df,
        substitution_pairs,
        cooccurrence_weight=cooccurrence_weight,
        substitution_weight=substitution_weight,
        min_cooccurrence=min_cooccurrence,
    )
    
    # Write to temporary edgelist file
    logger.info("Writing edgelist...")
    with tempfile.NamedTemporaryFile(mode='w', suffix='.edg', delete=False) as tmp:
        edgelist_path = Path(tmp.name)
        for card1, card2, weight in edges:
            tmp.write(f"{card1}\t{card2}\t{weight}\n")
    
    try:
        # Create PecanPy graph
        logger.info("Creating PecanPy graph...")
        graph = SparseOTF(p=p, q=q, workers=workers, verbose=True, extend=True)
        graph.read_edg(str(edgelist_path), weighted=True, directed=False)
        
        # Generate walks
        logger.info(f"Generating random walks (num_walks={num_walks}, walk_length={walk_length})...")
        walks = graph.simulate_walks(
            num_walks=num_walks,
            walk_length=walk_length,
        )
        logger.info(f"  Generated {len(walks)} walks")
    finally:
        # Clean up temp file
        edgelist_path.unlink()
    
    # Train Word2Vec
    logger.info(f"Training Word2Vec (dim={dim}, window={window_size}, epochs={epochs})...")
    model = Word2Vec(
        sentences=walks,
        vector_size=dim,
        window=window_size,
        min_count=1,
        workers=workers,
        epochs=epochs,
        sg=1,  # Skip-gram
    )
    
    # Save
    wv = model.wv
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wv.save(str(output_path))
    logger.info(f"✅ Saved embeddings to {output_path}")
    logger.info(f"  Vocabulary: {len(wv)} cards")
    
    return wv


def main() -> int:
    """Train multi-task embeddings."""
    parser = argparse.ArgumentParser(description="Train multi-task embeddings")
    parser.add_argument("--pairs", type=Path, required=True, help="Pairs CSV (co-occurrence)")
    parser.add_argument("--substitution-pairs", type=Path, help="Substitution pairs JSON")
    parser.add_argument("--output", type=Path, required=True, help="Output .wv file")
    parser.add_argument("--dim", type=int, default=128, help="Embedding dimension")
    parser.add_argument("--walk-length", type=int, default=80, help="Walk length")
    parser.add_argument("--num-walks", type=int, default=10, help="Number of walks per node")
    parser.add_argument("--window-size", type=int, default=10, help="Window size")
    parser.add_argument("--p", type=float, default=1.0, help="Return parameter")
    parser.add_argument("--q", type=float, default=1.0, help="In-out parameter")
    parser.add_argument("--epochs", type=int, default=10, help="Training epochs")
    parser.add_argument("--cooccurrence-weight", type=float, default=1.0, help="Weight for co-occurrence edges")
    parser.add_argument("--substitution-weight", type=float, default=5.0, help="Weight for substitution edges")
    parser.add_argument("--min-cooccurrence", type=int, default=2, help="Minimum co-occurrence count")
    parser.add_argument("--workers", type=int, default=4, help="Number of workers")
    
    args = parser.parse_args()
    
    if not HAS_DEPS:
        print("Error: Missing dependencies")
        return 1
    
    try:
        wv = train_multitask_embeddings(
            pairs_csv=args.pairs,
            substitution_pairs_path=args.substitution_pairs,
            output_path=args.output,
            dim=args.dim,
            walk_length=args.walk_length,
            num_walks=args.num_walks,
            window_size=args.window_size,
            p=args.p,
            q=args.q,
            epochs=args.epochs,
            cooccurrence_weight=args.cooccurrence_weight,
            substitution_weight=args.substitution_weight,
            min_cooccurrence=args.min_cooccurrence,
            workers=args.workers,
        )
        
        logger.info("\n✅ Multi-task training complete!")
        return 0
    except Exception as e:
        logger.error(f"❌ Training failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit(main())

