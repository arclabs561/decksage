#!/usr/bin/env python3
"""
Weighted Late Fusion for Multi-Modal Card Similarity

Combines three similarity signals:
1. Embedding similarity (cosine similarity in embedding space)
2. Jaccard similarity (co-occurrence graph)
3. Functional tag similarity (Jaccard on functional tags)

Supports multiple aggregation methods:
- weighted: Linear combination of normalized scores
- rrf: Reciprocal Rank Fusion
- combsum: Sum of scores
- combmax: Maximum of scores
- combmin: Minimum of scores

Also supports MMR (Maximal Marginal Relevance) for result diversification.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


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
    - Jaccard: 15% (direct co-occurrence)
    - Functional: 10% (role-based similarity)
    """

    embed: float = 0.20  # Co-occurrence embeddings (Node2Vec/PecanPy)
    jaccard: float = 0.15  # Direct co-occurrence (Jaccard similarity)
    functional: float = 0.10  # Functional tag similarity (role-based)
    text_embed: float = 0.25  # Instruction-tuned embeddings (zero-shot, semantic)
    sideboard: float = 0.0  # Sideboard co-occurrence signal (optional)
    temporal: float = 0.0  # Temporal trend signal (optional)
    gnn: float = 0.30  # GNN-learned embeddings (GraphSAGE, multi-hop)
    archetype: float = 0.0  # Archetype staples and co-occurrence (optional)
    format: float = 0.0  # Format-specific and cross-format patterns (optional)

    def normalized(self) -> FusionWeights:
        """Return normalized weights that sum to 1.0."""
        total = self.embed + self.jaccard + self.functional + self.text_embed + self.sideboard + self.temporal + self.gnn + self.archetype + self.format
        if total <= 0.0:
            return FusionWeights(embed=0.15, jaccard=0.15, functional=0.15, text_embed=0.10, sideboard=0.10, temporal=0.05, gnn=0.10, archetype=0.10, format=0.10)
        return FusionWeights(
            embed=self.embed / total,
            jaccard=self.jaccard / total,
            functional=self.functional / total,
            text_embed=self.text_embed / total,
            sideboard=self.sideboard / total,
            temporal=self.temporal / total,
            gnn=self.gnn / total,
            archetype=self.archetype / total,
            format=self.format / total,
        )


