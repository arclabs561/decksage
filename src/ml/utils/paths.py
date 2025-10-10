"""Canonical paths for data and models."""

from pathlib import Path
import os

# Project root (src/ml -> src -> root), overridable via env for installed package layouts
_env_root = os.getenv("DECKSAGE_ROOT")
if _env_root:
    PROJECT_ROOT = Path(_env_root)
else:
    PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

# Data directories
DATA_DIR = PROJECT_ROOT / "data"
PROCESSED_DIR = DATA_DIR / "processed"
EMBEDDINGS_DIR = DATA_DIR / "embeddings"
GRAPHS_DIR = DATA_DIR / "graphs"

# Backend directory (legacy location for some data)
BACKEND_DIR = PROJECT_ROOT / "src" / "backend"

# Experiments directory
EXPERIMENTS_DIR = PROJECT_ROOT / "experiments"

# Common data files
PAIRS_LARGE = PROCESSED_DIR / "pairs_large.csv"
PAIRS_500 = PROCESSED_DIR / "pairs_500decks.csv"

# NEW: Fixed metadata export (Oct 2025 - bug fix)
DECKS_WITH_METADATA = PROCESSED_DIR / "decks_with_metadata.jsonl"

# Test sets
TEST_SET_MAGIC = EXPERIMENTS_DIR / "test_set_canonical_magic.json"
TEST_SET_POKEMON = EXPERIMENTS_DIR / "test_set_canonical_pokemon.json"
TEST_SET_YUGIOH = EXPERIMENTS_DIR / "test_set_canonical_yugioh.json"

# Experiment log (Oct 2025: consolidated to canonical version)
EXPERIMENT_LOG = EXPERIMENTS_DIR / "EXPERIMENT_LOG_CANONICAL.jsonl"


class PATHS:
    """Namespace for canonical paths."""

    # Directories
    data = DATA_DIR
    processed = PROCESSED_DIR
    embeddings = EMBEDDINGS_DIR
    graphs = GRAPHS_DIR
    experiments = EXPERIMENTS_DIR
    backend = BACKEND_DIR

    # Data files
    pairs_large = PAIRS_LARGE
    pairs_500 = PAIRS_500
    decks_with_metadata = DECKS_WITH_METADATA

    # Test sets
    test_magic = TEST_SET_MAGIC
    test_pokemon = TEST_SET_POKEMON
    test_yugioh = TEST_SET_YUGIOH

    # Logs
    experiment_log = EXPERIMENT_LOG

    @staticmethod
    def embedding(name: str) -> Path:
        """Get path to embedding file."""
        return EMBEDDINGS_DIR / f"{name}.wv"

    @staticmethod
    def graph(name: str) -> Path:
        """Get path to graph edgelist."""
        return GRAPHS_DIR / f"{name}.edg"
