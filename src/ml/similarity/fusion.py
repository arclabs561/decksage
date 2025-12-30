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
    """Weights for combining different similarity modalities."""

    embed: float = 0.25  # Node2Vec/PecanPy embeddings (updated based on evaluation: P@10=0.0278)
    jaccard: float = 0.75  # Jaccard co-occurrence (updated based on evaluation: P@10=0.0833, 3x better)
    functional: float = 0.0  # Functional tag similarity (not measured yet)
    text_embed: float = 0.10  # Text embeddings (card Oracle text)
    sideboard: float = 0.10  # Sideboard co-occurrence signal
    temporal: float = 0.05  # Temporal trend signal
    gnn: float = 0.10  # GNN-learned embeddings (PyTorch Geometric)
    archetype: float = 0.10  # Archetype staples and co-occurrence
    format: float = 0.10  # Format-specific and cross-format patterns

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
        """
        self.embeddings = embeddings
        self.adj = adj or {}
        self.tagger = tagger
        self.weights = (weights or FusionWeights()).normalized()
        self.text_embedder = text_embedder
        self.card_data = card_data or {}
        self.sideboard_cooccurrence = sideboard_cooccurrence or {}
        self.temporal_cooccurrence = temporal_cooccurrence or {}
        self.gnn_embedder = gnn_embedder
        self.archetype_staples = archetype_staples or {}
        self.archetype_cooccurrence = archetype_cooccurrence or {}
        self.format_cooccurrence = format_cooccurrence or {}
        self.cross_format_patterns = cross_format_patterns or {}
        self.aggregator = aggregator
        self.rrf_k = rrf_k
        self.mmr_lambda = mmr_lambda
        self.candidate_topn = candidate_topn

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

    def _get_temporal_similarity(self, query: str, candidate: str) -> float:
        """Get temporal co-occurrence similarity (weighted by recency)."""
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

        # From adjacency graph
        if self.adj and query in self.adj:
            candidates.update(self.adj[query])
            # Also include neighbors of neighbors (2-hop)
            for neighbor in self.adj[query]:
                if neighbor in self.adj:
                    candidates.update(self.adj[neighbor])

        # From embeddings
        if self.embeddings and query in self.embeddings:
            try:
                similar = self.embeddings.most_similar(query, topn=self.candidate_topn)
                candidates.update(card for card, _ in similar)
            except Exception:
                pass

        # Remove query itself
        candidates.discard(query)
        return candidates

    def _compute_similarity_scores(self, query: str, candidates: set[str]) -> dict[str, dict[str, float]]:
        """Compute similarity scores for all modalities."""
        scores = {c: {} for c in candidates}

        for candidate in candidates:
            if self.weights.embed > 0.0:
                scores[candidate]["embed"] = self._get_embedding_similarity(query, candidate)
            if self.weights.jaccard > 0.0:
                scores[candidate]["jaccard"] = self._get_jaccard_similarity(query, candidate)
            if self.weights.functional > 0.0:
                scores[candidate]["functional"] = self._get_functional_tag_similarity(query, candidate)
            if self.weights.text_embed > 0.0:
                scores[candidate]["text_embed"] = self._get_text_embedding_similarity(query, candidate)
            if self.weights.sideboard > 0.0:
                scores[candidate]["sideboard"] = self._get_sideboard_similarity(query, candidate)
            if self.weights.temporal > 0.0:
                scores[candidate]["temporal"] = self._get_temporal_similarity(query, candidate)
            if self.weights.gnn > 0.0:
                scores[candidate]["gnn"] = self._get_gnn_similarity(query, candidate)

        return scores

    def _aggregate_weighted(self, scores: dict[str, float]) -> float:
        """Weighted linear combination."""
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
        """Maximum of scores."""
        max_score = 0.0
        if self.weights.embed > 0.0 and "embed" in scores:
            max_score = max(max_score, scores["embed"])
        if self.weights.jaccard > 0.0 and "jaccard" in scores:
            max_score = max(max_score, scores["jaccard"])
        if self.weights.functional > 0.0 and "functional" in scores:
            max_score = max(max_score, scores["functional"])
        if self.weights.text_embed > 0.0 and "text_embed" in scores:
            max_score = max(max_score, scores["text_embed"])
        if self.weights.sideboard > 0.0 and "sideboard" in scores:
            max_score = max(max_score, scores["sideboard"])
        if self.weights.temporal > 0.0 and "temporal" in scores:
            max_score = max(max_score, scores["temporal"])
        if self.weights.gnn > 0.0 and "gnn" in scores:
            max_score = max(max_score, scores["gnn"])
        if self.weights.archetype > 0.0 and "archetype" in scores:
            max_score = max(max_score, scores["archetype"])
        if self.weights.format > 0.0 and "format" in scores:
            max_score = max(max_score, scores["format"])
        return max_score

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

    def similar(self, query: str, k: int = 10) -> list[tuple[str, float]]:
        """
        Find similar cards to query.

        Args:
            query: Card name to find similarities for
            k: Number of results to return

        Returns:
            List of (card_name, similarity_score) tuples, sorted by score descending
        """
        if query not in self.adj and (not self.embeddings or query not in self.embeddings):
            return []

        candidates = self._get_candidates(query)
        if not candidates:
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
            return self._apply_mmr(sorted_candidates, fused_scores, k)
        else:
            return [(c, fused_scores[c]) for c in sorted_candidates[:k]]

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

