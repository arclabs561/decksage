"""
Shared operations for ML pipeline.
Consolidates common patterns used across multiple scripts.
"""

from pathlib import Path

from gensim.models import KeyedVectors


def load_embeddings(embedding_path: Path, subdir: str | None = None) -> KeyedVectors:
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
        full_path = (
            emb_dir / subdir / embedding_path.name
            if embedding_path.suffix
            else emb_dir / subdir / f"{embedding_path}.wv"
        )
    else:
        # Try direct path first
        if embedding_path.exists():
            full_path = embedding_path
        else:
            # Search organized subdirectories
            for subdir_name in ["multitask", "trained", "game_specific", "baselines"]:
                candidate = (
                    emb_dir
                    / subdir_name
                    / (embedding_path.name if embedding_path.suffix else f"{embedding_path}.wv")
                )
                if candidate.exists():
                    full_path = candidate
                    break
            else:
                # Fallback to old location
                full_path = emb_dir / (
                    embedding_path.name if embedding_path.suffix else f"{embedding_path}.wv"
                )

    if not full_path.exists():
        raise FileNotFoundError(f"Embedding not found: {full_path}")

    return KeyedVectors.load(str(full_path))


def get_embedding_path(embedding_name: str, category: str | None = None) -> Path:
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


def jaccard_similarity(set1: set[str], set2: set[str]) -> float:
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
    game: str | None = None,
    max_rows: int | None = None,
) -> dict[str, set[str]]:
    """
    Load graph adjacency for Jaccard similarity.

    Delegates to graph_loading.load_graph (unified implementation).

    Args:
        pairs_csv: Path to pairs CSV file (columns: NAME_1, NAME_2) - legacy option
        graph_db: Path to incremental graph SQLite database - preferred option
        game: Filter by game ("MTG", "PKM", "YGO") - only used with graph_db
        max_rows: Ignored (kept for backward compat signature)

    Returns:
        Dictionary mapping card names to sets of neighbor card names
    """
    from .graph_loading import load_graph

    source = graph_db if (graph_db and graph_db.exists()) else pairs_csv
    result = load_graph(source, game=game, include_weights=False)
    return result.adjacency


# Alias for backward compatibility
load_jaccard_graph = load_graph_for_jaccard
