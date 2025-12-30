#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
#     "numpy<2.0.0",
#     "gensim>=4.3.0",
#     "pecanpy>=2.0.0",
# ]
# ///
"""
Train embeddings with contrastive learning for substitution task.

Strategy:
1. Create positive pairs from substitution test data (functionally similar)
2. Create negative pairs from random cards (functionally different)
3. Add these pairs to the graph with high/low weights
4. Train Node2Vec on augmented graph

This encourages embeddings to capture functional similarity.

Research References:
- Graph Contrastive Learning: https://proceedings.nips.cc/paper/2020/file/3fe230348e9a12c13120749e3f9fa4cd-Paper.pdf
- Variational Graph Contrastive Learning: https://arxiv.org/abs/2411.07150
- Subgraph Contrastive Learning: https://arxiv.org/abs/2502.20885
- Deep Graph Contrastive Representation Learning: https://arxiv.org/abs/2006.04131
- Dual Space Graph Contrastive Learning: https://arxiv.org/abs/2201.07409
- Enhancing Hyperbolic Graph Embeddings: https://arxiv.org/abs/2201.08554
- Capturing Fine-grained Semantics: https://arxiv.org/abs/2304.11658
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import tempfile
from pathlib import Path
from typing import Any

try:
    import pandas as pd
    import numpy as np
    from gensim.models import Word2Vec, KeyedVectors
    from pecanpy.pecanpy import SparseOTF
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

import sys
script_dir = Path(__file__).parent
src_dir = script_dir.parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_substitution_pairs(substitution_path: Path) -> list[tuple[str, str]]:
    """Load substitution pairs from test data."""
    with open(substitution_path) as f:
        data = json.load(f)
    
    pairs = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, list) and len(item) >= 2:
                pairs.append((str(item[0]), str(item[1])))
            elif isinstance(item, dict):
                query = item.get("query", "")
                target = item.get("target", "")
                if query and target:
                    pairs.append((query, target))
    elif isinstance(data, dict):
        pairs_list = data.get("pairs", [])
        for item in pairs_list:
            if isinstance(item, list) and len(item) >= 2:
                pairs.append((str(item[0]), str(item[1])))
            elif isinstance(item, dict):
                query = item.get("query", "")
                target = item.get("target", "")
                if query and target:
                    pairs.append((query, target))
    
    return pairs


def create_contrastive_edges(
    pairs_csv: Path,
    substitution_pairs: list[tuple[str, str]],
    positive_weight: float = 10.0,  # Increased from 5.0
    negative_weight: float = 0.1,
    num_negatives: int = 1000,
) -> list[tuple[str, str, float]]:
    """Create contrastive edges for substitution learning."""
    logger.info("Creating contrastive edges...")
    
    # Load all cards from pairs
    df = pd.read_csv(pairs_csv, nrows=50000)
    all_cards = set(df["NAME_1"].unique()) | set(df["NAME_2"].unique())
    
    # Positive edges: substitution pairs (high weight)
    positive_edges = []
    positive_cards = set()
    
    for query, target in substitution_pairs:
        if query in all_cards and target in all_cards:
            positive_edges.append((query, target, positive_weight))
            positive_cards.add(query)
            positive_cards.add(target)
    
    logger.info(f"  Created {len(positive_edges)} positive edges")
    
    # Negative edges: random pairs (low weight, but still connected)
    # This helps the model learn to distinguish functional similarity
    negative_edges = []
    positive_set = set(positive_edges)
    cards_list = list(all_cards)
    
    for _ in range(num_negatives):
        card1 = random.choice(cards_list)
        card2 = random.choice(cards_list)
        
        if card1 == card2:
            continue
        
        # Skip if this is already a positive pair
        edge_key = tuple(sorted([card1, card2]))
        if edge_key in positive_set:
            continue
        
        negative_edges.append((card1, card2, negative_weight))
    
    logger.info(f"  Created {len(negative_edges)} negative edges")
    
    return positive_edges + negative_edges


def train_with_contrastive_substitution(
    pairs_csv: Path,
    substitution_path: Path,
    output_path: Path,
    dimensions: int = 128,
    walk_length: int = 80,
    num_walks: int = 10,
    window_size: int = 10,
    epochs: int = 15,
    p: float = 1.0,
    q: float = 1.0,
    positive_weight: float = 5.0,
    negative_weight: float = 0.1,
) -> KeyedVectors:
    """Train embeddings with contrastive learning for substitution."""
    if not HAS_DEPS:
        logger.error("Missing dependencies")
        return None
    
    # Load base graph
    logger.info(f"Loading base graph from {pairs_csv}...")
    df = pd.read_csv(pairs_csv)
    
    name_cols = [c for c in df.columns if "NAME" in c.upper()]
    if len(name_cols) < 2:
        logger.error("Could not find name columns")
        return None
    
    card1_col, card2_col = name_cols[0], name_cols[1]
    count_col = None
    for c in df.columns:
        if "COUNT" in c.upper():
            count_col = c
            break
    
    # Create base edgelist
    base_edges = []
    for _, row in df.iterrows():
        card1 = str(row[card1_col]).strip()
        card2 = str(row[card2_col]).strip()
        
        if not card1 or not card2 or card1 == card2:
            continue
        
        if card1 > card2:
            card1, card2 = card2, card1
        
        weight = int(row[count_col]) if count_col and pd.notna(row[count_col]) else 1
        base_edges.append((card1, card2, weight))
    
    logger.info(f"  Base edges: {len(base_edges):,}")
    
    # Load substitution pairs
    logger.info(f"Loading substitution pairs from {substitution_path}...")
    substitution_pairs = load_substitution_pairs(substitution_path)
    logger.info(f"  Loaded {len(substitution_pairs)} substitution pairs")
    
    # Create contrastive edges
    contrastive_edges = create_contrastive_edges(
        pairs_csv,
        substitution_pairs,
        positive_weight=positive_weight,
        negative_weight=negative_weight,
    )
    
    # Combine all edges
    all_edges = base_edges + contrastive_edges
    logger.info(f"  Total edges: {len(all_edges):,} (base: {len(base_edges)}, contrastive: {len(contrastive_edges)})")
    
    # Write edgelist
    with tempfile.NamedTemporaryFile(mode='w', suffix='.edg', delete=False) as tmp:
        edgelist_path = Path(tmp.name)
        for card1, card2, weight in all_edges:
            tmp.write(f"{card1}\t{card2}\t{weight}\n")
    
    try:
        # Create PecanPy graph
        logger.info("Creating PecanPy graph...")
        graph = SparseOTF(p=p, q=q, workers=1, verbose=False, extend=True)
        graph.read_edg(str(edgelist_path), weighted=True, directed=False)
        
        # Generate walks
        logger.info("Generating random walks...")
        walks = graph.simulate_walks(
            num_walks=num_walks,
            walk_length=walk_length,
        )
    finally:
        edgelist_path.unlink()
    
    logger.info(f"  Generated {len(walks)} walks")
    
    # Train Word2Vec
    logger.info("Training Word2Vec...")
    model = Word2Vec(
        sentences=walks,
        vector_size=dimensions,
        window=window_size,
        min_count=1,
        workers=1,
        epochs=epochs,
    )
    
    # Save
    wv = model.wv
    wv.save(str(output_path))
    logger.info(f"✅ Saved embeddings to {output_path}")
    
    return wv


def main() -> int:
    parser = argparse.ArgumentParser(description="Train embeddings with contrastive learning for substitution")
    parser.add_argument("--input", type=Path, required=True, help="Input pairs CSV")
    parser.add_argument("--substitution", type=Path, required=True, help="Substitution test pairs JSON")
    parser.add_argument("--output", type=Path, required=True, help="Output embedding file")
    parser.add_argument("--dimensions", type=int, default=128, help="Embedding dimensions")
    parser.add_argument("--walk-length", type=int, default=80, help="Walk length")
    parser.add_argument("--num-walks", type=int, default=10, help="Number of walks per node")
    parser.add_argument("--window-size", type=int, default=10, help="Word2Vec window size")
    parser.add_argument("--epochs", type=int, default=15, help="Training epochs")
    parser.add_argument("--p", type=float, default=1.0, help="Node2Vec parameter p")
    parser.add_argument("--q", type=float, default=1.0, help="Node2Vec parameter q")
    parser.add_argument("--positive-weight", type=float, default=5.0, help="Weight for positive (substitution) edges")
    parser.add_argument("--negative-weight", type=float, default=0.1, help="Weight for negative (random) edges")
    
    args = parser.parse_args()
    
    if not HAS_DEPS:
        logger.error("Missing dependencies")
        return 1
    
    train_with_contrastive_substitution(
        pairs_csv=args.input,
        substitution_path=args.substitution,
        output_path=args.output,
        dimensions=args.dimensions,
        walk_length=args.walk_length,
        num_walks=args.num_walks,
        window_size=args.window_size,
        epochs=args.epochs,
        p=args.p,
        q=args.q,
        positive_weight=args.positive_weight,
        negative_weight=args.negative_weight,
    )
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

