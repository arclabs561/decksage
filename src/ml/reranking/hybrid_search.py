#!/usr/bin/env python3
"""
Two-stage hybrid search: fast retrieval → learned reranking.

Combines the speed of manual fusion with the quality of learned reranking.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any


logger = logging.getLogger(__name__)


class HybridSearchWithReranking:
    """
    Two-stage search pipeline: retrieve → rerank.

    Stage 1: Fast retrieval using manual fusion (weighted/RRF)
    Stage 2: Learned reranking using trained model (optional)
    """

    def __init__(
        self,
        retriever: Any,  # WeightedLateFusion instance
        reranker: Any | None = None,  # LearnedReranker instance
        feature_extractor: Callable[[str, str], dict[str, float]] | None = None,
        top_k_retrieve: int = 100,  # Retrieve more candidates
        top_k_final: int = 10,  # Final results after reranking
        use_reranking: bool = True,  # Toggle reranking on/off
    ):
        """
        Initialize hybrid search.

        Args:
            retriever: WeightedLateFusion instance for fast retrieval
            reranker: LearnedReranker instance (optional)
            feature_extractor: Function to extract features (optional, auto-created if None)
            top_k_retrieve: Number of candidates to retrieve in stage 1
            top_k_final: Number of final results after reranking
            use_reranking: Whether to use reranking (requires reranker)
        """
        self.retriever = retriever
        self.reranker = reranker
        self.top_k_retrieve = top_k_retrieve
        self.top_k_final = top_k_final
        self.use_reranking = use_reranking and reranker is not None

        # Auto-create feature extractor if not provided
        if feature_extractor is None:
            from ml.reranking.feature_extraction import extract_ltr_features

            # Get card_data from retriever if available
            card_data = getattr(retriever, "card_data", None)

            # Cache for similarity scores per query (to avoid recomputation)
            self._similarity_cache: dict[str, dict[str, dict[str, float]]] = {}
            # Cache for retrieved candidates per query (to speed up rank computation)
            self._query_candidates_cache: dict[str, set[str]] = {}

            def _extract_features(query: str, candidate: str) -> dict[str, float]:
                # Pass cached similarity scores to feature extraction if available
                cached_scores = None
                if query in self._similarity_cache:
                    cached_scores = self._similarity_cache[query].get(candidate)

                limit_candidates = self._query_candidates_cache.get(query)

                # Use optimized feature extraction with cached scores
                from ml.reranking.feature_extraction import extract_ltr_features_optimized

                try:
                    return extract_ltr_features_optimized(
                        query,
                        candidate,
                        retriever,
                        card_data,
                        cached_scores=cached_scores,
                        limit_candidates=limit_candidates,
                    )
                except (AttributeError, ImportError):
                    # Fallback to standard extraction if optimized version not available
                    return extract_ltr_features(query, candidate, retriever, card_data)

            self.feature_extractor = _extract_features
        else:
            self.feature_extractor = feature_extractor

        if self.use_reranking and reranker is None:
            logger.warning("use_reranking=True but no reranker provided. Disabling reranking.")
            self.use_reranking = False

    def search(self, query: str) -> list[tuple[str, float]]:
        """
        Search with optional reranking.

        Args:
            query: Query card name

        Returns:
            List of (card_name, score) tuples, sorted by score descending
        """
        # Stage 1: Fast retrieval (use current fusion for speed)
        try:
            candidates = self.retriever.similar(query, k=self.top_k_retrieve)
        except Exception as e:
            logger.error(f"Error in retrieval stage: {e}")
            return []

        if not candidates:
            return []

        # Cache retrieved candidates for this query (for faster feature extraction)
        candidate_set = {c[0] for c in candidates}
        if hasattr(self, "_query_candidates_cache"):
            self._query_candidates_cache[query] = candidate_set

        # Pre-compute and cache similarity scores for all candidates (one-time cost)
        if hasattr(self, "_similarity_cache") and query not in self._similarity_cache:
            try:
                # Compute similarity scores for all candidates at once
                all_scores = self.retriever._compute_similarity_scores(query, candidate_set)
                self._similarity_cache[query] = all_scores
            except Exception as e:
                logger.warning(f"Error caching similarity scores: {e}")
                # Continue without cache

        if not self.use_reranking:
            # Fallback to manual fusion results
            return candidates[: self.top_k_final]

        # Stage 2: Learned reranking (use LTR for quality)
        try:
            reranked = self.reranker.rerank(
                query=query,
                candidates=[c[0] for c in candidates],
                feature_extractor=self.feature_extractor,
            )

            return reranked[: self.top_k_final]

        except Exception as e:
            logger.warning(f"Error in reranking stage, falling back to retrieval results: {e}")
            # Fallback to manual fusion results
            return candidates[: self.top_k_final]

    def similar(self, query: str, k: int | None = None) -> list[tuple[str, float]]:
        """
        Alias for search() for compatibility with WeightedLateFusion interface.

        Args:
            query: Query card name
            k: Number of results (overrides top_k_final if provided)

        Returns:
            List of (card_name, score) tuples
        """
        if k is not None:
            original_top_k = self.top_k_final
            self.top_k_final = k
            results = self.search(query)
            self.top_k_final = original_top_k
            return results
        return self.search(query)


__all__ = ["HybridSearchWithReranking"]
