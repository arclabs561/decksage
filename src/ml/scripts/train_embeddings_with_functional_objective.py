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
Train embeddings with functional similarity objective.

Uses functional tags to guide embedding training, encouraging
cards with similar functions to be close in embedding space.

Research Basis:
- Functional tags provide explicit similarity signals
- Graph augmentation with functional edges improves substitution performance
- Tag Jaccard similarity provides better edge weighting than binary matching
- Combining graph structure with semantic information improves embeddings

References:
- Graph embedding with attributes: Research on attributed graph embeddings
- Functional similarity learning: Research on learning substitutable items
- Multi-modal graph learning: Combining structure and attributes
"""

from __future__ import annotations

import argparse
import logging
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Fix import path
import sys
script_dir = Path(__file__).parent
src_dir = script_dir.parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

try:
    from ml.enrichment.card_functional_tagger import FunctionalTagger
    HAS_TAGGER = True
except ImportError:
    HAS_TAGGER = False


def create_functional_edges(
    pairs_csv: Path,
    tagger: Any,
    functional_weight: float = 1.0,
    tag_threshold: float = 0.2,
) -> list[tuple[str, str, float]]:
    """
    Create additional edges for cards with similar functional tags.
    
    Returns list of (card1, card2, weight) tuples.
    """
    if not HAS_TAGGER:
        return []
    
    logger.info("Creating functional edges...")
    
    # Load pairs to get card names
    df = pd.read_csv(pairs_csv, nrows=50000)
    all_cards = set(df["NAME_1"].unique()) | set(df["NAME_2"].unique())
    
    functional_edges = []
    
    # Group cards by functional tags
    cards_by_tag: dict[str, list[str]] = {}
    card_tags: dict[str, set[str]] = {}  # card -> set of tags
    
    for card in all_cards:
        try:
            tags = tagger.tag_card(card)
            if not tags:
                continue
            
            # Get active tags (boolean fields that are True)
            from dataclasses import asdict
            tag_dict = asdict(tags)
            active_tags = {k for k, v in tag_dict.items() if isinstance(v, bool) and v}
            
            if not active_tags:
                continue
            
            card_tags[card] = active_tags
            
            for tag in active_tags:
                if tag not in cards_by_tag:
                    cards_by_tag[tag] = []
                cards_by_tag[tag].append(card)
        except Exception:
            continue
    
    # Create edges with weights based on tag overlap (Jaccard similarity)
    # This is better than binary connection - weights by functional similarity
    logger.info(f"  Computing functional similarity for {len(card_tags)} cards...")
    
    cards_list = list(card_tags.keys())
    for i, card1 in enumerate(cards_list):
        if i % 1000 == 0 and i > 0:
            logger.info(f"    Processed {i}/{len(cards_list)} cards...")
        
        tags1 = card_tags[card1]
        
        for card2 in cards_list[i+1:]:
            tags2 = card_tags.get(card2, set())
            
            if not tags2:
                continue
            
            # Jaccard similarity of functional tags
            intersection = len(tags1 & tags2)
            union = len(tags1 | tags2)
            
            if union == 0:
                continue
            
            jaccard = intersection / union
            
            # Only create edge if there's meaningful overlap (threshold)
            if jaccard >= tag_threshold:
                weight = functional_weight * jaccard  # Weight by similarity
                functional_edges.append((card1, card2, weight))
    
    logger.info(f"  Created {len(functional_edges)} functional edges")
    return functional_edges


def train_with_functional_objective(
    pairs_csv: Path,
    output_path: Path,
    dimensions: int = 128,
    walk_length: int = 80,
    num_walks: int = 10,
    window_size: int = 10,
    epochs: int = 1,
    p: float = 1.0,
    q: float = 1.0,
    functional_weight: float = 1.0,
    tag_threshold: float = 0.2,
) -> KeyedVectors:
    """Train embeddings with functional similarity objective."""
    logger.info("Training embeddings with functional objective...")
    
    # Load base graph
    df = pd.read_csv(pairs_csv, nrows=100000)
    
    # Create adjacency dict
    adj = {}
    weights = {}
    
    for _, row in df.iterrows():
        card1 = str(row["NAME_1"])
        card2 = str(row["NAME_2"])
        
        if card1 not in adj:
            adj[card1] = set()
        if card2 not in adj:
            adj[card2] = set()
        
        adj[card1].add(card2)
        adj[card2].add(card1)
        
        # Base weight
        edge_key = tuple(sorted([card1, card2]))
        weights[edge_key] = weights.get(edge_key, 0.0) + 1.0
    
    # Add functional edges if tagger available
    if HAS_TAGGER:
        try:
            tagger = FunctionalTagger()
            functional_edges = create_functional_edges(pairs_csv, tagger, functional_weight, tag_threshold)
            
            for card1, card2, weight in functional_edges:
                if card1 not in adj:
                    adj[card1] = set()
                if card2 not in adj:
                    adj[card2] = set()
                
                adj[card1].add(card2)
                adj[card2].add(card1)
                
                edge_key = tuple(sorted([card1, card2]))
                weights[edge_key] = weights.get(edge_key, 0.0) + weight
        except Exception as e:
            logger.warning(f"Could not add functional edges: {e}")
    
    # Create temporary edgelist file for PecanPy
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.edg', delete=False) as f:
        edgelist_path = Path(f.name)
        for (c1, c2), w in weights.items():
            f.write(f"{c1}\t{c2}\t{w}\n")
    
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
        # Clean up temp file
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
    
    # Save as KeyedVectors
    wv = model.wv
    wv.save(str(output_path))
    logger.info(f"✅ Saved embeddings to {output_path}")
    
    return wv


def main() -> int:
    """Train embeddings with functional objective."""
    parser = argparse.ArgumentParser(description="Train embeddings with functional similarity")
    parser.add_argument("--input", type=Path, required=True, help="Input pairs CSV")
    parser.add_argument("--output", type=Path, required=True, help="Output embedding file")
    parser.add_argument("--dimensions", type=int, default=128, help="Embedding dimensions")
    parser.add_argument("--walk-length", type=int, default=80, help="Walk length")
    parser.add_argument("--num-walks", type=int, default=10, help="Number of walks per node")
    parser.add_argument("--window-size", type=int, default=10, help="Word2Vec window size")
    parser.add_argument("--epochs", type=int, default=5, help="Training epochs")
    parser.add_argument("--p", type=float, default=1.0, help="Node2Vec parameter p")
    parser.add_argument("--q", type=float, default=1.0, help="Node2Vec parameter q")
    parser.add_argument("--functional-weight", type=float, default=1.0, help="Weight for functional edges")
    parser.add_argument("--tag-threshold", type=float, default=0.2, help="Minimum tag Jaccard for functional edges")
    
    args = parser.parse_args()
    
    if not HAS_DEPS:
        logger.error("Missing dependencies")
        return 1
    
    train_with_functional_objective(
        pairs_csv=args.input,
        output_path=args.output,
        dimensions=args.dimensions,
        walk_length=args.walk_length,
        num_walks=args.num_walks,
        window_size=args.window_size,
        epochs=args.epochs,
        p=args.p,
        q=args.q,
        functional_weight=args.functional_weight,
        tag_threshold=args.tag_threshold,
    )
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

