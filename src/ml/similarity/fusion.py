#!/usr/bin/env python3
"""
Weighted Late Fusion for Multi-Modal Card Similarity

Combines multiple similarity signals:
1. Embedding similarity (cosine similarity in embedding space)
2. Jaccard similarity (co-occurrence graph)
3. Functional tag similarity (Jaccard on functional tags)
4. Text embedding similarity (instruction-tuned embeddings)
5. Visual embedding similarity (SigLIP/CLIP on card images)

Supports multiple aggregation methods:
- rrf: Reciprocal Rank Fusion (default, recommended for heterogeneous signals)
- isr: Inverse Square Root (slower rank decay, gives more weight to lower ranks)
- weighted: Linear combination of normalized scores (requires weight tuning)
- combsum: Sum of scores
- combmnz: Sum of scores x overlap count (rewards agreement between modalities)
- combmax: Maximum of scores
- combmin: Minimum of scores

Also supports MMR (Maximal Marginal Relevance) for result diversification.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, fields
from typing import Any, ClassVar


logger = logging.getLogger(__name__)

# Canonical ordered list of signal names, matching FusionWeights field order.
_SIGNAL_NAMES: tuple[str, ...] = (
    "embed",
    "jaccard",
    "functional",
    "text_embed",
    "visual_embed",
    "archetype",
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

    Default weights:
    - Instruction-tuned: 30% (zero-shot, semantic understanding)
    - Co-occurrence: 25% (established patterns, Node2Vec/PecanPy)
    - Visual: 20% (visual similarity from card images)
    - Jaccard: 15% (direct co-occurrence)
    - Functional: 10% (role-based similarity)
    - Archetype: 0% (optional, archetype-aware co-occurrence)
    """

    embed: float = 0.25  # Co-occurrence embeddings (Node2Vec/PecanPy)
    jaccard: float = 0.15  # Direct co-occurrence (Jaccard similarity)
    functional: float = 0.10  # Functional tag similarity (role-based)
    text_embed: float = 0.30  # Instruction-tuned embeddings (zero-shot, semantic)
    visual_embed: float = 0.20  # Visual embeddings (card images, CLIP/SigLIP)
    archetype: float = 0.0  # Archetype staples and co-occurrence (optional)

    def to_dict(self) -> dict[str, float]:
        """Return weights as a dict keyed by signal name."""
        return {f.name: getattr(self, f.name) for f in fields(self)}

    def normalized(self) -> FusionWeights:
        """Return normalized weights that sum to 1.0."""
        d = self.to_dict()
        total = sum(d.values())
        if total <= 0.0:
            return FusionWeights(
                embed=0.25,
                jaccard=0.15,
                functional=0.15,
                text_embed=0.25,
                visual_embed=0.10,
                archetype=0.10,
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
    _SIGNAL_COMPUTERS: ClassVar[dict[str, str | None]] = {
        "embed": "_get_embedding_similarity",
        "jaccard": None,
        "functional": "_get_functional_tag_similarity",
        "text_embed": "_get_text_embedding_similarity",
        "visual_embed": "_get_visual_embedding_similarity",
        "archetype": "_get_archetype_similarity",
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
        archetype_staples: dict[str, dict[str, float]] | None = None,
        archetype_cooccurrence: dict[str, dict[str, float]] | None = None,
        task_type: str | None = None,
        adaptive_visual_weights: bool = True,  # Adjust visual weights based on coverage
        graph_weights: dict | None = None,  # Edge weights for candidate capping
        game: str | None = None,  # Game name for loading text index
        # Legacy kwargs accepted but ignored (callers may still pass them).
        **_kwargs: Any,
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
            archetype_staples: Optional dict mapping card -> archetype -> frequency
            archetype_cooccurrence: Optional dict mapping card -> co-occurring card -> frequency (within archetypes)
            task_type: Optional task type for instruction-tuned embeddings (e.g., "substitution", "completion", "synergy")
        """
        # Apply task-specific weights if task_type provided
        base_weights = weights or FusionWeights()
        if task_type:
            try:
                from .fusion_improvements import create_task_specific_weights

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
        self.archetype_staples = archetype_staples or {}
        self.archetype_cooccurrence = archetype_cooccurrence or {}
        self._weights_cache = graph_weights or {}
        self.aggregator = aggregator
        self.adaptive_visual_weights = adaptive_visual_weights

        # Adjust weights based on visual coverage if adaptive mode enabled
        if adaptive_visual_weights and visual_embedder and weights and weights.visual_embed > 0.0:
            try:
                from .visual_coverage import (
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

        # Text embedding index for candidate generation (breaks co-occurrence echo chamber)
        # Load precomputed numpy index from data/cache/text_embeddings/
        self._text_index_matrix = None  # [N, D] L2-normalized
        self._text_index_names: list[str] = []
        self._text_name_to_idx: dict[str, int] = {}
        self._game = game
        if game and (text_embedder is not None or (card_data and self.weights.text_embed > 0)):
            self._try_load_text_index(game)

        # Pre-compute the weights dict for use in aggregation hot path.
        self._weights_dict = self.weights.to_dict()

    def _try_load_text_index(self, game: str) -> None:
        """Load precomputed text embedding index if available."""
        data_dir = Path(__file__).resolve().parent.parent.parent.parent / "data"
        idx_path = data_dir / "cache" / "text_embeddings" / f"{game}_embeddings.npy"
        names_path = data_dir / "cache" / "text_embeddings" / f"{game}_names.txt"

        if not idx_path.exists():
            return

        try:
            import numpy as np

            self._text_index_matrix = np.load(str(idx_path))
            with open(names_path) as f:
                self._text_index_names = [line.strip() for line in f]
            self._text_name_to_idx = {n: i for i, n in enumerate(self._text_index_names)}
            logger.info(
                f"Loaded text embedding index: {len(self._text_index_names)} cards, "
                f"{self._text_index_matrix.shape[1]}D"
            )
        except Exception as e:
            logger.debug(f"Failed to load text index: {e}")

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
            from .tagger_utils import extract_tag_set

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
        self,
        query: str,
        candidate: str,
        task_type: str | None = None,
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

        # Text embedding candidates (from precomputed index, fast)
        if self._text_index_matrix is not None and query in self._text_name_to_idx:
            try:
                import numpy as np

                q_idx = self._text_name_to_idx[query]
                q_vec = self._text_index_matrix[q_idx : q_idx + 1]  # [1, D]
                sims = (q_vec @ self._text_index_matrix.T).flatten()  # [N]
                n_text_candidates = min(30, self.candidate_topn)
                top_indices = np.argpartition(-sims, n_text_candidates)[:n_text_candidates]
                for idx in top_indices:
                    candidates.add(self._text_index_names[idx])
            except Exception as e:
                logger.debug(f"Text index candidate retrieval failed: {e}")

        # Remove query itself
        candidates.discard(query)
        return candidates

    # ------------------------------------------------------------------
    # Similarity scoring
    # ------------------------------------------------------------------

    def _compute_similarity_scores(
        self,
        query: str,
        candidates: set[str],
        task_type: str | None = None,
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
                        query,
                        candidate,
                        task_type=task_type,
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
        return [(sig, wd[sig], data[sig]) for sig in _SIGNAL_NAMES if wd[sig] > 0.0 and sig in data]

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
                      If provided, temporarily switches weights AND text instruction for this call

        Returns:
            List of (card_name, similarity_score) tuples, sorted by score descending
        """
        effective_task_type = task_type or self.task_type

        # If task_type override differs from construction default, temporarily
        # switch to task-specific weights so that e.g. "substitution" zeroes out
        # co-occurrence signals even when the fusion was built for "synergy".
        # Only do this when the instance was constructed with a task_type
        # (self.task_type is not None), meaning task-aware switching was intended.
        # When self.task_type is None, the caller provided explicit weights
        # that should not be overridden.
        saved_weights_dict = None
        if task_type and self.task_type and task_type != self.task_type:
            try:
                from .fusion_improvements import create_task_specific_weights

                task_weights = create_task_specific_weights(task_type, FusionWeights()).normalized()
                saved_weights_dict = self._weights_dict
                self._weights_dict = task_weights.to_dict()
            except ImportError:
                pass

        if query not in self.adj and (not self.embeddings or query not in self.embeddings):
            if saved_weights_dict is not None:
                self._weights_dict = saved_weights_dict
            return []

        candidates = self._get_candidates(query)
        if not candidates:
            if saved_weights_dict is not None:
                self._weights_dict = saved_weights_dict
            return []

        # Compute similarity scores for all modalities
        modality_scores = self._compute_similarity_scores(
            query,
            candidates,
            task_type=effective_task_type,
        )

        # Aggregate scores based on method
        if self.aggregator in ("rrf", "isr"):
            # For rank-based aggregators, convert scores to ranks per modality.
            # Collect all active signal names present in scores.
            active_sigs = [sig for sig in _SIGNAL_NAMES if self._weights_dict[sig] > 0.0]

            # Build per-signal ranked lists and convert to rank dicts.
            per_signal_ranked: dict[str, list[tuple[str, float]]] = {sig: [] for sig in active_sigs}
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
                cand: self._aggregate(ranks.get(cand, {}), self.aggregator) for cand in candidates
            }

        else:
            # Score-based aggregators use modality_scores directly.
            fused_scores = {
                cand: self._aggregate(modality_scores[cand], self.aggregator) for cand in candidates
            }

        # Sort by score
        sorted_candidates = sorted(candidates, key=lambda c: fused_scores.get(c, 0.0), reverse=True)

        # Apply MMR if needed
        if self.mmr_lambda > 0.0:
            results = self._apply_mmr(sorted_candidates, fused_scores, k)
        else:
            results = [(c, fused_scores[c]) for c in sorted_candidates[:k]]

        # Restore original weights if they were temporarily overridden
        if saved_weights_dict is not None:
            self._weights_dict = saved_weights_dict

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
