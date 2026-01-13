"""Learning-to-Rank reranking module.

This module provides learned reranking capabilities for combining multiple
similarity signals using gradient boosting models (LightGBM/XGBoost).

Key components:
- LearnedReranker: Main reranker class that uses trained models
- extract_ltr_features: Comprehensive feature extraction for LTR
- HybridSearchWithReranking: Two-stage pipeline (retrieve → rerank)
"""

from ml.reranking.feature_extraction import extract_ltr_features
from ml.reranking.hybrid_search import HybridSearchWithReranking
from ml.reranking.learned_reranker import LearnedReranker


__all__ = [
    "HybridSearchWithReranking",
    "LearnedReranker",
    "extract_ltr_features",
]
