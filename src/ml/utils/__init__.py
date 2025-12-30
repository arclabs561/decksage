"""Shared utilities for multi-game ML experiments."""

from .constants import GAME_FILTERS, RELEVANCE_WEIGHTS, get_filter_set
from .data_loading import build_adjacency_dict, load_embeddings, load_pairs, load_test_set
from .evaluation import compute_precision_at_k, evaluate_similarity, jaccard_similarity
from .paths import PATHS

# AimStack helpers (optional)
try:
    from .aim_helpers import (
        create_training_run,
        track_artifact,
        track_evaluation_metrics,
        track_hyperparameter_result,
        track_training_metrics,
    )
    __all__ = [
        "GAME_FILTERS",
        "PATHS",
        "RELEVANCE_WEIGHTS",
        "build_adjacency_dict",
        "compute_precision_at_k",
        "evaluate_similarity",
        "get_filter_set",
        "jaccard_similarity",
        "load_embeddings",
        "load_pairs",
        "load_test_set",
        "create_training_run",
        "track_artifact",
        "track_evaluation_metrics",
        "track_hyperparameter_result",
        "track_training_metrics",
    ]
except ImportError:
    __all__ = [
        "GAME_FILTERS",
        "PATHS",
        "RELEVANCE_WEIGHTS",
        "build_adjacency_dict",
        "compute_precision_at_k",
        "evaluate_similarity",
        "get_filter_set",
        "jaccard_similarity",
        "load_embeddings",
        "load_pairs",
        "load_test_set",
    ]
