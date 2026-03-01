#!/usr/bin/env python3
"""
Optimal Transport deck completion.

Formulates deck building as a discrete OT problem: transport mass from a
"current deck" distribution to a "target archetype" distribution over the
card pool, where the cost matrix encodes embedding distance, role gaps,
and mana-curve fit.

The Sinkhorn solver from the POT library produces a fractional transport
plan, which is then rounded to integer card counts respecting copy limits
and deck-size targets.

Requires: pip install pot  (or uv add pot)
"""

from __future__ import annotations

import logging
import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

logger = logging.getLogger("decksage.ot_completion")

try:
    import ot as pot  # type: ignore[import-not-found]
except ImportError:
    pot = None
    logger.warning("POT not installed. Install with: uv add pot")

# Re-use existing type aliases from deck_completion
from .deck_completion import (
    MAGIC_BASIC_LANDS,
    POKEMON_BASIC_ENERGY,
    CandidateFn,
    CMCFn,
    TagSetFn,
    _legal_add,
    _main_partition_name,
)


@dataclass
class OTCompletionConfig:
    """Configuration for OT-based deck completion."""

    game: Literal["magic", "yugioh", "pokemon"] = "magic"
    target_main_size: int = 60

    # Cost matrix weights (must sum to 1.0 for interpretability, but not enforced)
    embedding_weight: float = 0.5
    role_weight: float = 0.3
    curve_weight: float = 0.2

    # Sinkhorn parameters
    sinkhorn_reg: float = 0.05  # Entropic regularization (lower = sparser plan)
    sinkhorn_max_iter: int = 1000
    sinkhorn_tol: float = 1e-9

    # Rounding
    max_copies: int | None = None  # Override per-game default

    # Pool filtering
    pool_size: int = 200  # Max candidate pool size (top-k by embedding similarity)


@dataclass
class OTCompletionResult:
    """Result of OT-based deck completion."""

    deck: dict
    additions: list[dict[str, Any]]  # [{card, count, cost, reasoning}]
    transport_plan: np.ndarray | None = None
    cost_matrix: np.ndarray | None = None
    metrics: dict[str, Any] = field(default_factory=dict)


def deck_to_distribution(
    deck: dict,
    game: str,
    card_pool: list[str],
) -> np.ndarray:
    """
    Convert deck card counts to a probability distribution over the card pool.

    Returns a 1-D array of shape (len(card_pool),) that sums to 1.0.
    Cards not in the pool get zero mass.
    """
    pool_index = {name: i for i, name in enumerate(card_pool)}
    counts = np.zeros(len(card_pool), dtype=np.float64)

    part_name = _main_partition_name(game)
    for p in deck.get("partitions", []) or []:
        if p.get("name") != part_name:
            continue
        for card in p.get("cards", []) or []:
            name = card.get("name", "")
            count = int(card.get("count", 0))
            if name in pool_index:
                counts[pool_index[name]] += count

    total = counts.sum()
    if total == 0:
        # Uniform over pool if deck is empty
        return np.ones(len(card_pool), dtype=np.float64) / len(card_pool)
    return counts / total


