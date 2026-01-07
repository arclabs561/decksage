"""Canonical paths for data and models."""

import os
from pathlib import Path


# Project root (src/ml -> src -> root), overridable via env for installed package layouts
# Also handles runctl execution context (runs from project root)
_env_root = os.getenv("DECKSAGE_ROOT")
if _env_root:
    PROJECT_ROOT = Path(_env_root)
else:
    # Try to find project root by looking for markers (works with runctl)
    current = Path(__file__).parent.parent.parent.parent
    # Check if we're already at project root (runctl runs from project root)
    markers = [
        "pyproject.toml",
        "requirements.txt",
        "setup.py",
        "Cargo.toml",
        ".git",
        "runctl.toml",
        ".runctl.toml",
    ]
    if any((current / m).exists() for m in markers):
        PROJECT_ROOT = current
    else:
        # Fall back to relative path calculation
        PROJECT_ROOT = current

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

# Graph database (SQLite primary, JSON fallback)
INCREMENTAL_GRAPH_DB = GRAPHS_DIR / "incremental_graph.db"
INCREMENTAL_GRAPH_JSON = GRAPHS_DIR / "incremental_graph.json"

# Pack database (for pack/booster/starter deck information)
PACKS_DB = DATA_DIR / "packs.db"

# NEW: Fixed metadata export (Oct 2025 - bug fix)
DECKS_WITH_METADATA = PROCESSED_DIR / "decks_with_metadata.jsonl"
DECKS_ALL_UNIFIED = PROCESSED_DIR / "decks_all_unified.jsonl"
DECKS_ALL_ENHANCED = PROCESSED_DIR / "decks_all_enhanced.jsonl"
DECKS_ALL_FINAL = PROCESSED_DIR / "decks_all_final.jsonl"

# Test sets (unified - merged from best available sources)
TEST_SET_MAGIC = EXPERIMENTS_DIR / "test_set_unified_magic.json"
TEST_SET_POKEMON = EXPERIMENTS_DIR / "test_set_unified_pokemon.json"
TEST_SET_YUGIOH = EXPERIMENTS_DIR / "test_set_unified_yugioh.json"

# Experiment log (Oct 2025: consolidated to canonical version)
EXPERIMENT_LOG = EXPERIMENTS_DIR / "EXPERIMENT_LOG_CANONICAL.jsonl"

# Annotations directory
ANNOTATIONS_DIR = PROJECT_ROOT / "annotations"
ANNOTATIONS_LLM_DIR = EXPERIMENTS_DIR / "annotations_llm"

# Common processed files
CARD_ATTRIBUTES = PROCESSED_DIR / "card_attributes_enriched.csv"

# Common experiment files
SUBSTITUTION_PAIRS_COMBINED = EXPERIMENTS_DIR / "substitution_pairs_combined.json"
SUBSTITUTION_PAIRS_FROM_LLM = EXPERIMENTS_DIR / "substitution_pairs_from_llm.json"
HYPERPARAMETER_RESULTS = EXPERIMENTS_DIR / "hyperparameter_results.json"
HYBRID_EVALUATION_RESULTS = EXPERIMENTS_DIR / "hybrid_evaluation_results.json"


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
    decks_all_unified = DECKS_ALL_UNIFIED
    decks_all_enhanced = DECKS_ALL_ENHANCED
    decks_all_final = DECKS_ALL_FINAL

    # Graph database
    incremental_graph_db = INCREMENTAL_GRAPH_DB
    incremental_graph_json = INCREMENTAL_GRAPH_JSON

    # Pack database
    packs_db = PACKS_DB

    # Test sets
    test_magic = TEST_SET_MAGIC
    test_pokemon = TEST_SET_POKEMON
    test_yugioh = TEST_SET_YUGIOH

    # Logs
    experiment_log = EXPERIMENT_LOG

    # Annotations
    annotations = ANNOTATIONS_DIR
    annotations_llm = ANNOTATIONS_LLM_DIR

    # Common processed files
    card_attributes = CARD_ATTRIBUTES

    # Common experiment files
    substitution_pairs_combined = SUBSTITUTION_PAIRS_COMBINED
    substitution_pairs_from_llm = SUBSTITUTION_PAIRS_FROM_LLM
    hyperparameter_results = HYPERPARAMETER_RESULTS
    hybrid_evaluation_results = HYBRID_EVALUATION_RESULTS

    @staticmethod
    def embedding(name: str) -> Path:
        """Get path to embedding file."""
        return EMBEDDINGS_DIR / f"{name}.wv"

    @staticmethod
    def graph(name: str) -> Path:
        """Get path to graph edgelist."""
        return GRAPHS_DIR / f"{name}.edg"
