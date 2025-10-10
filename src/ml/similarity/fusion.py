#!/usr/bin/env python3
"""
Weighted late-fusion similarity for card retrieval.

Principles:
- Keep it simple and interpretable (avoid premature abstraction)
- Use available signals; degrade gracefully when some are missing
- Limit candidate universe for performance; avoid full corpus scans

Signals supported:
- Embedding cosine similarity (Node2Vec via gensim KeyedVectors)
- Co-occurrence Jaccard similarity (adjacency built from pairs)
- Functional tag similarity (Jaccard over boolean tag sets)

Semantic and vision signals can be added later as optional scorers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Tuple
import math

try:
    from gensim.models import KeyedVectors  # type: ignore

    HAS_GENSIM = True
except Exception:  # pragma: no cover
    KeyedVectors = object  # type: ignore
    HAS_GENSIM = False

# Local import (absolute to support both package and top-level test imports)
from .similarity_methods import jaccard_similarity as sm_jaccard


# ------------------------------
# Utilities
# ------------------------------

def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _cosine_to_unit(sim: float) -> float:
    """Map cosine similarity [-1, 1] to [0, 1]."""
    # Guard against floating rounding near boundaries (match test isclose behavior)
    if sim <= -1.0 or math.isclose(sim, -1.0, rel_tol=1e-9):
        return 0.0
    if sim >= 1.0 or math.isclose(sim, 1.0, rel_tol=1e-9):
        return 1.0
    return _clamp01(0.5 * (sim + 1.0))


def _to_dict(pairs: Iterable[Tuple[str, float]]) -> Dict[str, float]:
    return {c: float(s) for c, s in pairs}


def _tag_set_from_dataclass(dc) -> set[str]:
    """Extract set of tag names with Truthy values, excluding 'card_name' and non-bool fields."""
    if dc is None:
        return set()
    tag_set: set[str] = set()
    for field_name, value in dc.__dict__.items():
        if field_name == "card_name":
            continue
        if isinstance(value, bool) and value:
            tag_set.add(field_name)
    return tag_set


def _jaccard_sets(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return float(inter) / float(union) if union else 0.0


# ------------------------------
# Fusion Engine
# ------------------------------

@dataclass
class FusionWeights:
    embed: float = 0.40
    jaccard: float = 0.35
    functional: float = 0.25

    def normalized(self) -> "FusionWeights":
        total = self.embed + self.jaccard + self.functional
        if total <= 0.0:
            # Avoid division by zero; default to equal weights
            return FusionWeights(embed=1 / 3, jaccard=1 / 3, functional=1 / 3)
        return FusionWeights(
            embed=self.embed / total,
            jaccard=self.jaccard / total,
            functional=self.functional / total,
        )


class WeightedLateFusion:
    """
    Combine multiple similarity signals for a query.

    - embeddings: gensim KeyedVectors or None
    - adj: adjacency dict for co-occurrence graph (card -> set of neighbors) or None
    - tagger: object with method tag_card(name|data) returning dataclass of booleans (optional)
    - weights: FusionWeights; will be normalized internally
    - candidate_topn: how many candidates to gather from each base method
    """

    def __init__(
        self,
        embeddings: Optional["KeyedVectors"],
        adj: Optional[Dict[str, set]],
        tagger: Optional[object] = None,
        weights: Optional[FusionWeights] = None,
        candidate_topn: int = 200,
        *,
        aggregator: str = "weighted",
        rrf_k: int = 60,
        mmr_lambda: float = 0.0,
    ) -> None:
        self.embeddings = embeddings if HAS_GENSIM else None
        self.adj = adj
        self.tagger = tagger
        self.weights = (weights or FusionWeights()).normalized()
        self.candidate_topn = max(10, int(candidate_topn))
        self.aggregator = (aggregator or "weighted").lower().strip()
        self.rrf_k = max(1, int(rrf_k))
        # MMR diversification parameter in [0,1]; 0 disables diversification
        self.mmr_lambda = 0.0 if mmr_lambda <= 0 else (1.0 if mmr_lambda > 1.0 else float(mmr_lambda))

    # --------------------------
    # Public API
    # --------------------------
    def similar(self, query: str, k: int = 10) -> List[Tuple[str, float]]:
        candidates = self._gather_candidates(query)
        if not candidates:
            return []

        # Scores per modality
        embed_scores = self._score_embeddings(query, candidates)
        jac_scores = self._score_jaccard(query, candidates)
        func_scores = self._score_functional(query, candidates)

        # Simple query-adaptive reliability scaling: down-weight jaccard when degree is tiny
        if jac_scores is not None and self.adj is not None and query in self.adj:
            try:
                deg = len(self.adj.get(query, set()))
                if deg <= 1:
                    # Low degree: reduce impact of co-occurrence signal
                    jac_scores = {c: s * 0.5 for c, s in jac_scores.items()}
            except Exception:
                pass

        combined = self._combine_scores(candidates, embed_scores, jac_scores, func_scores)
        combined.sort(key=lambda x: x[1], reverse=True)
        # Optional diversity re-ranking (MMR)
        if self.mmr_lambda > 0.0 and combined:
            combined = self._mmr_rerank(combined, k)
            return combined[:k]
        return combined[:k]

    def similar_multi(self, queries: List[str], k: int = 10) -> List[Tuple[str, float]]:
        """
        Fuse results across multiple related queries using RRF across per-query rankings.
        """
        rankings: List[List[str]] = []
        for q in queries:
            try:
                r = self.similar(q, k=min(self.candidate_topn, max(k, 10)))
                rankings.append([c for c, _ in r])
            except Exception:
                continue
        if not rankings:
            return []
        # RRF across per-query rankings
        scores: Dict[str, float] = {}
        k0 = self.rrf_k
        for rank_list in rankings:
            pos = {c: i + 1 for i, c in enumerate(rank_list)}
            for c, rnk in pos.items():
                scores[c] = scores.get(c, 0.0) + 1.0 / float(k0 + rnk)
        items = list(scores.items())
        items.sort(key=lambda x: x[1], reverse=True)
        if self.mmr_lambda > 0.0:
            items = self._mmr_rerank(items, k)
        return items[:k]

    # --------------------------
    # Aggregation helpers
    # --------------------------
    def _combine_scores(
        self,
        candidates: Iterable[str],
        embed_scores: Optional[Dict[str, float]],
        jac_scores: Optional[Dict[str, float]],
        func_scores: Optional[Dict[str, float]],
    ) -> List[Tuple[str, float]]:
        # Optional per-modality normalization to comparable scales
        def normalize(d: Optional[Dict[str, float]]) -> Optional[Dict[str, float]]:
            if d is None:
                return None
            if not d:
                return d
            m = max(d.values())
            if m <= 0.0:
                return d
            return {k: (v / m) for k, v in d.items()}

        embed_scores = normalize(embed_scores)
        jac_scores = normalize(jac_scores)

        active = {
            "embed": embed_scores is not None,
            "jaccard": jac_scores is not None,
            "functional": func_scores is not None,
        }

        # Adaptive normalization over available modalities
        w_map = {"embed": self.weights.embed, "jaccard": self.weights.jaccard, "functional": self.weights.functional}
        total_w = sum(w for k_, w in w_map.items() if active[k_])
        if total_w <= 0:
            # Fall back to equal weights over active modalities
            num_active = sum(1 for v in active.values() if v)
            if num_active == 0:
                return []
            for k_ in w_map.keys():
                w_map[k_] = (1.0 / num_active) if active[k_] else 0.0
        else:
            for k_ in w_map.keys():
                w_map[k_] = (w_map[k_] / total_w) if active[k_] else 0.0

        agg = self.aggregator

        if agg in {"weighted", "sum", "combsum", "comb-sum"}:
            combined: List[Tuple[str, float]] = []
            for card in candidates:
                s = 0.0
                if active["embed"]:
                    s += w_map["embed"] * embed_scores.get(card, 0.0)  # type: ignore[arg-type]
                if active["jaccard"]:
                    s += w_map["jaccard"] * jac_scores.get(card, 0.0)  # type: ignore[arg-type]
                if active["functional"]:
                    s += w_map["functional"] * func_scores.get(card, 0.0)  # type: ignore[arg-type]
                combined.append((card, float(s)))
            return combined

        if agg in {"combmnz", "comb-mnz"}:
            combined = []
            for card in candidates:
                s_e = (embed_scores or {}).get(card, 0.0)
                s_j = (jac_scores or {}).get(card, 0.0)
                s_f = (func_scores or {}).get(card, 0.0)
                s_sum = w_map["embed"] * s_e + w_map["jaccard"] * s_j + w_map["functional"] * s_f
                nz = int(s_e > 0) + int(s_j > 0) + int(s_f > 0)
                combined.append((card, float(s_sum * max(1, nz))))
            return combined

        if agg == "rrf":
            # Build ranks per modality
            ranks: List[Dict[str, int]] = []
            for scores in (embed_scores, jac_scores, func_scores):
                if scores is None:
                    continue
                order = sorted(scores.items(), key=lambda x: x[1], reverse=True)
                ranks.append({c: i + 1 for i, (c, _) in enumerate(order)})
            k0 = self.rrf_k
            rrf_scores: Dict[str, float] = {}
            for card in candidates:
                s = 0.0
                for rnk in ranks:
                    pos = rnk.get(card)
                    if pos is not None:
                        s += 1.0 / float(k0 + pos)
                rrf_scores[card] = s
            return list(rrf_scores.items())

        # Default fallback (weighted)
        combined = []
        for card in candidates:
            s = 0.0
            if active["embed"]:
                s += w_map["embed"] * embed_scores.get(card, 0.0)  # type: ignore[arg-type]
            if active["jaccard"]:
                s += w_map["jaccard"] * jac_scores.get(card, 0.0)  # type: ignore[arg-type]
            if active["functional"]:
                s += w_map["functional"] * func_scores.get(card, 0.0)  # type: ignore[arg-type]
            combined.append((card, float(s)))
        return combined

    def _mmr_rerank(self, items: List[Tuple[str, float]], k: int) -> List[Tuple[str, float]]:
        selected: List[Tuple[str, float]] = []
        remaining: Dict[str, float] = {c: s for c, s in items}
        lam = self.mmr_lambda

        def pair_sim(a: str, b: str) -> float:
            if self.embeddings is None:
                return 0.0
            try:
                sim = float(self.embeddings.similarity(a, b))  # type: ignore[attr-defined]
                return _cosine_to_unit(sim)
            except Exception:
                return 0.0

        while remaining and len(selected) < k:
            best_c: Optional[str] = None
            best_score = -1e9
            for c, rel in remaining.items():
                if not selected:
                    mmr_score = rel
                else:
                    max_sim = max(pair_sim(c, s_c) for s_c, _ in selected)
                    mmr_score = lam * rel - (1.0 - lam) * max_sim
                if mmr_score > best_score:
                    best_score = mmr_score
                    best_c = c
            assert best_c is not None
            selected.append((best_c, remaining.pop(best_c)))

        return selected + [(c, s) for c, s in items if c not in {x for x, _ in selected}]

    # --------------------------
    # Candidate gathering
    # --------------------------
    def _gather_candidates(self, query: str) -> List[str]:
        cand: set[str] = set()

        # Embedding neighbors
        if self.embeddings is not None and query in self.embeddings:
            try:
                neighbors = self.embeddings.most_similar(query, topn=self.candidate_topn)
                cand.update([c for c, _ in neighbors])
            except Exception:
                pass

        # Jaccard neighbors
        if self.adj is not None and query in self.adj:
            try:
                neighbors_j = sm_jaccard(query, self.adj, top_k=self.candidate_topn, filter_lands=True)
                cand.update([c for c, _ in neighbors_j])
            except Exception:
                pass

        # If neither provided candidates, but query exists in embeddings, fall back to emb topK
        if not cand and self.embeddings is not None and query in getattr(self.embeddings, "index_to_key", []):
            try:
                neighbors = self.embeddings.most_similar(query, topn=50)
                cand.update([c for c, _ in neighbors])
            except Exception:
                pass

        return list(cand)

    # --------------------------
    # Scorers
    # --------------------------
    def _score_embeddings(self, query: str, candidates: Iterable[str]) -> Optional[Dict[str, float]]:
        if self.embeddings is None or query not in getattr(self.embeddings, "index_to_key", []):
            return None
        scores: Dict[str, float] = {}
        for c in candidates:
            if c in self.embeddings:
                try:
                    sim = float(self.embeddings.similarity(query, c))
                    scores[c] = _cosine_to_unit(sim)
                except Exception:
                    continue
        return scores

    def _score_jaccard(self, query: str, candidates: Iterable[str]) -> Optional[Dict[str, float]]:
        if self.adj is None or query not in self.adj:
            return None
        # Get a trimmed ranking first to avoid full scan
        top_pairs = sm_jaccard(query, self.adj, top_k=self.candidate_topn, filter_lands=True)
        base = _to_dict(top_pairs)
        # Ensure all candidates have a value
        return {c: base.get(c, 0.0) for c in candidates}

    def _score_functional(self, query: str, candidates: Iterable[str]) -> Optional[Dict[str, float]]:
        if self.tagger is None:
            return None
        # Tag query
        try:
            # MTG tagger expects a name; Pokemon/YGO taggers expect a dict
            query_tags_dc = None
            try:
                query_tags_dc = self.tagger.tag_card(query)  # type: ignore[attr-defined]
            except TypeError:
                query_tags_dc = None  # Unsupported tagger signature

            if query_tags_dc is None:
                return None

            query_tag_set = _tag_set_from_dataclass(query_tags_dc)
        except Exception:
            return None

        scores: Dict[str, float] = {}
        for c in candidates:
            try:
                cand_tags_dc = self.tagger.tag_card(c)  # type: ignore[attr-defined]
                cand_set = _tag_set_from_dataclass(cand_tags_dc)
                scores[c] = _jaccard_sets(query_tag_set, cand_set)
            except Exception:
                # Best-effort; continue
                continue
        return scores


__all__ = [
    "FusionWeights",
    "WeightedLateFusion",
]