def compute_reference_distribution(
    seed_cards: list[str],
    embeddings: Any,  # gensim KeyedVectors
    card_pool: list[str],
    temperature: float = 0.1,
) -> np.ndarray:
    """
    Build a target distribution from seed card embeddings.

    For each card in the pool, compute average cosine similarity to seed cards,
    then apply softmax with temperature to get a distribution. Lower temperature
    concentrates mass on the most similar cards.

    Args:
        seed_cards: Cards currently in deck (seeds for the target)
        embeddings: KeyedVectors with card embeddings
        card_pool: Full candidate pool
        temperature: Softmax temperature (lower = sharper)

    Returns:
        1-D array of shape (len(card_pool),) summing to 1.0
    """
    if not seed_cards or embeddings is None:
        return np.ones(len(card_pool), dtype=np.float64) / len(card_pool)

    # Get seed vectors (skip missing)
    seed_vecs = []
    for s in seed_cards:
        if s in embeddings:
            seed_vecs.append(embeddings[s])
    if not seed_vecs:
        return np.ones(len(card_pool), dtype=np.float64) / len(card_pool)

    seed_matrix = np.array(seed_vecs, dtype=np.float64)
    seed_norms = np.linalg.norm(seed_matrix, axis=1, keepdims=True)
    seed_norms[seed_norms == 0] = 1.0
    seed_matrix = seed_matrix / seed_norms

    # Compute average similarity for each pool card
    scores = np.zeros(len(card_pool), dtype=np.float64)
    for i, name in enumerate(card_pool):
        if name in embeddings:
            vec = embeddings[name].astype(np.float64)
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            sims = seed_matrix @ vec  # cosine similarities
            scores[i] = float(np.mean(sims))

    # Softmax with temperature
    scores = scores / max(temperature, 1e-8)
    scores -= scores.max()  # numerical stability
    exp_scores = np.exp(scores)
    dist = exp_scores / exp_scores.sum()
    return dist


def build_cost_matrix(
    card_pool: list[str],
    embeddings: Any,  # gensim KeyedVectors
    seed_cards: list[str],
    *,
    tag_set_fn: TagSetFn | None = None,
    cmc_fn: CMCFn | None = None,
    role_gaps: dict[str, int] | None = None,
    curve_target: dict[int, float] | None = None,
    embedding_weight: float = 0.5,
    role_weight: float = 0.3,
    curve_weight: float = 0.2,
) -> np.ndarray:
    """
    Build the cost matrix C[i, j] for transporting from source card i to target card j.

    The cost combines:
    1. Embedding distance (1 - cosine similarity) between cards
    2. Role penalty: higher cost for cards that don't fill identified role gaps
    3. Curve penalty: higher cost for cards whose CMC deviates from target curve

    For deck completion, we use a simplified form: C[i] is the cost of adding
    card i to the deck (1-D cost vector, not a full matrix), since we're
    transporting from a "deficit" source to the card pool.

    Returns:
        2-D array of shape (len(card_pool), len(card_pool)) for full OT, or
        1-D array of shape (len(card_pool),) for simplified marginal cost.
    """
    n = len(card_pool)
    costs = np.ones(n, dtype=np.float64)  # Default high cost

    # 1. Embedding distance component
    if embeddings is not None and seed_cards:
        seed_vecs = []
        for s in seed_cards:
            if s in embeddings:
                seed_vecs.append(embeddings[s])
        if seed_vecs:
            seed_matrix = np.array(seed_vecs, dtype=np.float64)
            seed_norms = np.linalg.norm(seed_matrix, axis=1, keepdims=True)
            seed_norms[seed_norms == 0] = 1.0
            seed_matrix = seed_matrix / seed_norms

            emb_costs = np.ones(n, dtype=np.float64)
            for i, name in enumerate(card_pool):
                if name in embeddings:
                    vec = embeddings[name].astype(np.float64)
                    norm = np.linalg.norm(vec)
                    if norm > 0:
                        vec = vec / norm
                    sims = seed_matrix @ vec
                    emb_costs[i] = 1.0 - float(np.mean(sims))
            costs = embedding_weight * emb_costs

    # 2. Role penalty component
    if tag_set_fn is not None and role_gaps:
        role_costs = np.ones(n, dtype=np.float64) * 0.5  # Neutral baseline
        total_gap = sum(role_gaps.values()) or 1
        for i, name in enumerate(card_pool):
            tags = tag_set_fn(name)
            bonus = 0.0
            for role, gap in role_gaps.items():
                if role in tags:
                    bonus += gap / total_gap
            # Lower cost for cards that fill gaps
            role_costs[i] = max(0.0, 0.5 - bonus)
        costs += role_weight * role_costs

    # 3. Curve penalty component
    if cmc_fn is not None and curve_target:
        curve_costs = np.ones(n, dtype=np.float64) * 0.5
        for i, name in enumerate(card_pool):
            cmc = cmc_fn(name)
            if cmc is not None:
                # How much does this CMC slot need filling?
                target_prop = curve_target.get(cmc, 0.0)
                # Higher target proportion = lower cost
                curve_costs[i] = max(0.0, 0.5 - float(target_prop))
        costs += curve_weight * curve_costs

    return costs


