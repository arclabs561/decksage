#!/usr/bin/env python3
"""
Similarity Function Helper

Creates similarity functions for use in evaluation/validation scripts.
Allows deck quality validation to work without full API.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from ..similarity.fusion import FusionWeights, WeightedLateFusion
from ..similarity.similarity_methods import jaccard_similarity, load_graph
from ..utils.data_loading import load_embeddings
from ..utils.paths import PATHS

logger = logging.getLogger(__name__)


def create_similarity_function(
    embeddings_path: Path | str | None = None,
    pairs_path: Path | str | None = None,
    method: str = "fusion",
    weights: FusionWeights | None = None,
    tag_set_fn: Callable[[str], set[str]] | None = None,
) -> Callable[[str, int], list[tuple[str, float]]]:
    """
    Create a similarity function from embeddings/graph data.
    
    Args:
        embeddings_path: Path to .wv embeddings file
        pairs_path: Path to pairs CSV for Jaccard similarity
        method: 'embedding', 'jaccard', or 'fusion'
        weights: Fusion weights (only used for fusion method)
        tag_set_fn: Function to get functional tags (only used for fusion)
    
    Returns:
        Function (query: str, k: int) -> [(card, score), ...]
    """
    # Load embeddings
    embeddings = None
    if embeddings_path:
        if isinstance(embeddings_path, str):
            embeddings_path = Path(embeddings_path)
        
        if embeddings_path.exists():
            try:
                # Handle both .wv extension and without
                emb_name = str(embeddings_path)
                if emb_name.endswith(".wv"):
                    emb_name = emb_name[:-3]
                embeddings = load_embeddings(emb_name)
                logger.info(f"Loaded embeddings: {len(embeddings)} cards")
            except Exception as e:
                logger.warning(f"Failed to load embeddings from {embeddings_path}: {e}")
                embeddings = None
        else:
            logger.warning(f"Embeddings not found: {embeddings_path}")
            embeddings = None
    
    # Load graph for Jaccard
    adj = None
    weights_dict = None
    if pairs_path:
        if isinstance(pairs_path, str):
            pairs_path = Path(pairs_path)
        
        if pairs_path.exists():
            try:
                adj, weights_dict = load_graph(str(pairs_path), filter_lands=True)
                if adj:
                    logger.info(f"Loaded graph: {len(adj)} cards")
                else:
                    logger.warning(f"Graph loaded but empty: {pairs_path}")
                    adj = None
            except Exception as e:
                logger.warning(f"Failed to load graph from {pairs_path}: {e}")
                adj = None
                weights_dict = None
        else:
            logger.warning(f"Pairs file not found: {pairs_path}")
            adj = None
            weights_dict = None
    
    # Create similarity function based on method
    if method == "embedding":
        if embeddings is None:
            raise ValueError("Embeddings required for embedding method")
        
        def similarity_fn(query: str, k: int) -> list[tuple[str, float]]:
            if query not in embeddings:
                logger.warning(f"Card not in embeddings: {query}")
                return []
            similar = embeddings.most_similar(query, topn=k)
            return [(card, float(score)) for card, score in similar]
        
        return similarity_fn
    
    elif method == "jaccard":
        if adj is None:
            raise ValueError("Graph required for jaccard method")
        
        def similarity_fn(query: str, k: int) -> list[tuple[str, float]]:
            if query not in adj:
                logger.warning(f"Card not in graph: {query}")
                return []
            scores = jaccard_similarity(query, adj, k=k)
            return [(card, float(score)) for card, score in scores]
        
        return similarity_fn
    
    elif method == "fusion":
        if embeddings is None and adj is None:
            raise ValueError("Need embeddings or graph for fusion method")
        
        # Use default weights if not provided
        if weights is None:
            weights = FusionWeights(
                embed=0.20,
                jaccard=0.15,
                functional=0.10,
                text_embed=0.25,
                gnn=0.30,
            ).normalized()
        
        # Create fusion instance
        fusion = WeightedLateFusion(
            embeddings=embeddings,
            adj=adj,
            tagger=tag_set_fn,
            weights=weights,
            aggregator="weighted",
        )
        
        def similarity_fn(query: str, k: int) -> list[tuple[str, float]]:
            # Use fusion.similar() directly (simpler than creating request)
            results = fusion.similar(query, k, task_type="substitution")
            return [(card, float(score)) for card, score in results]
        
        return similarity_fn
    
    else:
        raise ValueError(f"Unknown method: {method}")


def create_similarity_function_from_env() -> Callable[[str, int], list[tuple[str, float]]]:
    """
    Create similarity function from environment variables (like API does).
    
    Reads EMBEDDINGS_PATH and PAIRS_PATH from environment.
    """
    import os
    
    emb_path = os.getenv("EMBEDDINGS_PATH")
    pairs_path = os.getenv("PAIRS_PATH")
    method = os.getenv("SIMILARITY_METHOD", "fusion")
    
    if not emb_path and not pairs_path:
        raise ValueError(
            "EMBEDDINGS_PATH or PAIRS_PATH required. "
            "Set environment variables or pass paths directly."
        )
    
    return create_similarity_function(
        embeddings_path=Path(emb_path) if emb_path else None,
        pairs_path=Path(pairs_path) if pairs_path else None,
        method=method,
    )


def create_similarity_function_from_defaults(
    game: str = "magic",
) -> Callable[[str, int], list[tuple[str, float]]]:
    """
    Create similarity function using default paths for a game.
    
    Args:
        game: 'magic', 'pokemon', or 'yugioh'
    
    Returns:
        Similarity function
    """
    # Try to find embeddings
    embeddings_path = None
    for name in [
        f"{game}_128d_test_pecanpy",
        f"{game}_production",
        "production",
    ]:
        candidate = PATHS.embedding(name)
        if candidate.exists():
            embeddings_path = candidate
            break
    
    # Try to find pairs
    pairs_path = PATHS.pairs_large
    if not pairs_path.exists():
        pairs_path = None
    
    if not embeddings_path and not pairs_path:
        raise ValueError(
            f"No embeddings or pairs found for {game}. "
            "Set EMBEDDINGS_PATH and PAIRS_PATH or train embeddings first."
        )
    
    return create_similarity_function(
        embeddings_path=embeddings_path,
        pairs_path=pairs_path,
        method="fusion",
    )