class WeightedLateFusion:
    """
    Weighted late fusion of multiple similarity signals.

    Combines embedding, Jaccard, and functional tag similarities
    using configurable weights and aggregation methods.
    """

    def __init__(
        self,
        embeddings: Optional[Any] = None,
        adj: Optional[dict[str, set[str]]] = None,
        tagger: Optional[Any] = None,
        weights: Optional[FusionWeights] = None,
        aggregator: str = "weighted",
        rrf_k: int = 60,
        mmr_lambda: float = 0.0,
        candidate_topn: int = 100,
        text_embedder: Optional[Any] = None,
        card_data: Optional[dict[str, dict[str, Any]]] = None,
        sideboard_cooccurrence: Optional[dict[str, dict[str, float]]] = None,
        temporal_cooccurrence: Optional[dict[str, dict[str, dict[str, float]]]] = None,
        gnn_embedder: Optional[Any] = None,
        archetype_staples: Optional[dict[str, dict[str, float]]] = None,
        archetype_cooccurrence: Optional[dict[str, dict[str, float]]] = None,
        format_cooccurrence: Optional[dict[str, dict[str, dict[str, float]]]] = None,
        cross_format_patterns: Optional[dict[str, dict[str, float]]] = None,
        task_type: Optional[str] = None,
        graph: Optional[Any] = None,  # IncrementalCardGraph instance for enhanced temporal similarity
    ):
        """
        Initialize fusion model.

        Args:
            embeddings: Embedding model with `similarity(q, c)` and `most_similar(q, topn)` methods
            adj: Adjacency dict mapping card -> set of neighbors
            tagger: Functional tagger with `tag_card(name)` method returning tags object
            weights: FusionWeights instance (will be normalized)
            aggregator: "weighted", "rrf", "combsum", "combmax", "combmin"
            rrf_k: RRF constant (typically 60)
            mmr_lambda: MMR diversification parameter (0.0 = no diversification, 1.0 = max diversity)
            candidate_topn: Number of candidates to consider from each modality before fusion
            text_embedder: Optional CardTextEmbedder instance for text embeddings
            card_data: Optional dict mapping card name -> card dict (for Oracle text access)
            sideboard_cooccurrence: Optional dict mapping card -> dict of co-occurring cards -> frequency
            temporal_cooccurrence: Optional dict mapping month -> card -> co-occurring card -> frequency
            gnn_embedder: Optional GNN embedder (CardGNNEmbedder) for learned graph representations
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
        self.card_data = card_data or {}
        self.sideboard_cooccurrence = sideboard_cooccurrence or {}
        self.temporal_cooccurrence = temporal_cooccurrence or {}
        self.gnn_embedder = gnn_embedder
        self.archetype_staples = archetype_staples or {}
        self.archetype_cooccurrence = archetype_cooccurrence or {}
        self.format_cooccurrence = format_cooccurrence or {}
        self.cross_format_patterns = cross_format_patterns or {}
        self.graph = graph  # IncrementalCardGraph for enhanced temporal similarity
        self.aggregator = aggregator
        self.rrf_k = rrf_k
        self.mmr_lambda = mmr_lambda
        self.candidate_topn = candidate_topn
        self.task_type = task_type
        
        # OPTIMIZATION: Cache for similarity computations (LRU cache for repeated queries)
        self._similarity_cache: dict[tuple[str, str, str], float] = {}  # (query, candidate, modality) -> score
        self._cache_max_size = 10000  # Limit cache size to prevent memory issues

    def _get_embedding_similarity(self, query: str, candidate: str) -> float:
        """Get embedding similarity between query and candidate."""
        if not self.embeddings:
            return 0.0
        if query not in self.embeddings or candidate not in self.embeddings:
            return 0.0
        try:
            sim = self.embeddings.similarity(query, candidate)
            return _cosine_to_unit(sim)
        except Exception:
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
            from dataclasses import asdict

            query_tags = self.tagger.tag_card(query)
            candidate_tags = self.tagger.tag_card(candidate)

            # Extract boolean fields that are True
            query_tag_set = {k for k, v in asdict(query_tags).items() if isinstance(v, bool) and v}
            candidate_tag_set = {k for k, v in asdict(candidate_tags).items() if isinstance(v, bool) and v}

            return _jaccard_sets(query_tag_set, candidate_tag_set)
        except Exception:
            return 0.0

    def _get_text_embedding_similarity(self, query: str, candidate: str) -> float:
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
            if hasattr(self.text_embedder, 'similarity'):
                # Instruction-tuned embedder - use task-specific instruction if available
                instruction_type = self.task_type or "substitution"  # Default to substitution
                similarity = self.text_embedder.similarity(
                    query_input,
                    candidate_input,
                    instruction_type=instruction_type,
                )
            else:
                # Legacy text embedder
                similarity = self.text_embedder.similarity(query_input, candidate_input)
            
            return float(similarity)
        except Exception:
            return 0.0

    def _get_sideboard_similarity(self, query: str, candidate: str) -> float:
        """Get sideboard co-occurrence similarity."""
        if not self.sideboard_cooccurrence:
            return 0.0
        try:
            query_sb = self.sideboard_cooccurrence.get(query, {})
            return float(query_sb.get(candidate, 0.0))
        except Exception:
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
        if hasattr(self, 'graph') and self.graph:
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
        except Exception:
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
            from ml.data.temporal_stats import (
                compute_recency_score,
                compute_consistency,
                compute_trend,
            )
            from ml.data.format_events import (
                get_legal_periods,
                is_legal_in_period,
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
                        format_weight = (current_period_count * 2.0 + historical_period_count * 0.3) / total_count
                except Exception:
                    # If format events lookup fails, use default weight
                    pass
            
            # Combine signals
            base_score = recency_score * format_weight
            enhanced_score = (
                base_score * 0.4 +  # Recency + format awareness
                consistency * 0.3 +  # Consistency
                trend_score * 0.2 +  # Trend
                0.1  # Small baseline
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
        except Exception:
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
        except Exception:
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
        except Exception:
            return 0.0

    def _get_candidates(self, query: str) -> set[str]:
        """Get candidate set from all available modalities."""
        candidates = set()

        # OPTIMIZATION: Limit 2-hop expansion to reduce candidate set size
        # From adjacency graph (1-hop only for speed)
        if self.adj and query in self.adj:
            candidates.update(self.adj[query])
            # OPTIMIZATION: Skip 2-hop expansion in fast mode (too many candidates)
            # Only do 2-hop if we have very few 1-hop neighbors
            if len(self.adj[query]) < 10:
                for neighbor in list(self.adj[query])[:5]:  # Limit 2-hop expansion
                    if neighbor in self.adj:
                        candidates.update(self.adj[neighbor])

        # From embeddings (fast, always include)
        if self.embeddings and query in self.embeddings:
            try:
                similar = self.embeddings.most_similar(query, topn=min(self.candidate_topn, 50))  # Limit to 50
                candidates.update(card for card, _ in similar)
            except Exception:
                pass
        
        # From GNN embeddings (skip if not available - expensive)
        if self.gnn_embedder:
            try:
                similar = self.gnn_embedder.most_similar(query, topn=min(self.candidate_topn, 50))
                candidates.update(card for card, _ in similar)
            except Exception:
                pass
        
        # OPTIMIZATION: Skip text embeddings in candidate generation (too slow)
        # Text embeddings are only used for similarity scoring, not candidate generation
        # This avoids expensive LLM calls during candidate generation

        # Remove query itself
        candidates.discard(query)
        return candidates

    def _compute_similarity_scores(self, query: str, candidates: set[str]) -> dict[str, dict[str, float]]:
        """Compute similarity scores for all modalities (optimized)."""
        scores = {c: {} for c in candidates}

        # OPTIMIZATION: Pre-compute query neighbors for Jaccard (used for all candidates)
        query_neighbors = self.adj.get(query, set()) if self.adj else set()
        query_neighbors_len = len(query_neighbors)  # Pre-compute length for union calculation
        
        # OPTIMIZATION: Batch process candidates to reduce function call overhead
        candidates_list = list(candidates)
        
        # OPTIMIZATION: Pre-compute which modalities to compute (avoid repeated conditionals)
        compute_embed = self.weights.embed > 0.0
        compute_jaccard = self.weights.jaccard > 0.0
        compute_functional = self.weights.functional > 0.0
        compute_text_embed = self.weights.text_embed > 0.0
        compute_sideboard = self.weights.sideboard > 0.0
        compute_temporal = self.weights.temporal > 0.0
        compute_gnn = self.weights.gnn > 0.0
        
        for candidate in candidates_list:
            # OPTIMIZATION: Only compute modalities with non-zero weights
            if compute_embed:
                scores[candidate]["embed"] = self._get_embedding_similarity(query, candidate)
            if compute_jaccard:
                # OPTIMIZATION: Use pre-computed query_neighbors and optimized Jaccard
                candidate_neighbors = self.adj.get(candidate, set()) if self.adj else set()
                intersection = len(query_neighbors & candidate_neighbors)
                # OPTIMIZATION: Faster union calculation: |A ∪ B| = |A| + |B| - |A ∩ B|
                union = query_neighbors_len + len(candidate_neighbors) - intersection
                scores[candidate]["jaccard"] = float(intersection) / float(union) if union > 0 else 0.0
            if compute_functional:
                scores[candidate]["functional"] = self._get_functional_tag_similarity(query, candidate)
            if compute_text_embed:
                scores[candidate]["text_embed"] = self._get_text_embedding_similarity(query, candidate)
            if compute_sideboard:
                scores[candidate]["sideboard"] = self._get_sideboard_similarity(query, candidate)
            if compute_temporal:
                scores[candidate]["temporal"] = self._get_temporal_similarity(query, candidate)
            if compute_gnn:
                scores[candidate]["gnn"] = self._get_gnn_similarity(query, candidate)

        return scores

    def _aggregate_weighted(self, scores: dict[str, float]) -> float:
        """Weighted linear combination (optimized with vectorized operations)."""
        # OPTIMIZATION: Pre-compute weight-score pairs for enabled modalities
        # This avoids repeated dict lookups and conditionals
        weight_score_pairs = []
        if self.weights.embed > 0.0 and "embed" in scores:
            weight_score_pairs.append((self.weights.embed, scores["embed"]))
        if self.weights.jaccard > 0.0 and "jaccard" in scores:
            weight_score_pairs.append((self.weights.jaccard, scores["jaccard"]))
        if self.weights.functional > 0.0 and "functional" in scores:
            weight_score_pairs.append((self.weights.functional, scores["functional"]))
        if self.weights.text_embed > 0.0 and "text_embed" in scores:
            weight_score_pairs.append((self.weights.text_embed, scores["text_embed"]))
        if self.weights.sideboard > 0.0 and "sideboard" in scores:
            weight_score_pairs.append((self.weights.sideboard, scores["sideboard"]))
        if self.weights.temporal > 0.0 and "temporal" in scores:
            weight_score_pairs.append((self.weights.temporal, scores["temporal"]))
        if self.weights.gnn > 0.0 and "gnn" in scores:
            weight_score_pairs.append((self.weights.gnn, scores["gnn"]))
        if self.weights.archetype > 0.0 and "archetype" in scores:
            weight_score_pairs.append((self.weights.archetype, scores["archetype"]))
        if self.weights.format > 0.0 and "format" in scores:
            weight_score_pairs.append((self.weights.format, scores["format"]))
        
        # OPTIMIZATION: Use sum() with generator for faster computation
        return sum(w * s for w, s in weight_score_pairs)

    def _aggregate_rrf(self, ranks: dict[str, int]) -> float:
        """Reciprocal Rank Fusion."""
        total = 0.0
        if self.weights.embed > 0.0 and "embed" in ranks:
            total += self.weights.embed / (self.rrf_k + ranks["embed"])
        if self.weights.jaccard > 0.0 and "jaccard" in ranks:
            total += self.weights.jaccard / (self.rrf_k + ranks["jaccard"])
        if self.weights.functional > 0.0 and "functional" in ranks:
            total += self.weights.functional / (self.rrf_k + ranks["functional"])
        if self.weights.text_embed > 0.0 and "text_embed" in ranks:
            total += self.weights.text_embed / (self.rrf_k + ranks["text_embed"])
        if self.weights.sideboard > 0.0 and "sideboard" in ranks:
            total += self.weights.sideboard / (self.rrf_k + ranks["sideboard"])
        if self.weights.temporal > 0.0 and "temporal" in ranks:
            total += self.weights.temporal / (self.rrf_k + ranks["temporal"])
        if self.weights.gnn > 0.0 and "gnn" in ranks:
            total += self.weights.gnn / (self.rrf_k + ranks["gnn"])
        if self.weights.archetype > 0.0 and "archetype" in ranks:
            total += self.weights.archetype / (self.rrf_k + ranks["archetype"])
        if self.weights.format > 0.0 and "format" in ranks:
            total += self.weights.format / (self.rrf_k + ranks["format"])
        return total

    def _aggregate_combsum(self, scores: dict[str, float]) -> float:
        """Sum of scores."""
        total = 0.0
        if self.weights.embed > 0.0 and "embed" in scores:
            total += self.weights.embed * scores["embed"]
        if self.weights.jaccard > 0.0 and "jaccard" in scores:
            total += self.weights.jaccard * scores["jaccard"]
        if self.weights.functional > 0.0 and "functional" in scores:
            total += self.weights.functional * scores["functional"]
        if self.weights.text_embed > 0.0 and "text_embed" in scores:
            total += self.weights.text_embed * scores["text_embed"]
        if self.weights.sideboard > 0.0 and "sideboard" in scores:
            total += self.weights.sideboard * scores["sideboard"]
        if self.weights.temporal > 0.0 and "temporal" in scores:
            total += self.weights.temporal * scores["temporal"]
        if self.weights.gnn > 0.0 and "gnn" in scores:
            total += self.weights.gnn * scores["gnn"]
        if self.weights.archetype > 0.0 and "archetype" in scores:
            total += self.weights.archetype * scores["archetype"]
        if self.weights.format > 0.0 and "format" in scores:
            total += self.weights.format * scores["format"]
        return total

    def _aggregate_combmax(self, scores: dict[str, float]) -> float:
        """Maximum of scores (optimized)."""
        # OPTIMIZATION: Collect enabled scores and use max() once
        enabled_scores = []
        if self.weights.embed > 0.0 and "embed" in scores:
            enabled_scores.append(scores["embed"])
        if self.weights.jaccard > 0.0 and "jaccard" in scores:
            enabled_scores.append(scores["jaccard"])
        if self.weights.functional > 0.0 and "functional" in scores:
            enabled_scores.append(scores["functional"])
        if self.weights.text_embed > 0.0 and "text_embed" in scores:
            enabled_scores.append(scores["text_embed"])
        if self.weights.sideboard > 0.0 and "sideboard" in scores:
            enabled_scores.append(scores["sideboard"])
        if self.weights.temporal > 0.0 and "temporal" in scores:
            enabled_scores.append(scores["temporal"])
        if self.weights.gnn > 0.0 and "gnn" in scores:
            enabled_scores.append(scores["gnn"])
        if self.weights.archetype > 0.0 and "archetype" in scores:
            enabled_scores.append(scores["archetype"])
        if self.weights.format > 0.0 and "format" in scores:
            enabled_scores.append(scores["format"])
        return max(enabled_scores) if enabled_scores else 0.0

    def _aggregate_combmin(self, scores: dict[str, float]) -> float:
        """Minimum of scores."""
        min_score = 1.0
        found = False
        if self.weights.embed > 0.0 and "embed" in scores:
            min_score = min(min_score, scores["embed"])
            found = True
        if self.weights.jaccard > 0.0 and "jaccard" in scores:
            min_score = min(min_score, scores["jaccard"])
            found = True
        if self.weights.functional > 0.0 and "functional" in scores:
            min_score = min(min_score, scores["functional"])
            found = True
        if self.weights.text_embed > 0.0 and "text_embed" in scores:
            min_score = min(min_score, scores["text_embed"])
            found = True
        if self.weights.sideboard > 0.0 and "sideboard" in scores:
            min_score = min(min_score, scores["sideboard"])
            found = True
        if self.weights.temporal > 0.0 and "temporal" in scores:
            min_score = min(min_score, scores["temporal"])
            found = True
        if self.weights.gnn > 0.0 and "gnn" in scores:
            min_score = min(min_score, scores["gnn"])
            found = True
        if self.weights.archetype > 0.0 and "archetype" in scores:
            min_score = min(min_score, scores["archetype"])
            found = True
        if self.weights.format > 0.0 and "format" in scores:
            min_score = min(min_score, scores["format"])
            found = True
        return min_score if found else 0.0

    def _apply_mmr(self, candidates: list[str], scores: dict[str, float], k: int) -> list[tuple[str, float]]:
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

    def similar(self, query: str, k: int = 10, task_type: Optional[str] = None) -> list[tuple[str, float]]:
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
        # Use provided task_type for this call, or fall back to instance task_type
        original_task_type = self.task_type
        if task_type is not None:
            self.task_type = task_type
        
        try:
            if query not in self.adj and (not self.embeddings or query not in self.embeddings):
                # Restore original task_type before returning
                if task_type is not None:
                    self.task_type = original_task_type
                return []

            candidates = self._get_candidates(query)
            if not candidates:
                # Restore original task_type before returning
                if task_type is not None:
                    self.task_type = original_task_type
                return []

            # Compute similarity scores for all modalities
            modality_scores = self._compute_similarity_scores(query, candidates)

            # Aggregate scores based on method
            if self.aggregator == "rrf":
                # For RRF, we need ranks instead of scores
                # Build ranked lists per modality
                embed_ranked = []
                jaccard_ranked = []
                functional_ranked = []
                text_embed_ranked = []
                sideboard_ranked = []
                temporal_ranked = []
                gnn_ranked = []
                archetype_ranked = []
                format_ranked = []

                for candidate in candidates:
                    if "embed" in modality_scores[candidate]:
                        embed_ranked.append((candidate, modality_scores[candidate]["embed"]))
                    if "jaccard" in modality_scores[candidate]:
                        jaccard_ranked.append((candidate, modality_scores[candidate]["jaccard"]))
                    if "functional" in modality_scores[candidate]:
                        functional_ranked.append((candidate, modality_scores[candidate]["functional"]))
                    if "text_embed" in modality_scores[candidate]:
                        text_embed_ranked.append((candidate, modality_scores[candidate]["text_embed"]))
                    if "sideboard" in modality_scores[candidate]:
                        sideboard_ranked.append((candidate, modality_scores[candidate]["sideboard"]))
                    if "temporal" in modality_scores[candidate]:
                        temporal_ranked.append((candidate, modality_scores[candidate]["temporal"]))
                    if "gnn" in modality_scores[candidate]:
                        gnn_ranked.append((candidate, modality_scores[candidate]["gnn"]))
                    if "archetype" in modality_scores[candidate]:
                        archetype_ranked.append((candidate, modality_scores[candidate]["archetype"]))
                    if "format" in modality_scores[candidate]:
                        format_ranked.append((candidate, modality_scores[candidate]["format"]))

                embed_ranked.sort(key=lambda x: x[1], reverse=True)
                jaccard_ranked.sort(key=lambda x: x[1], reverse=True)
                functional_ranked.sort(key=lambda x: x[1], reverse=True)
                text_embed_ranked.sort(key=lambda x: x[1], reverse=True)
                sideboard_ranked.sort(key=lambda x: x[1], reverse=True)
                temporal_ranked.sort(key=lambda x: x[1], reverse=True)
                gnn_ranked.sort(key=lambda x: x[1], reverse=True)
                archetype_ranked.sort(key=lambda x: x[1], reverse=True)
                format_ranked.sort(key=lambda x: x[1], reverse=True)

                # Build rank dicts
                ranks = {}
                for rank, (candidate, _) in enumerate(embed_ranked, start=1):
                    if candidate not in ranks:
                        ranks[candidate] = {}
                    ranks[candidate]["embed"] = rank
                for rank, (candidate, _) in enumerate(jaccard_ranked, start=1):
                    if candidate not in ranks:
                        ranks[candidate] = {}
                    ranks[candidate]["jaccard"] = rank
                for rank, (candidate, _) in enumerate(functional_ranked, start=1):
                    if candidate not in ranks:
                        ranks[candidate] = {}
                    ranks[candidate]["functional"] = rank
                for rank, (candidate, _) in enumerate(text_embed_ranked, start=1):
                    if candidate not in ranks:
                        ranks[candidate] = {}
                    ranks[candidate]["text_embed"] = rank
                for rank, (candidate, _) in enumerate(sideboard_ranked, start=1):
                    if candidate not in ranks:
                        ranks[candidate] = {}
                    ranks[candidate]["sideboard"] = rank
                for rank, (candidate, _) in enumerate(temporal_ranked, start=1):
                    if candidate not in ranks:
                        ranks[candidate] = {}
                    ranks[candidate]["temporal"] = rank
                for rank, (candidate, _) in enumerate(gnn_ranked, start=1):
                    if candidate not in ranks:
                        ranks[candidate] = {}
                    ranks[candidate]["gnn"] = rank
                for rank, (candidate, _) in enumerate(archetype_ranked, start=1):
                    if candidate not in ranks:
                        ranks[candidate] = {}
                    ranks[candidate]["archetype"] = rank
                for rank, (candidate, _) in enumerate(format_ranked, start=1):
                    if candidate not in ranks:
                        ranks[candidate] = {}
                    ranks[candidate]["format"] = rank

                # Compute RRF scores
                fused_scores = {}
                for candidate in candidates:
                    candidate_ranks = ranks.get(candidate, {})
                    fused_scores[candidate] = self._aggregate_rrf(candidate_ranks)

            else:
                # For other aggregators, use scores directly
                fused_scores = {}
                for candidate in candidates:
                    candidate_scores = modality_scores[candidate]
                    if self.aggregator == "weighted":
                        fused_scores[candidate] = self._aggregate_weighted(candidate_scores)
                    elif self.aggregator == "combsum":
                        fused_scores[candidate] = self._aggregate_combsum(candidate_scores)
                    elif self.aggregator == "combmax":
                        fused_scores[candidate] = self._aggregate_combmax(candidate_scores)
                    elif self.aggregator == "combmin":
                        fused_scores[candidate] = self._aggregate_combmin(candidate_scores)
                    else:
                        # Default to weighted
                        fused_scores[candidate] = self._aggregate_weighted(candidate_scores)

            # Sort by score
            sorted_candidates = sorted(candidates, key=lambda c: fused_scores.get(c, 0.0), reverse=True)

            # Apply MMR if needed
            if self.mmr_lambda > 0.0:
                results = self._apply_mmr(sorted_candidates, fused_scores, k)
            else:
                results = [(c, fused_scores[c]) for c in sorted_candidates[:k]]
            
            # Restore original task_type
            if task_type is not None:
                self.task_type = original_task_type
            
            return results
        except Exception:
            # Restore task_type on exception
            if task_type is not None:
                self.task_type = original_task_type
            raise
        finally:
            # Ensure task_type is restored even on exception
            if task_type is not None:
                self.task_type = original_task_type

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
                    if self.aggregator == "weighted":
                        score = self._aggregate_weighted(candidate_modality)
                    elif self.aggregator == "combsum":
                        score = self._aggregate_combsum(candidate_modality)
                    elif self.aggregator == "combmax":
                        score = self._aggregate_combmax(candidate_modality)
                    elif self.aggregator == "combmin":
                        score = self._aggregate_combmin(candidate_modality)
                    else:
                        score = self._aggregate_weighted(candidate_modality)
                    scores.append(score)

            if scores:
                # Average across queries
                candidate_scores[candidate] = sum(scores) / len(scores)

        # Sort and return top-k
        sorted_candidates = sorted(candidate_scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_candidates[:k]


__all__ = ["FusionWeights", "WeightedLateFusion", "_clamp01", "_cosine_to_unit", "_jaccard_sets"]