def _round_transport_plan(
    plan_marginal: np.ndarray,
    card_pool: list[str],
    deck: dict,
    game: str,
    slots_to_fill: int,
    max_copies: int | None = None,
) -> list[tuple[str, int]]:
    """
    Round fractional OT plan to integer card counts.

    Uses greedy rounding: sort by fractional mass, greedily assign copies
    while respecting copy limits and total slot count.

    Args:
        plan_marginal: 1-D array of fractional card masses from OT solution
        card_pool: List of card names corresponding to plan indices
        deck: Current deck (for copy limit checking)
        game: Game name
        slots_to_fill: Number of card slots to add
        max_copies: Override per-game copy limit

    Returns:
        List of (card_name, count) tuples
    """
    if max_copies is None:
        if game == "yugioh":
            max_copies = 3
        else:
            max_copies = 4

    # Sort by descending mass
    indices = np.argsort(-plan_marginal)
    additions: list[tuple[str, int]] = []
    remaining = slots_to_fill

    for idx in indices:
        if remaining <= 0:
            break
        name = card_pool[idx]
        mass = float(plan_marginal[idx])
        if mass < 1e-8:
            break

        # How many copies does the OT plan suggest?
        suggested = max(1, round(mass * slots_to_fill))
        # Clamp to remaining slots and copy limit
        count = min(suggested, remaining)

        # Check legality for each copy
        actual = 0
        for _ in range(count):
            if _legal_add(game, deck, name):
                actual += 1
                # Temporarily add to deck for subsequent legality checks
                part_name = _main_partition_name(game)
                added = False
                for p in deck.get("partitions", []) or []:
                    if p.get("name") == part_name:
                        for c in p.get("cards", []) or []:
                            if c.get("name") == name:
                                c["count"] = c.get("count", 0) + 1
                                added = True
                                break
                        if not added:
                            p.setdefault("cards", []).append({"name": name, "count": 1})
                            added = True
                        break

        if actual > 0:
            additions.append((name, actual))
            remaining -= actual

    return additions


