"""Shared utilities for multi-game ML experiments.

Exports are lazy. Importing ``ml.utils`` previously pulled pandas, gensim, and
the annotation stack through ``data_loading``; a script that needed one small
helper paid for all of it. ``__getattr__`` resolves each name on first use.
"""

from __future__ import annotations

import importlib
from typing import Any


_EXPORTS = {
    "GAME_FILTERS": "constants",
    "RELEVANCE_WEIGHTS": "constants",
    "get_filter_set": "constants",
    "build_adjacency_dict": "data_loading",
    "load_embeddings": "data_loading",
    "load_pairs": "data_loading",
    "load_test_set": "data_loading",
    "compute_precision_at_k": "evaluation",
    "evaluate_similarity": "evaluation",
    "jaccard_similarity": "evaluation",
    "PATHS": "paths",
    "convert_annotations_to_substitution_pairs": "annotation_utils",
    "extract_substitution_pairs_from_annotations": "annotation_utils",
    "load_hand_annotations": "annotation_utils",
    "load_similarity_annotations": "annotation_utils",
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(f".{module}", __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
