"""
Shared operations for ML pipeline.
Consolidates common patterns used across multiple scripts.
"""
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set
import json
import pandas as pd
from gensim.models import KeyedVectors

def load_embeddings(embedding_path: Path, subdir: Optional[str] = None) -> KeyedVectors:
    """
    Load embeddings with automatic path resolution.
    
    Supports:
    - Direct paths: data/embeddings/file.wv
    - Subdirectory paths: data/embeddings/multitask/file.wv
    - Name-only: will search organized subdirectories
    """
    from ml.utils.paths import PATHS
    emb_dir = PATHS.embeddings
    
    # If subdir specified, use it
    if subdir:
        full_path = emb_dir / subdir / embedding_path.name if embedding_path.suffix else emb_dir / subdir / f"{embedding_path}.wv"
    else:
        # Try direct path first
        if embedding_path.exists():
            full_path = embedding_path
        else:
            # Search organized subdirectories
            for subdir_name in ["multitask", "trained", "game_specific", "baselines"]:
                candidate = emb_dir / subdir_name / (embedding_path.name if embedding_path.suffix else f"{embedding_path}.wv")
                if candidate.exists():
                    full_path = candidate
                    break
            else:
                # Fallback to old location
                full_path = emb_dir / (embedding_path.name if embedding_path.suffix else f"{embedding_path}.wv")
    
    if not full_path.exists():
        raise FileNotFoundError(f"Embedding not found: {full_path}")
    
    return KeyedVectors.load(str(full_path))

def get_embedding_path(embedding_name: str, category: Optional[str] = None) -> Path:
    """Get path to embedding, checking organized subdirectories."""
    from ml.utils.paths import PATHS
    emb_dir = PATHS.embeddings
    
    if category:
        return emb_dir / category / f"{embedding_name}.wv"
    
    # Search all categories
    for cat in ["multitask", "trained", "game_specific", "baselines"]:
        candidate = emb_dir / cat / f"{embedding_name}.wv"
        if candidate.exists():
            return candidate
    
    # Fallback
    return emb_dir / f"{embedding_name}.wv"


def jaccard_similarity(set1: Set[str], set2: Set[str]) -> float:
    """
    Compute Jaccard similarity between two sets.
    
    Args:
        set1: First set
        set2: Second set
    
    Returns:
        Jaccard coefficient (0.0 to 1.0)
    """
    if not set1 or not set2:
        return 0.0
    
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    
    return intersection / union if union > 0 else 0.0


def load_graph_for_jaccard(
    pairs_csv: Path | None = None,
    graph_db: Path | None = None,
    game: Optional[str] = None,
    max_rows: Optional[int] = None,
) -> Dict[str, Set[str]]:
    """
    Load graph adjacency for Jaccard similarity.
    
    Args:
        pairs_csv: Path to pairs CSV file (columns: NAME_1, NAME_2) - legacy option
        graph_db: Path to incremental graph SQLite database - preferred option
        game: Filter by game ("MTG", "PKM", "YGO") - only used with graph_db
        max_rows: Optional limit on number of rows to read (for testing) - only used with pairs_csv
    
    Returns:
        Dictionary mapping card names to sets of neighbor card names
    """
    # Try incremental graph first if provided
    if graph_db and graph_db.exists():
        print(f"Loading graph from incremental graph database: {graph_db}...")
        try:
            import sys
            from pathlib import Path as PathType
            script_dir = PathType(__file__).parent
            src_dir = script_dir.parent.parent
            if str(src_dir) not in sys.path:
                sys.path.insert(0, str(src_dir))
            
            from ml.data.incremental_graph import IncrementalCardGraph
            
            graph = IncrementalCardGraph(graph_path=graph_db, use_sqlite=True)
            
            # Query edges (optionally filtered by game)
            # OPTIMIZATION: Use query_edges with game filter to reduce data transfer
            edges = graph.query_edges(game=game, min_weight=1)
            
            # OPTIMIZATION: Pre-allocate adj dict and batch process edges
            # Use defaultdict for cleaner code and better performance
            from collections import defaultdict
            adj: Dict[str, Set[str]] = defaultdict(set)
            
            # Process edges in batch (vectorized where possible)
            for edge in edges:
                card1 = edge.card1
                card2 = edge.card2
                adj[card1].add(card2)
                adj[card2].add(card1)
            
            # Convert defaultdict to regular dict for consistency
            adj = dict(adj)
            
            print(f"  Loaded {len(adj):,} cards from graph database")
            if game:
                print(f"  Filtered by game: {game}")
            return adj
        except Exception as e:
            print(f"  Warning: Could not load from graph database: {e}")
            print(f"  Falling back to pairs CSV...")
    
    # Fallback to pairs CSV
    if pairs_csv is None:
        from ml.utils.paths import PATHS
        pairs_csv = PATHS.pairs_large
    
    if not pairs_csv.exists():
        raise FileNotFoundError(f"Graph source not found: {pairs_csv} or {graph_db}")
    
    print(f"Loading graph from {pairs_csv}...")
    
    # OPTIMIZATION: Use chunked reading with C engine for faster CSV parsing
    chunk_size = 1000000  # Larger chunks for better performance
    adj: Dict[str, Set[str]] = {}
    
    # OPTIMIZATION: Use defaultdict and vectorized operations
    from collections import defaultdict
    adj = defaultdict(set)
    
    if max_rows:
        # For limited rows, read all at once (faster for small datasets)
        df = pd.read_csv(
            pairs_csv,
            nrows=max_rows,
            engine='c',  # C parser is faster
            usecols=['NAME_1', 'NAME_2'],  # Only read needed columns
            dtype={'NAME_1': 'string', 'NAME_2': 'string'},
        )
        chunks = [df]
    else:
        # Process in chunks for very large files
        # OPTIMIZATION: Only read needed columns, use C engine, pre-specify types
        chunks = pd.read_csv(
            pairs_csv,
            chunksize=chunk_size,
            engine='c',  # C parser is faster than Python
            usecols=['NAME_1', 'NAME_2'],  # Only read needed columns (faster I/O)
            dtype={'NAME_1': 'string', 'NAME_2': 'string'},  # Pre-specify types (faster parsing)
            low_memory=False,  # Disable low_memory mode for faster parsing (uses more memory but faster)
        )
    
    # OPTIMIZATION: Process chunks with vectorized operations
    for chunk_df in chunks:
        # OPTIMIZATION: Filter by game if specified (before processing)
        if game:
            # If game column exists, filter it
            if 'GAME' in chunk_df.columns:
                chunk_df = chunk_df[chunk_df['GAME'] == game]
            elif 'game' in chunk_df.columns:
                chunk_df = chunk_df[chunk_df['game'] == game]
        
        # OPTIMIZATION: Vectorized processing - convert to string once, drop NaN
        card1_col = chunk_df["NAME_1"].astype(str)
        card2_col = chunk_df["NAME_2"].astype(str)
        
        # OPTIMIZATION: Filter out NaN and empty strings before iteration
        mask = (card1_col != 'nan') & (card2_col != 'nan') & (card1_col != '') & (card2_col != '')
        card1_col = card1_col[mask]
        card2_col = card2_col[mask]
        
        # OPTIMIZATION: Use zip for faster iteration (avoids iterrows overhead)
        for card1, card2 in zip(card1_col, card2_col):
            adj[card1].add(card2)
            adj[card2].add(card1)
    
    # Convert defaultdict to regular dict for consistency
    adj = dict(adj)
    
    print(f"  Loaded {len(adj):,} cards")
    return adj


# Alias for backward compatibility
load_jaccard_graph = load_graph_for_jaccard