def ot_complete_deck(
    game: str,
    deck: dict,
    embeddings: Any,  # gensim KeyedVectors
    cfg: OTCompletionConfig | None = None,
    *,
    candidate_fn: CandidateFn | None = None,
    tag_set_fn: TagSetFn | None = None,
    cmc_fn: CMCFn | None = None,
    role_gaps: dict[str, int] | None = None,
    curve_target: dict[int, float] | None = None,
) -> OTCompletionResult:
    """
    Complete a deck using optimal transport.

    1. Build candidate pool from seed cards via embeddings
    2. Construct source distribution (current deck) and target distribution
    3. Build cost matrix (embedding + role + curve)
    4. Solve OT with Sinkhorn
    5. Round fractional plan to integer counts
    6. Apply additions to deck

    Args:
        game: Game name
        deck: Current deck dict (partitions format)
        embeddings: KeyedVectors with card embeddings
        cfg: OT completion config
        candidate_fn: Optional function to get candidates (used for pool building)
        tag_set_fn: Function to get functional tags for a card
        cmc_fn: Function to get CMC for a card
        role_gaps: Dict of role -> gap_count for role-aware costs
        curve_target: Target CMC distribution {cmc: proportion}

    Returns:
        OTCompletionResult with completed deck and metadata
    """
    if pot is None:
        raise ImportError("POT library required for OT completion. Install with: uv add pot")

    cfg = cfg or OTCompletionConfig(game=game)
    import copy

    deck = copy.deepcopy(deck)

    part_name = _main_partition_name(game)
    # Ensure partition exists
    found = False
    for p in deck.get("partitions", []) or []:
        if p.get("name") == part_name:
            found = True
            break
    if not found:
        deck.setdefault("partitions", []).append({"name": part_name, "cards": []})

    # Current deck cards
    seed_cards: list[str] = []
    current_size = 0
    for p in deck.get("partitions", []) or []:
        if p.get("name") == part_name:
            for c in p.get("cards", []) or []:
                name = c.get("name", "")
                count = int(c.get("count", 0))
                if name:
                    seed_cards.append(name)
                    current_size += count

    slots_to_fill = max(0, cfg.target_main_size - current_size)
    if slots_to_fill == 0:
        return OTCompletionResult(
            deck=deck,
            additions=[],
            metrics={"slots_to_fill": 0, "current_size": current_size},
        )

    # Build candidate pool
    card_pool = _build_candidate_pool(
        seed_cards=seed_cards,
        embeddings=embeddings,
        candidate_fn=candidate_fn,
        pool_size=cfg.pool_size,
        exclude=set(seed_cards),
    )

    if not card_pool:
        logger.warning("Empty candidate pool, cannot complete deck via OT")
        return OTCompletionResult(
            deck=deck,
            additions=[],
            metrics={"error": "empty_candidate_pool"},
        )

    n = len(card_pool)

    # Source distribution: uniform over "deficit" (we want to fill slots_to_fill)
    # Target distribution: similarity-weighted over candidate pool
    source = np.ones(n, dtype=np.float64) / n
    target = compute_reference_distribution(
        seed_cards=seed_cards,
        embeddings=embeddings,
        card_pool=card_pool,
        temperature=0.1,
    )

    # Cost vector for each candidate
    cost_vec = build_cost_matrix(
        card_pool=card_pool,
        embeddings=embeddings,
        seed_cards=seed_cards,
        tag_set_fn=tag_set_fn,
        cmc_fn=cmc_fn,
        role_gaps=role_gaps,
        curve_target=curve_target,
        embedding_weight=cfg.embedding_weight,
        role_weight=cfg.role_weight,
        curve_weight=cfg.curve_weight,
    )

    # For 1-D OT (Earth Mover's Distance variant), we use the cost vector
    # as a diagonal cost matrix: C[i,j] = cost_vec[i] if i==j, else high cost.
    # But more naturally, we solve: minimize sum_j plan[j] * cost[j]
    # subject to: sum_j plan[j] = 1, plan[j] >= 0
    # This is just argmin(cost), which is trivial.
    #
    # Instead, use full OT between source and target with cost matrix derived
    # from pairwise embedding distances in the pool.
    cost_matrix = _build_pairwise_cost_matrix(
        card_pool=card_pool,
        embeddings=embeddings,
        cost_vec=cost_vec,
    )

    # Solve OT with Sinkhorn
    try:
        transport_plan = pot.sinkhorn(
            source,
            target,
            cost_matrix,
            reg=cfg.sinkhorn_reg,
            numItermax=cfg.sinkhorn_max_iter,
            stopThr=cfg.sinkhorn_tol,
            warn=False,
        )
    except Exception as e:
        logger.error(f"Sinkhorn solver failed: {e}")
        return OTCompletionResult(
            deck=deck,
            additions=[],
            metrics={"error": f"sinkhorn_failed: {e}"},
        )

    # Extract target marginal (how much mass each target card receives)
    target_marginal = transport_plan.sum(axis=0)

    # Round to integer counts
    additions = _round_transport_plan(
        plan_marginal=target_marginal,
        card_pool=card_pool,
        deck=deck,
        game=game,
        slots_to_fill=slots_to_fill,
        max_copies=cfg.max_copies,
    )

    # Build addition records with reasoning
    addition_records: list[dict[str, Any]] = []
    for card_name, count in additions:
        idx = card_pool.index(card_name)
        record: dict[str, Any] = {
            "card": card_name,
            "count": count,
            "ot_mass": float(target_marginal[idx]),
            "cost": float(cost_vec[idx]),
        }
        # Add role info if available
        if tag_set_fn:
            tags = tag_set_fn(card_name)
            filled_roles = []
            if role_gaps:
                filled_roles = [r for r in role_gaps if r in tags]
            record["reasoning"] = (
                f"Fills roles: {', '.join(filled_roles)}" if filled_roles else "Embedding similarity"
            )
        else:
            record["reasoning"] = "Embedding similarity"
        addition_records.append(record)

    # Compute OT distance (Wasserstein approximation)
    ot_distance = float(np.sum(transport_plan * cost_matrix))

    return OTCompletionResult(
        deck=deck,
        additions=addition_records,
        transport_plan=transport_plan,
        cost_matrix=cost_matrix,
        metrics={
            "slots_to_fill": slots_to_fill,
            "current_size": current_size,
            "pool_size": n,
            "cards_added": sum(c for _, c in additions),
            "ot_distance": ot_distance,
            "sinkhorn_reg": cfg.sinkhorn_reg,
        },
    )


