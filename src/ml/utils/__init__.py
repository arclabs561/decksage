"""Shared utilities for multi-game ML experiments."""

from .constants import GAME_FILTERS, RELEVANCE_WEIGHTS, get_filter_set
from .data_loading import build_adjacency_dict, load_embeddings, load_pairs, load_test_set
from .evaluation import compute_precision_at_k, evaluate_similarity, jaccard_similarity
from .paths import PATHS


# Annotation utilities (optional - may not be available in all contexts)
try:
    from . import annotation_utils as _annotation_utils
except ImportError:
    HAS_ANNOTATION_UTILS = False
    _annotation_utils = None  # type: ignore[assignment]
else:
    HAS_ANNOTATION_UTILS = True
    convert_annotations_to_substitution_pairs = (
        _annotation_utils.convert_annotations_to_substitution_pairs
    )
    extract_substitution_pairs_from_annotations = (
        _annotation_utils.extract_substitution_pairs_from_annotations
    )
    load_hand_annotations = _annotation_utils.load_hand_annotations
    load_similarity_annotations = _annotation_utils.load_similarity_annotations

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
        "create_training_run",
        "evaluate_similarity",
        "get_filter_set",
        "jaccard_similarity",
        "load_embeddings",
        "load_pairs",
        "load_test_set",
        "track_artifact",
        "track_evaluation_metrics",
        "track_hyperparameter_result",
        "track_training_metrics",
    ]
    if HAS_ANNOTATION_UTILS:
        __all__.extend(
            [
                "convert_annotations_to_substitution_pairs",
                "extract_substitution_pairs_from_annotations",
                "load_hand_annotations",
                "load_similarity_annotations",
            ]
        )
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
    if HAS_ANNOTATION_UTILS:
        __all__.extend(
            [
                "convert_annotations_to_substitution_pairs",
                "extract_substitution_pairs_from_annotations",
                "load_hand_annotations",
                "load_similarity_annotations",
            ]
        )
