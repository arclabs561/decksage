#!/usr/bin/env python3
"""
Weighted Late Fusion for Multi-Modal Card Similarity

This module implements manual fusion (weighted combination) of similarity signals.
For learned reranking (learning-to-rank), see src/ml/reranking/learned_reranker.py

Combines multiple similarity signals:
1. Embedding similarity (cosine similarity in embedding space)
2. Jaccard similarity (co-occurrence graph)
3. Functional tag similarity (Jaccard on functional tags)
4. Text embedding similarity (instruction-tuned embeddings)
5. Visual embedding similarity (SigLIP/CLIP on card images)
6. GNN embedding similarity (GraphSAGE learned representations)
7. Pack embedding similarity (pack-level co-occurrence embeddings)

Supports multiple aggregation methods:
- rrf: Reciprocal Rank Fusion (default, recommended for heterogeneous signals)
- isr: Inverse Square Root (slower rank decay, gives more weight to lower ranks)
- weighted: Linear combination of normalized scores (requires weight tuning)
- combsum: Sum of scores
- combmnz: Sum of scores x overlap count (rewards agreement between modalities)
- combmax: Maximum of scores
- combmin: Minimum of scores

Also supports MMR (Maximal Marginal Relevance) for result diversification.

NOTE: This is manual fusion. For optimal performance, consider using learned reranking
(learning-to-rank) which learns optimal feature combination from labeled data.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, fields
from typing import Any


logger = logging.getLogger(__name__)

# Canonical ordered list of signal names, matching FusionWeights field order.
_SIGNAL_NAMES: tuple[str, ...] = (
    "embed",
    "jaccard",
    "functional",
    "text_embed",
    "visual_embed",
    "sideboard",
    "temporal",
    "gnn",
    "pack_embed",
    "archetype",
    "format",
)


def _clamp01(x: float) -> float:
    """Clamp value to [0, 1] range."""
    return max(0.0, min(1.0, x))


def _cosine_to_unit(c: float) -> float:
    """Map cosine similarity [-1, 1] to [0, 1] range."""
    return _clamp01((c + 1.0) / 2.0)


def _jaccard_sets(a: set[str], b: set[str]) -> float:
    """Compute Jaccard similarity between two sets."""
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return float(inter) / float(union) if union else 0.0


@dataclass
class FusionWeights:
    """Weights for combining different similarity modalities.

    Default weights match recommended hybrid system configuration:
    - GNN: 30% (multi-hop, new cards, inductive learning)
    - Instruction-tuned: 25% (zero-shot, semantic understanding)
    - Co-occurrence: 20% (established patterns, Node2Vec/PecanPy)
    - Visual: 20% (visual similarity from card images)
    - Jaccard: 15% (direct co-occurrence)
    - Functional: 10% (role-based similarity)
    """

    embed: float = 0.20  # Co-occurrence embeddings (Node2Vec/PecanPy)
    jaccard: float = 0.15  # Direct co-occurrence (Jaccard similarity)
    functional: float = 0.10  # Functional tag similarity (role-based)
    text_embed: float = 0.25  # Instruction-tuned embeddings (zero-shot, semantic)
    visual_embed: float = 0.20  # Visual embeddings (card images, CLIP/SigLIP)
    sideboard: float = 0.0  # Sideboard co-occurrence signal (optional)
    temporal: float = 0.0  # Temporal trend signal (optional)
    gnn: float = 0.30  # GNN-learned embeddings (GraphSAGE, multi-hop)
    pack_embed: float = 0.0  # Pack-level co-occurrence embeddings (optional)
    archetype: float = 0.0  # Archetype staples and co-occurrence (optional)
    format: float = 0.0  # Format-specific and cross-format patterns (optional)

    def to_dict(self) -> dict[str, float]:
        """Return weights as a dict keyed by signal name."""
        return {f.name: getattr(self, f.name) for f in fields(self)}

    def normalized(self) -> FusionWeights:
        """Return normalized weights that sum to 1.0."""
        d = self.to_dict()
        total = sum(d.values())
        if total <= 0.0:
            return FusionWeights(
                embed=0.15,
                jaccard=0.15,
                functional=0.15,
                text_embed=0.10,
                visual_embed=0.10,
                sideboard=0.10,
                temporal=0.05,
                gnn=0.10,
                pack_embed=0.0,
                archetype=0.10,
                format=0.10,
            )
        return FusionWeights(**{k: v / total for k, v in d.items()})


class WeightedLateFusion:
    """
    Weighted late fusion of multiple similarity signals.

    Combines embedding, Jaccard, and functional tag similarities
    using configurable weights and aggregation methods.
    """

    # Signal registry: signal_name -> method_name.
    # "jaccard" is None because it is special-cased for optimization
    # (pre-computed query_neighbors).
    _SIGNAL_COMPUTERS: dict[str, str | None] = {
        "embed": "_get_embedding_similarity",
        "jaccard": None,
        "functional": "_get_functional_tag_similarity",
        "text_embed": "_get_text_embedding_similarity",
        "visual_embed": "_get_visual_embedding_similarity",
        "sideboard": "_get_sideboard_similarity",
        "temporal": "_get_temporal_similarity",
        "gnn": "_get_gnn_similarity",
        "pack_embed": "_get_pack_embed_similarity",
        "archetype": "_get_archetype_similarity",
        "format": "_get_format_similarity",
    }

    def __init__(
        self,
        embeddings: Any | None = None,
        adj: dict[str, set[str]] | None = None,
        tagger: Any | None = None,
        weights: FusionWeights | None = None,
        aggregator: str = "rrf",  # RRF recommended for heterogeneous signals (more robust than weighted)
        rrf_k: int = 60,
        mmr_lambda: float = 0.0,
        candidate_topn: int = 100,
        text_embedder: Any | None = None,
        visual_embedder: Any | None = None,
        card_data: dict[str, dict[str, Any]] | None = None,
        sideboard_cooccurrence: dict[str, dict[str, float]] | None = None,
        temporal_cooccurrence: dict[str, dict[str, dict[str, float]]] | None = None,
        gnn_embedder: Any | None = None,
        pack_embeddings: Any | None = None,
        archetype_staples: dict[str, dict[str, float]] | None = None,
        archetype_cooccurrence: dict[str, dict[str, float]] | None = None,
        format_cooccurrence: dict[str, dict[str, dict[str, float]]] | None = None,
        cross_format_patterns: dict[str, dict[str, float]] | None = None,
        task_type: str | None = None,
        graph: Any | None = None,  # IncrementalCardGraph instance for enhanced temporal similarity
        adaptive_visual_weights: bool = True,  # Adjust visual weights based on coverage
        graph_weights: dict | None = None,  # Edge weights for candidate capping
    ):
        """
        Initialize fusion model.

        Args:
            embeddings: Embedding model with `similarity(q, c)` and `most_similar(q, topn)` methods
            adj: Adjacency dict mapping card -> set of neighbors
            tagger: Functional tagger with `tag_card(name)` method returning tags object
            weights: FusionWeights instance (will be normalized)
            aggregator: "rrf", "isr", "weighted", "combsum", "combmnz", "combmax", "combmin"
            rrf_k: RRF constant (typically 60)
            mmr_lambda: MMR diversification parameter (0.0 = no diversification, 1.0 = max diversity)
            candidate_topn: Number of candidates to consider from each modality before fusion
            text_embedder: Optional CardTextEmbedder instance for text embeddings
            visual_embedder: Optional CardVisualEmbedder instance for visual embeddings
            card_data: Optional dict mapping card name -> card dict (for Oracle text access)
            sideboard_cooccurrence: Optional dict mapping card -> dict of co-occurring cards -> frequency
            temporal_cooccurrence: Optional dict mapping month -> card -> co-occurring card -> frequency
            gnn_embedder: Optional GNN embedder (CardGNNEmbedder) for learned graph representations
            pack_embeddings: Optional pack-level embedding model with similarity(q, c) and most_similar(q, topn) methods
            archetype_staples: Optional dict mapping card -> archetype -> frequency
            archetype_cooccurrence: Optional dict mapping card -> co-occurring card -> frequency (within archetypes)
            format_cooccurrence: Optional dict mapping format -> card -> co-occurring card -> frequency
            cross_format_patterns: Optional dict mapping card -> co-occurring card -> cross-format frequency
            graph: Optional IncrementalCardGraph instance for enhanced temporal similarity with monthly_counts
            task_type: Optional task type for instruction-tuned embeddings (e.g., "substitution", "completion", "synergy")
        """
        # Apply task-specific weights if task_type provided
        base_weights = weights or FusionWeights()
        if task_type:
            try:
                from ..utils.fusion_improvements import create_task_specific_weights

                self.weights = create_task_specific_weights(task_type, base_weights).normalized()
            except ImportError:
                # Fallback if fusion_improvements not available
                self.weights = base_weights.normalized()
        else:
            self.weights = base_weights.normalized()

        self.embeddings = embeddings
        self.adj = adj or {}
        self.tagger = tagger
        self.text_embedder = text_embedder
        self.visual_embedder = visual_embedder
        self.card_data = card_data or {}
        self.sideboard_cooccurrence = sideboard_cooccurrence or {}
        self.temporal_cooccurrence = temporal_cooccurrence or {}
        self.gnn_embedder = gnn_embedder
        self.pack_embeddings = pack_embeddings
        self.archetype_staples = archetype_staples or {}
        self.archetype_cooccurrence = archetype_cooccurrence or {}
        self.format_cooccurrence = format_cooccurrence or {}
        self.cross_format_patterns = cross_format_patterns or {}
        self.graph = graph  # IncrementalCardGraph for enhanced temporal similarity
        self._weights_cache = graph_weights or {}
        self.aggregator = aggregator
        self.adaptive_visual_weights = adaptive_visual_weights

        # Adjust weights based on visual coverage if adaptive mode enabled
        if adaptive_visual_weights and visual_embedder and weights and weights.visual_embed > 0.0:
            try:
                from ..utils.visual_coverage import (
                    adjust_weights_for_coverage,
                    compute_visual_coverage,
                )

                coverage = compute_visual_coverage(visual_embedder, card_data)
                if coverage["coverage_rate"] < 0.1:  # Less than 10% coverage
                    logger.info(
                        f"Low visual coverage ({coverage['coverage_rate']:.1%}), "
                        f"adjusting weights (original visual_embed={weights.visual_embed:.3f})"
                    )
                    weights = adjust_weights_for_coverage(weights, coverage["coverage_rate"])
                    logger.info(f"Adjusted visual_embed weight: {weights.visual_embed:.3f}")
            except (ImportError, AttributeError, KeyError, ValueError) as e:
                logger.debug(f"Failed to adjust weights for coverage: {e}")
        self.rrf_k = rrf_k
        self.mmr_lambda = mmr_lambda
        self.candidate_topn = candidate_topn
        self.task_type = task_type

        # Pre-compute the weights dict for use in aggregation hot path.
        self._weights_dict = self.weights.to_dict()

    def _get_embedding_similarity(self, query: str, candidate: str) -> float:
        """Get embedding similarity between query and candidate."""
        if not self.embeddings:
            return 0.0
        if query not in self.embeddings or candidate not in self.embeddings:
            return 0.0
        try:
            sim = self.embeddings.similarity(query, candidate)
            return _cosine_to_unit(sim)
        except (KeyError, RuntimeError, ValueError):
            return 0.0

    def _get_jaccard_similarity(self, query: str, candidate: str) -> float:
        """Get Jaccard similarity from co-occurrence graph."""
        if not self.adj or query not in self.adj:
            return 0.0
        query_neighbors = self.adj[query]
        if candidate not in self.adj:
            return 0.0
        candidate_neighbors = self.adj[candidate]
        return _jaccard_sets(query_neighbors, candidate_neighbors)

    def _get_functional_tag_similarity(self, query: str, candidate: str) -> float:
        """Get functional tag similarity using Jaccard on tag sets."""
        if not self.tagger:
            return 0.0
        try:
            from ..utils.tagger_utils import extract_tag_set

            query_tags = self.tagger.tag_card(query)
            candidate_tags = self.tagger.tag_card(candidate)

            # Taggers can return dicts, dataclasses, or regular classes. Use the
            # shared extraction utility for consistent behavior.
            query_tag_set = extract_tag_set(query_tags, exclude_fields={"card_name"})
            candidate_tag_set = extract_tag_set(candidate_tags, exclude_fields={"card_name"})

            return _jaccard_sets(query_tag_set, candidate_tag_set)
        except Exception:
            return 0.0

    def _get_text_embedding_similarity(
        self, query: str, candidate: str, task_type: str | None = None,
    ) -> float:
        """Get text embedding similarity from card Oracle text."""
        if not self.text_embedder:
            return 0.0
        try:
            # Get card data if available
            query_card = self.card_data.get(query) or self.card_data.get(query.lower())
            candidate_card = self.card_data.get(candidate) or self.card_data.get(candidate.lower())

            # Use card dict if available, otherwise use name string
            query_input = query_card if query_card else query
            candidate_input = candidate_card if candidate_card else candidate

            # Check if it's instruction-tuned embedder (has instruction support)
            if hasattr(self.text_embedder, "similarity"):
                # Instruction-tuned embedder - use task-specific instruction if available
                instruction_type = task_type or self.task_type or "substitution"
                similarity = self.text_embedder.similarity(
                    query_input,
                    candidate_input,
                    instruction_type=instruction_type,
                )
            else:
                # Legacy text embedder
                similarity = self.text_embedder.similarity(query_input, candidate_input)

            return float(similarity)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return 0.0

    def _get_visual_embedding_similarity(self, query: str, candidate: str) -> float:
        """Get visual embedding similarity from card image URLs."""
        if not self.visual_embedder:
            return 0.0

        try:
            # Get card data if available (same pattern as text embeddings)
            query_card_data = (
                self.card_data.get(query) or self.card_data.get(query.lower())
                if self.card_data
                else None
            )
            candidate_card_data = (
                self.card_data.get(candidate) or self.card_data.get(candidate.lower())
                if self.card_data
                else None
            )

            # Use card dict if available, otherwise use name string
            query_input = query_card_data if query_card_data else query
            candidate_input = candidate_card_data if candidate_card_data else candidate

            # Visual embedder handles card dicts, name strings, or PIL Images
            similarity = self.visual_embedder.similarity(query_input, candidate_input)
            return float(similarity)
        except (AttributeError, RuntimeError, OSError, ValueError):
            # Gracefully handle errors (missing images, download failures, etc.)
            return 0.0

    def _get_sideboard_similarity(self, query: str, candidate: str) -> float:
        """Get sideboard co-occurrence similarity."""
        if not self.sideboard_cooccurrence:
            return 0.0
        try:
            query_sb = self.sideboard_cooccurrence.get(query, {})
            return float(query_sb.get(candidate, 0.0))
        except (KeyError, TypeError):
            return 0.0

    def _get_temporal_similarity(
        self,
        query: str,
        candidate: str,
        format: str | None = None,
        game: str | None = None,
    ) -> float:
        """
        Get temporal co-occurrence similarity (weighted by recency and format awareness).

        Enhanced version that uses Edge monthly_counts if graph is available,
        otherwise falls back to temporal_cooccurrence dict.

        Args:
            query: Query card name
            candidate: Candidate card name
            format: Format name (e.g., "Standard", "Modern") for format-aware weighting
            game: Game name ("MTG", "PKM", "YGO") for format-aware weighting

        Returns:
            Temporal similarity score (0-1)
        """
        # Try to get edge from graph if available
        edge = None
        if hasattr(self, "graph") and self.graph:
            try:
                from ml.data.incremental_graph import IncrementalCardGraph

                if isinstance(self.graph, IncrementalCardGraph):
                    edge_key = tuple(sorted([query, candidate]))
                    edge = self.graph.edges.get(edge_key)
            except (ImportError, AttributeError):
                pass

        # If we have an edge with monthly_counts, use enhanced computation
        if edge and edge.monthly_counts:
            return self._get_temporal_similarity_from_edge(edge, format, game)

        # Fallback to existing temporal_cooccurrence dict
        if not self.temporal_cooccurrence:
            return 0.0

        try:
            # Get all months sorted
            months = sorted(self.temporal_cooccurrence.keys())
            if not months:
                return 0.0

            # Weight recent months more heavily
            recent_months = months[-3:] if len(months) >= 3 else months
            total_score = 0.0
            total_weight = 0.0

            for i, month in enumerate(recent_months):
                weight = i + 1  # More recent = higher weight
                month_data = self.temporal_cooccurrence[month]
                query_data = month_data.get(query, {})
                freq = query_data.get(candidate, 0.0)
                total_score += freq * weight
                total_weight += weight

            return float(total_score / total_weight) if total_weight > 0 else 0.0
        except (KeyError, TypeError):
            return 0.0

    def _get_temporal_similarity_from_edge(
        self,
        edge,
        format: str | None = None,
        game: str | None = None,
    ) -> float:
        """
        Compute enhanced temporal similarity from Edge monthly_counts.

        Uses format-aware weighting, recency decay, consistency, and trend signals.

        Args:
            edge: Edge object with monthly_counts
            format: Format name for format-aware weighting
            game: Game name for format-aware weighting

        Returns:
            Enhanced temporal similarity score (0-1)
        """
        try:
            from datetime import datetime

            from ml.data.format_events import (
                get_legal_periods,
                is_legal_in_period,
            )
            from ml.data.temporal_stats import (
                compute_consistency,
                compute_recency_score,
                compute_trend,
            )

            monthly_counts = edge.monthly_counts
            if not monthly_counts:
                return 0.0

            current_date = datetime.now()

            # 1. Recency score (exponential decay)
            recency_score = compute_recency_score(monthly_counts, current_date, decay_days=365.0)

            # 2. Consistency score (prefer stable co-occurrence)
            consistency = compute_consistency(monthly_counts)

            # 3. Trend score (boost if co-occurrence is increasing)
            trend = compute_trend(monthly_counts, lookback_months=6)
            # Normalize trend to 0-1 range (assuming max trend of 10 per month)
            trend_score = max(0.0, min(1.0, (trend + 5.0) / 10.0))  # Shift and scale

            # 4. Format-aware weighting (if format and game provided)
            format_weight = 1.0
            if format and game:
                try:
                    legal_periods = get_legal_periods(game, format, current_date)

                    # Count occurrences in current legal period vs historical
                    current_period_count = 0
                    historical_period_count = 0

                    for month_key, count in monthly_counts.items():
                        try:
                            month_date = datetime.strptime(month_key, "%Y-%m")
                            if is_legal_in_period(month_date, legal_periods):
                                current_period_count += count
                            else:
                                historical_period_count += count
                        except ValueError:
                            continue

                    total_count = current_period_count + historical_period_count
                    if total_count > 0:
                        # Weight current period 2x higher than historical
                        format_weight = (
                            current_period_count * 2.0 + historical_period_count * 0.3
                        ) / total_count
                except (ImportError, KeyError, ValueError, AttributeError):
                    # If format events lookup fails, use default weight
                    pass

            # Combine signals
            base_score = recency_score * format_weight
            enhanced_score = (
                base_score * 0.4  # Recency + format awareness
                + consistency * 0.3  # Consistency
                + trend_score * 0.2  # Trend
                + 0.1  # Small baseline
            )

            return float(min(1.0, enhanced_score))

        except ImportError:
            # Fallback if temporal_stats module not available
            # Simple recency-weighted average
            sorted_months = sorted(monthly_counts.keys())
            recent_months = sorted_months[-3:] if len(sorted_months) >= 3 else sorted_months

            total_score = 0.0
            total_weight = 0.0

            for i, month in enumerate(recent_months):
                weight = i + 1
                count = monthly_counts.get(month, 0)
                total_score += count * weight
                total_weight += weight

            return float(total_score / total_weight) if total_weight > 0 else 0.0

    def _get_gnn_similarity(self, query: str, candidate: str) -> float:
        """Get GNN embedding similarity."""
        if not self.gnn_embedder:
            return 0.0
        try:
            similarity = self.gnn_embedder.similarity(query, candidate)
            return _cosine_to_unit(similarity)  # Map to [0, 1]
        except (AttributeError, KeyError, RuntimeError, ValueError):
            return 0.0

    def _get_pack_embed_similarity(self, query: str, candidate: str) -> float:
        """Get pack-level embedding similarity."""
        if not self.pack_embeddings:
            return 0.0
        if query not in self.pack_embeddings or candidate not in self.pack_embeddings:
            return 0.0
        try:
            similarity = self.pack_embeddings.similarity(query, candidate)
            return _cosine_to_unit(similarity)  # Map to [0, 1]
        except (AttributeError, KeyError, RuntimeError, ValueError):
            return 0.0

    def _get_archetype_similarity(self, query: str, candidate: str) -> float:
        """Get archetype-based similarity."""
        if not self.archetype_staples or not self.archetype_cooccurrence:
            return 0.0
        try:
            from ..similarity.archetype_signal import archetype_similarity

            return archetype_similarity(
                query,
                candidate,
                self.archetype_staples,
                self.archetype_cooccurrence,
            )
        except (ImportError, KeyError, TypeError):
            return 0.0

    def _get_format_similarity(self, query: str, candidate: str) -> float:
        """Get format-based similarity."""
        if not self.format_cooccurrence:
            return 0.0
        try:
            from ..similarity.format_signal import format_similarity

            return format_similarity(
                query,
                candidate,
                self.format_cooccurrence,
                self.cross_format_patterns,
            )
        except (ImportError, KeyError, TypeError):
            return 0.0

    # ------------------------------------------------------------------
    # Candidate gathering
    # ------------------------------------------------------------------

    def _get_candidates(self, query: str) -> set[str]:
        """Get candidate set from all available modalities.

        Graph neighbors are capped at candidate_topn (default 100) by edge
        weight to avoid O(V) scoring on popular cards (Lightning Bolt has
        4,930 neighbors).
        """
        candidates = set()

        # From adjacency graph -- cap by co-occurrence weight for popular cards
        if self.adj and query in self.adj:
            neighbors = self.adj[query]
            if len(neighbors) <= self.candidate_topn:
                candidates.update(neighbors)
            else:
                # Keep top-N neighbors by edge weight (most co-occurred)
                if self._weights_cache:
                    scored = []
                    for n in neighbors:
                        w = self._weights_cache.get((query, n), 0)
                        scored.append((n, w))
                    scored.sort(key=lambda x: -x[1])
                    candidates.update(n for n, _ in scored[: self.candidate_topn])
                else:
                    # No weights available -- take arbitrary subset
                    candidates.update(list(neighbors)[: self.candidate_topn])
            # 2-hop only if very few 1-hop neighbors
            if len(neighbors) < 10:
                for neighbor in list(neighbors)[:5]:
                    if neighbor in self.adj:
                        for n2 in list(self.adj[neighbor])[: self.candidate_topn]:
                            candidates.add(n2)

        # From embeddings (fast, always include)
        if self.embeddings and query in self.embeddings:
            try:
                similar = self.embeddings.most_similar(
                    query, topn=min(self.candidate_topn, 50)
                )  # Limit to 50
                candidates.update(card for card, _ in similar)
            except (KeyError, RuntimeError, ValueError):
                pass

        # From GNN embeddings (skip if not available - expensive)
        if self.gnn_embedder:
            try:
                similar = self.gnn_embedder.most_similar(query, topn=min(self.candidate_topn, 50))
                candidates.update(card for card, _ in similar)
            except (AttributeError, KeyError, RuntimeError):
                pass

        # From pack embeddings
        if self.pack_embeddings and query in self.pack_embeddings:
            try:
                similar = self.pack_embeddings.most_similar(
                    query, topn=min(self.candidate_topn, 50)
                )
                candidates.update(card for card, _ in similar)
            except (AttributeError, KeyError, RuntimeError):
                pass

        # Text embeddings skipped in candidate generation (too slow).

        # Remove query itself
        candidates.discard(query)
        return candidates

    # ------------------------------------------------------------------
    # Similarity scoring
    # ------------------------------------------------------------------

    def _compute_similarity_scores(
        self, query: str, candidates: set[str], task_type: str | None = None,
    ) -> dict[str, dict[str, float]]:
        """Compute similarity scores for all modalities (optimized)."""
        scores = {c: {} for c in candidates}
        wd = self._weights_dict

        # Pre-compute query neighbors for Jaccard (used for all candidates)
        query_neighbors = self.adj.get(query, set()) if self.adj else set()
        query_neighbors_len = len(query_neighbors)

        # Determine which signals to compute (non-zero weight).
        active_signals = [sig for sig in _SIGNAL_NAMES if wd[sig] > 0.0]

        for candidate in candidates:
            for sig in active_signals:
                if sig == "jaccard":
                    # Optimized inline Jaccard using pre-computed query_neighbors
                    candidate_neighbors = self.adj.get(candidate, set()) if self.adj else set()
                    intersection = len(query_neighbors & candidate_neighbors)
                    union = query_neighbors_len + len(candidate_neighbors) - intersection
                    scores[candidate]["jaccard"] = (
                        float(intersection) / float(union) if union > 0 else 0.0
                    )
                elif sig == "text_embed":
                    # text_embed needs the task_type kwarg
                    scores[candidate]["text_embed"] = self._get_text_embedding_similarity(
                        query, candidate, task_type=task_type,
                    )
                else:
                    method = getattr(self, self._SIGNAL_COMPUTERS[sig])
                    scores[candidate][sig] = method(query, candidate)

        return scores

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def _active_pairs(self, data: dict[str, float]) -> list[tuple[str, float, float]]:
        """Return (signal, weight, value) triples for signals present in *data* with weight > 0."""
        wd = self._weights_dict
        return [
            (sig, wd[sig], data[sig])
            for sig in _SIGNAL_NAMES
            if wd[sig] > 0.0 and sig in data
        ]

    def _aggregate(self, data: dict[str, float], mode: str) -> float:
        """Dispatch aggregation by mode.

        For rank-based modes (rrf, isr) *data* values are integer ranks.
        For score-based modes (weighted, combsum, combmnz, combmax, combmin) *data* values are scores.
        """
        pairs = self._active_pairs(data)
        if not pairs:
            return 0.0

        if mode == "weighted" or mode == "combsum":
            # Both weighted and combsum use w * score in the original code.
            return sum(w * v for _, w, v in pairs)

        if mode == "rrf":
            return sum(w / (self.rrf_k + v) for _, w, v in pairs)

        if mode == "isr":
            return sum(w / math.sqrt(self.rrf_k + v) for _, w, v in pairs)

        if mode == "combmnz":
            score_sum = sum(w * v for _, w, v in pairs)
            return score_sum * len(pairs)

        if mode == "combmax":
            return max(v for _, _, v in pairs)

        if mode == "combmin":
            return min(v for _, _, v in pairs)

        # Default fallback: weighted
        return sum(w * v for _, w, v in pairs)

    # ------------------------------------------------------------------
    # MMR diversification
    # ------------------------------------------------------------------

    def _apply_mmr(
        self, candidates: list[str], scores: dict[str, float], k: int
    ) -> list[tuple[str, float]]:
        """Apply Maximal Marginal Relevance for diversification."""
        if self.mmr_lambda <= 0.0 or len(candidates) <= 1:
            # No diversification, just return top-k
            results = [(c, scores[c]) for c in candidates[:k]]
            results.sort(key=lambda x: x[1], reverse=True)
            return results

        selected = []
        remaining = list(candidates)
        remaining.sort(key=lambda c: scores[c], reverse=True)

        # Greedy MMR selection
        while len(selected) < k and remaining:
            best_candidate = None
            best_mmr = float("-inf")

            for candidate in remaining:
                # Relevance score
                relevance = scores[candidate]

                # Diversity penalty (max similarity to already selected)
                max_sim = 0.0
                if selected:
                    for sel in selected:
                        # Use Jaccard as diversity measure
                        sim = self._get_jaccard_similarity(candidate, sel)
                        max_sim = max(max_sim, sim)

                # MMR score: relevance - lambda * max_similarity
                mmr_score = relevance - self.mmr_lambda * max_sim

                if mmr_score > best_mmr:
                    best_mmr = mmr_score
                    best_candidate = candidate

            if best_candidate:
                selected.append(best_candidate)
                remaining.remove(best_candidate)
            else:
                break

        return [(c, scores[c]) for c in selected]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def similar(
        self, query: str, k: int = 10, task_type: str | None = None
    ) -> list[tuple[str, float]]:
        """
        Find similar cards to query.

        Args:
            query: Card name to find similarities for
            k: Number of results to return
            task_type: Optional task type override (e.g., "substitution", "completion", "synergy")
                      If provided, temporarily overrides instance task_type for this call

        Returns:
            List of (card_name, similarity_score) tuples, sorted by score descending
        """
        effective_task_type = task_type or self.task_type

        if query not in self.adj and (not self.embeddings or query not in self.embeddings):
            return []

        candidates = self._get_candidates(query)
        if not candidates:
            return []

        # Compute similarity scores for all modalities
        modality_scores = self._compute_similarity_scores(
            query, candidates, task_type=effective_task_type,
        )

        # Aggregate scores based on method
        if self.aggregator in ("rrf", "isr"):
            # For rank-based aggregators, convert scores to ranks per modality.
            # Collect all active signal names present in scores.
            active_sigs = [
                sig for sig in _SIGNAL_NAMES
                if self._weights_dict[sig] > 0.0
            ]

            # Build per-signal ranked lists and convert to rank dicts.
            per_signal_ranked: dict[str, list[tuple[str, float]]] = {
                sig: [] for sig in active_sigs
            }
            for candidate in candidates:
                cs = modality_scores[candidate]
                for sig in active_sigs:
                    if sig in cs:
                        per_signal_ranked[sig].append((candidate, cs[sig]))

            # Sort each signal's list descending by score.
            for sig in active_sigs:
                per_signal_ranked[sig].sort(key=lambda x: x[1], reverse=True)

            # Build per-candidate rank dicts.
            ranks: dict[str, dict[str, int]] = {}
            for sig in active_sigs:
                for rank, (cand, _) in enumerate(per_signal_ranked[sig], start=1):
                    if cand not in ranks:
                        ranks[cand] = {}
                    ranks[cand][sig] = rank

            # Compute fused scores.
            fused_scores = {
                cand: self._aggregate(ranks.get(cand, {}), self.aggregator)
                for cand in candidates
            }

        else:
            # Score-based aggregators use modality_scores directly.
            fused_scores = {
                cand: self._aggregate(modality_scores[cand], self.aggregator)
                for cand in candidates
            }

        # Sort by score
        sorted_candidates = sorted(
            candidates, key=lambda c: fused_scores.get(c, 0.0), reverse=True
        )

        # Apply MMR if needed
        if self.mmr_lambda > 0.0:
            results = self._apply_mmr(sorted_candidates, fused_scores, k)
        else:
            results = [(c, fused_scores[c]) for c in sorted_candidates[:k]]

        return results

    def similar_multi(self, queries: list[str], k: int = 10) -> list[tuple[str, float]]:
        """
        Find similar cards for multiple queries (multi-query fusion).

        Args:
            queries: List of card names
            k: Number of results to return

        Returns:
            List of (card_name, similarity_score) tuples, sorted by score descending
        """
        if not queries:
            return []

        # Get candidates from all queries
        all_candidates = set()
        for query in queries:
            all_candidates.update(self._get_candidates(query))

        if not all_candidates:
            return []

        # Compute scores for each query-candidate pair
        candidate_scores = {}
        for candidate in all_candidates:
            scores = []
            for query in queries:
                if query not in self.adj and (not self.embeddings or query not in self.embeddings):
                    continue

                modality_scores = self._compute_similarity_scores(query, {candidate})
                if candidate in modality_scores:
                    candidate_modality = modality_scores[candidate]
                    score = self._aggregate(candidate_modality, self.aggregator)
                    scores.append(score)

            if scores:
                # Average across queries
                candidate_scores[candidate] = sum(scores) / len(scores)

        # Sort and return top-k
        sorted_candidates = sorted(candidate_scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_candidates[:k]


__all__ = ["FusionWeights", "WeightedLateFusion", "_clamp01", "_cosine_to_unit", "_jaccard_sets"]