def _build_candidate_pool(
    seed_cards: list[str],
    embeddings: Any,
    candidate_fn: CandidateFn | None,
    pool_size: int,
    exclude: set[str],
) -> list[str]:
    """
    Build candidate card pool from seed cards.

    Uses candidate_fn if available, otherwise falls back to embedding
    most_similar().
    """
    candidates: dict[str, float] = {}

    if candidate_fn is not None:
        for seed in seed_cards[:10]:  # Limit seeds to avoid explosion
            for name, score in candidate_fn(seed, pool_size // 5):
                if name not in exclude:
                    candidates[name] = max(candidates.get(name, 0.0), score)
    elif embeddings is not None:
        for seed in seed_cards[:10]:
            if seed in embeddings:
                try:
                    for name, score in embeddings.most_similar(seed, topn=pool_size // 5):
                        if name not in exclude:
                            candidates[name] = max(candidates.get(name, 0.0), score)
                except KeyError:
                    continue

    # Sort by score and take top pool_size
    sorted_cands = sorted(candidates.items(), key=lambda x: x[1], reverse=True)
    return [name for name, _ in sorted_cands[:pool_size]]


def _build_pairwise_cost_matrix(
    card_pool: list[str],
    embeddings: Any,
    cost_vec: np.ndarray,
) -> np.ndarray:
    """
    Build pairwise cost matrix for OT.

    Uses embedding cosine distance as base, modulated by the per-card cost vector.
    C[i,j] = 0.5 * emb_dist(i,j) + 0.25 * cost_vec[i] + 0.25 * cost_vec[j]
    """
    n = len(card_pool)

    # Start with cost_vec contribution (additive: source cost + target cost)
    cost_i = cost_vec.reshape(-1, 1)  # (n, 1)
    cost_j = cost_vec.reshape(1, -1)  # (1, n)

    if embeddings is None:
        # No embeddings: just use cost vectors
        return 0.5 * cost_i + 0.5 * cost_j

    # Build embedding matrix
    vecs = np.zeros((n, embeddings.vector_size), dtype=np.float64)
    has_vec = np.zeros(n, dtype=bool)
    for i, name in enumerate(card_pool):
        if name in embeddings:
            vecs[i] = embeddings[name]
            has_vec[i] = True

    # Normalize
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    vecs = vecs / norms

    # Cosine distance matrix
    sim_matrix = vecs @ vecs.T
    dist_matrix = 1.0 - sim_matrix
    np.clip(dist_matrix, 0.0, 2.0, out=dist_matrix)

    # Combine: embedding distance + per-card costs
    cost_matrix = 0.5 * dist_matrix + 0.25 * cost_i + 0.25 * cost_j

    # Ensure non-negative (required by Sinkhorn)
    np.clip(cost_matrix, 0.0, None, out=cost_matrix)

    return cost_matrix


__all__ = [
    "OTCompletionConfig",
    "OTCompletionResult",
    "build_cost_matrix",
    "compute_reference_distribution",
    "deck_to_distribution",
    "ot_complete_deck",
]
