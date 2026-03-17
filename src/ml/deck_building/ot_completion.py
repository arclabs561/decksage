#!/usr/bin/env python3
"""
Optimal Transport deck completion.

Formulates deck building as a discrete OT problem: transport mass from a
quality-weighted source distribution over the candidate pool to a target
archetype distribution, where the cost matrix encodes embedding distance,
role gaps, and mana-curve fit.

Key design choices (v2, 2026-03-17):

1. **Quality-weighted source**: candidates with higher affinity to the seed
   deck receive more source mass, replacing the prior uniform distribution
   that treated all candidates equally.

2. **Unbalanced OT** (optional): uses sinkhorn_unbalanced with KL penalty
   (reg_m) so the solver can leave low-quality candidate slots empty rather
   than filling them with weak cards.  When reg_m is large the problem
   approaches balanced OT; when small, more mass is allowed to vanish.

3. **ILP rounding**: instead of greedy rounding (which discards the structure
   of the fractional plan), solves a small integer linear program via
   scipy.optimize.milp to find the integer card counts closest to the
   fractional marginal while respecting copy limits and deck-size targets.
   Falls back to greedy rounding if scipy is unavailable.

4. **Seed-relative cost**: the pairwise cost matrix C[i,j] blends embedding
   distance between pool cards (structural diversity) with each card's
   individual affinity cost to the seed deck (quality signal), avoiding the
   circular pattern where both source and target are derived from the same
   embedding similarity.

The log-stabilized Sinkhorn solver (pot.sinkhorn with method='sinkhorn_log')
produces the fractional transport plan.  Log-domain stabilization avoids
overflow/underflow at low regularization (reg=0.01).

Requires: pip install pot  (or uv add pot)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

from .constants import MAGIC_BASIC_LANDS, POKEMON_BASIC_ENERGY
from .deck_completion import (
    CandidateFn,
    CMCFn,
    TagSetFn,
    _legal_add,
    _main_partition_name,
)


logger = logging.getLogger("decksage.ot_completion")

try:
    import ot as pot  # type: ignore[import-not-found]
except ImportError:
    pot = None
    logger.warning("POT not installed. Install with: uv add pot")


@dataclass
class FormatConstraints:
    """Format-specific deck building constraints.

    Returned by ``get_format_constraints`` for known game/format pairs.
    """

    min_deck_size: int = 60
    max_deck_size: int | None = None  # None = no upper bound
    copy_limit: int = 4
    singleton: bool = False  # Commander: all non-basics limited to 1
    color_identity_required: bool = False  # Commander: cards must match CI
    basics_unlimited: bool = True  # Basic lands/energy exempt from copy limit


# -- Format preset tables --------------------------------------------------

_MAGIC_FORMATS: dict[str, FormatConstraints] = {
    "standard": FormatConstraints(min_deck_size=60, copy_limit=4),
    "modern": FormatConstraints(min_deck_size=60, copy_limit=4),
    "pioneer": FormatConstraints(min_deck_size=60, copy_limit=4),
    "legacy": FormatConstraints(min_deck_size=60, copy_limit=4),
    "vintage": FormatConstraints(min_deck_size=60, copy_limit=4),
    "pauper": FormatConstraints(min_deck_size=60, copy_limit=4),
    "commander": FormatConstraints(
        min_deck_size=100,
        max_deck_size=100,
        copy_limit=1,
        singleton=True,
        color_identity_required=True,
    ),
    "draft": FormatConstraints(min_deck_size=40, copy_limit=100, basics_unlimited=True),
    "sealed": FormatConstraints(min_deck_size=40, copy_limit=100, basics_unlimited=True),
}

_YUGIOH_FORMATS: dict[str, FormatConstraints] = {
    "advanced": FormatConstraints(min_deck_size=40, max_deck_size=60, copy_limit=3),
    "traditional": FormatConstraints(min_deck_size=40, max_deck_size=60, copy_limit=3),
}

_POKEMON_FORMATS: dict[str, FormatConstraints] = {
    "standard": FormatConstraints(min_deck_size=60, max_deck_size=60, copy_limit=4),
    "expanded": FormatConstraints(min_deck_size=60, max_deck_size=60, copy_limit=4),
    "pocket": FormatConstraints(min_deck_size=20, max_deck_size=20, copy_limit=2),
}

_FORMAT_TABLES: dict[str, dict[str, FormatConstraints]] = {
    "magic": _MAGIC_FORMATS,
    "yugioh": _YUGIOH_FORMATS,
    "pokemon": _POKEMON_FORMATS,
}


def get_format_constraints(game: str, format: str | None = None) -> FormatConstraints:
    """Return format constraints for a game/format pair.

    Falls back to sensible per-game defaults when ``format`` is None or
    unrecognised.
    """
    if format is None:
        # Sensible defaults per game
        if game == "yugioh":
            return FormatConstraints(min_deck_size=40, max_deck_size=60, copy_limit=3)
        if game == "pokemon":
            return FormatConstraints(min_deck_size=60, max_deck_size=60, copy_limit=4)
        return FormatConstraints(min_deck_size=60, copy_limit=4)

    table = _FORMAT_TABLES.get(game, {})
    key = format.strip().lower()
    if key in table:
        return table[key]

    logger.debug("Unknown format '%s' for game '%s', using game defaults", format, game)
    return get_format_constraints(game, None)


def _is_basic(game: str, card_name: str) -> bool:
    """Return True if *card_name* is a basic land / basic energy."""
    if game == "magic":
        return card_name in MAGIC_BASIC_LANDS
    if game == "pokemon":
        return card_name in POKEMON_BASIC_ENERGY
    return False


@dataclass
class OTCompletionConfig:
    """Configuration for OT-based deck completion."""

    game: Literal["magic", "yugioh", "pokemon"] = "magic"
    target_main_size: int = 60

    # Cost matrix weights (must sum to 1.0 for interpretability, but not enforced)
    # Tuned via parameter sweep (2026-03-01): reg=0.01, emb=0.3 gave lowest OT distance
    embedding_weight: float = 0.3
    role_weight: float = 0.1
    curve_weight: float = 0.6

    # Sinkhorn parameters
    sinkhorn_reg: float = 0.01  # Entropic regularization (lower = sparser plan)
    sinkhorn_max_iter: int = 1000
    sinkhorn_tol: float = 1e-9

    # Unbalanced OT: KL marginal penalty.  None = balanced (original behavior).
    # Typical values: 0.5 (aggressive filtering) to 5.0 (near-balanced).
    # When set, sinkhorn_unbalanced is used instead of sinkhorn.
    reg_m: float | None = None

    # Source distribution temperature.  Lower = concentrate mass on high-affinity
    # candidates.  None = uniform source (original behavior).
    source_temperature: float | None = 0.2

    # Rounding strategy: "ilp" (integer linear program) or "greedy" (original).
    rounding: Literal["ilp", "greedy"] = "ilp"

    # Rounding
    max_copies: int | None = None  # Override per-game default

    # Pool filtering
    pool_size: int = 200  # Max candidate pool size (top-k by embedding similarity)

    # Format-aware constraints (v3, 2026-03-17)
    format: str | None = None  # e.g. "standard", "modern", "commander"
    legality_data: dict[str, dict[str, str]] | None = None  # card -> format -> status
    color_identity: set[str] | None = None  # For Commander CI filtering
    card_color_identity: dict[str, set[str]] | None = None  # card -> color identity set

    # Archetype-aware completion (v4, 2026-03-17)
    # When set, uses archetype template to shape source distribution,
    # curve target, and cost matrix.  Load from archetype_templates_{game}.json.
    archetype_template: dict | None = None  # ArchetypeTemplate as dict


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


def compute_source_distribution(
    seed_cards: list[str],
    embeddings: Any,
    card_pool: list[str],
    temperature: float | None = None,
) -> np.ndarray:
    """
    Build a quality-weighted source distribution over the candidate pool.

    Unlike the uniform source in balanced OT, this assigns more mass to
    candidates with higher affinity to the seed deck.  The solver then
    preferentially transports from these high-quality candidates.

    When temperature is None, returns uniform (backward-compatible).

    Args:
        seed_cards: Cards currently in deck
        embeddings: KeyedVectors with card embeddings
        card_pool: Candidate pool
        temperature: Softmax temperature (lower = sharper).  None = uniform.

    Returns:
        1-D array of shape (len(card_pool),) summing to 1.0
    """
    n = len(card_pool)
    if temperature is None or not seed_cards or embeddings is None:
        return np.ones(n, dtype=np.float64) / n

    # Reuse the reference distribution logic with the source temperature
    return compute_reference_distribution(
        seed_cards=seed_cards,
        embeddings=embeddings,
        card_pool=card_pool,
        temperature=temperature,
    )


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
    Build a per-card cost vector for adding each candidate to the deck.

    The cost combines:
    1. Embedding distance (1 - cosine similarity) to seed cards
    2. Role penalty: higher cost for cards that don't fill identified role gaps
    3. Curve penalty: higher cost for cards whose CMC deviates from target curve

    Returns:
        1-D array of shape (len(card_pool),).
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


def _round_transport_plan_greedy(
    plan_marginal: np.ndarray,
    card_pool: list[str],
    deck: dict,
    game: str,
    slots_to_fill: int,
    max_copies: int | None = None,
    *,
    per_card_limits: dict[str, int] | None = None,
    format_constraints: FormatConstraints | None = None,
) -> list[tuple[str, int]]:
    """
    Round fractional OT plan to integer card counts via greedy rounding.

    Sort by fractional mass, greedily assign copies while respecting copy
    limits and total slot count.

    Args:
        plan_marginal: 1-D array of fractional card masses from OT solution
        card_pool: List of card names corresponding to plan indices
        deck: Current deck (for copy limit checking)
        game: Game name
        slots_to_fill: Number of card slots to add
        max_copies: Override per-game copy limit
        per_card_limits: Per-card copy limit overrides (e.g. restricted/limited cards)
        format_constraints: Format constraints (singleton, basics_unlimited, etc.)

    Returns:
        List of (card_name, count) tuples
    """
    if max_copies is None:
        if format_constraints is not None:
            max_copies = format_constraints.copy_limit
        elif game == "yugioh":
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


# Keep the old name as an alias for backward compatibility
_round_transport_plan = _round_transport_plan_greedy


def _round_transport_plan_ilp(
    plan_marginal: np.ndarray,
    card_pool: list[str],
    deck: dict,
    game: str,
    slots_to_fill: int,
    max_copies: int | None = None,
    *,
    per_card_limits: dict[str, int] | None = None,
    format_constraints: FormatConstraints | None = None,
) -> list[tuple[str, int]]:
    """
    Round fractional OT plan to integer card counts via integer linear program.

    Solves:  minimize  sum_i |x_i - slots_to_fill * marginal_i|
    subject to:  sum_i x_i = slots_to_fill
                 0 <= x_i <= copy_limit_i  (integer)

    The absolute-value objective is linearized via auxiliary variables:
      for each i: t_i >= x_i - f_i,  t_i >= f_i - x_i,  t_i >= 0
    where f_i = slots_to_fill * marginal_i.

    Falls back to greedy rounding if scipy.optimize.milp is unavailable or
    the solver fails.

    Args:
        plan_marginal: 1-D array of fractional card masses from OT solution
        card_pool: List of card names corresponding to plan indices
        deck: Current deck (for copy limit checking)
        game: Game name
        slots_to_fill: Number of card slots to add
        max_copies: Override per-game copy limit
        per_card_limits: Per-card copy limit overrides (e.g. restricted/limited cards)
        format_constraints: Format constraints (singleton, basics_unlimited, etc.)

    Returns:
        List of (card_name, count) tuples
    """
    try:
        from scipy.optimize import LinearConstraint, milp
        from scipy.sparse import eye as speye
        from scipy.sparse import hstack, vstack
    except ImportError:
        logger.debug("scipy.optimize.milp unavailable, falling back to greedy rounding")
        return _round_transport_plan_greedy(
            plan_marginal, card_pool, deck, game, slots_to_fill, max_copies
        )

    if max_copies is None:
        if format_constraints is not None:
            max_copies = format_constraints.copy_limit
        else:
            max_copies = 3 if game == "yugioh" else 4

    n = len(card_pool)
    if n == 0 or slots_to_fill <= 0:
        return []

    # Fractional targets
    frac = plan_marginal * slots_to_fill

    # Determine per-card copy limit (accounting for cards already in deck)
    upper_bounds = np.full(n, max_copies, dtype=np.float64)

    # Apply format-specific overrides
    fc = format_constraints
    for i, name in enumerate(card_pool):
        limit = max_copies
        # Basics are unlimited in most formats
        if fc and fc.basics_unlimited and _is_basic(game, name):
            limit = slots_to_fill  # effectively unlimited
        # Per-card overrides (restricted/limited/semi-limited)
        if per_card_limits and name in per_card_limits:
            limit = min(limit, per_card_limits[name])
        upper_bounds[i] = limit

    part_name = _main_partition_name(game)
    for i, name in enumerate(card_pool):
        existing = 0
        for p in deck.get("partitions", []) or []:
            for c in p.get("cards", []) or []:
                if c.get("name") == name:
                    existing += int(c.get("count", 0))
        upper_bounds[i] = max(0, upper_bounds[i] - existing)

    # Variables: x_0..x_{n-1} (integer card counts), t_0..t_{n-1} (abs deviations)
    # Objective: minimize sum(t_i)  (c = [0]*n + [1]*n)
    c_obj = np.zeros(2 * n)
    c_obj[n:] = 1.0  # minimize sum of t_i

    # Bounds: x_i in [0, upper_bounds[i]] (integer), t_i in [0, inf]
    from scipy.optimize import Bounds

    lb = np.zeros(2 * n)
    ub = np.concatenate([upper_bounds, np.full(n, np.inf)])
    bounds = Bounds(lb=lb, ub=ub)

    # Integrality: x_i = 1 (integer), t_i = 0 (continuous)
    integrality = np.zeros(2 * n, dtype=int)
    integrality[:n] = 1

    # Constraint 1: sum(x_i) = slots_to_fill
    import scipy.sparse as sp

    row_x = sp.csc_matrix(np.ones((1, n)))
    row_t = sp.csc_matrix(np.zeros((1, n)))
    A_eq = hstack([row_x, row_t], format="csc")
    sum_constraint = LinearConstraint(A_eq, lb=slots_to_fill, ub=slots_to_fill)

    # Constraint 2: t_i >= x_i - f_i  =>  -t_i + x_i <= f_i
    # Constraint 3: t_i >= f_i - x_i  =>  -t_i - x_i <= -f_i
    # Combined: for each i,
    #   x_i - t_i <= f_i     =>  row: [...0, 1, 0... | ...0, -1, 0...]
    #   -x_i - t_i <= -f_i   =>  row: [...0, -1, 0... | ...0, -1, 0...]

    I_n = speye(n, format="csc")
    # x_i - t_i <= f_i
    A_pos = hstack([I_n, -I_n], format="csc")
    # -x_i - t_i <= -f_i
    A_neg = hstack([-I_n, -I_n], format="csc")

    A_abs = vstack([A_pos, A_neg], format="csc")
    abs_ub = np.concatenate([frac, -frac])
    abs_constraint = LinearConstraint(A_abs, lb=-np.inf, ub=abs_ub)

    try:
        result = milp(
            c=c_obj,
            constraints=[sum_constraint, abs_constraint],
            integrality=integrality,
            bounds=bounds,
            options={"time_limit": 5.0},
        )
        if not result.success:
            logger.debug(
                f"ILP solver did not find optimal: {result.message}, falling back to greedy"
            )
            return _round_transport_plan_greedy(
                plan_marginal, card_pool, deck, game, slots_to_fill, max_copies
            )

        x = np.round(result.x[:n]).astype(int)
    except Exception as e:
        logger.debug(f"ILP solver failed: {e}, falling back to greedy")
        return _round_transport_plan_greedy(
            plan_marginal, card_pool, deck, game, slots_to_fill, max_copies
        )

    # Build additions list (verify legality).
    # Mutate ``deck`` in place (same contract as the greedy rounding function)
    # so that the caller sees the updated deck.
    additions: list[tuple[str, int]] = []

    for idx in np.argsort(-x):
        count = int(x[idx])
        if count <= 0:
            continue
        name = card_pool[idx]

        actual = 0
        for _ in range(count):
            if _legal_add(game, deck, name):
                actual += 1
                for p in deck.get("partitions", []) or []:
                    if p.get("name") == part_name:
                        added = False
                        for c in p.get("cards", []) or []:
                            if c.get("name") == name:
                                c["count"] = c.get("count", 0) + 1
                                added = True
                                break
                        if not added:
                            p.setdefault("cards", []).append({"name": name, "count": 1})
                        break

        if actual > 0:
            additions.append((name, actual))

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
    2. Construct source (quality-weighted) and target (archetype) distributions
    3. Build cost matrix (embedding + role + curve)
    4. Solve OT (balanced or unbalanced) with Sinkhorn
    5. Round fractional plan to integer counts (ILP or greedy)
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

    # Format-aware candidate filtering (before OT, so solver only sees legal cards)
    fmt_constraints = get_format_constraints(game, cfg.format)
    pre_filter_size = len(card_pool)

    if cfg.format and cfg.legality_data:
        fmt_key = cfg.format.strip().lower()
        card_pool = [
            c
            for c in card_pool
            if cfg.legality_data.get(c, {}).get(fmt_key) in ("legal", "restricted", None)
        ]

    if cfg.color_identity and cfg.card_color_identity:
        # Commander: exclude cards whose CI is not a subset of the deck CI
        deck_ci = cfg.color_identity
        card_pool = [
            c
            for c in card_pool
            if _is_basic(game, c) or cfg.card_color_identity.get(c, set()).issubset(deck_ci)
        ]

    format_filtered = pre_filter_size - len(card_pool)
    if format_filtered > 0:
        logger.info(
            "Format filter (%s/%s): removed %d of %d candidates",
            game,
            cfg.format,
            format_filtered,
            pre_filter_size,
        )

    if not card_pool:
        logger.warning("Empty candidate pool, cannot complete deck via OT")
        return OTCompletionResult(
            deck=deck,
            additions=[],
            metrics={"error": "empty_candidate_pool"},
        )

    n = len(card_pool)

    # Archetype-derived defaults: when an archetype template is provided,
    # use its curve/role distributions as fallback targets and bias costs
    # toward archetype-appropriate cards.
    archetype_core_set: set[str] = set()
    if cfg.archetype_template is not None:
        at = cfg.archetype_template
        # Use archetype CMC histogram as curve target if none provided
        if curve_target is None and at.get("cmc_histogram"):
            curve_target = {int(k): v for k, v in at["cmc_histogram"].items()}
            logger.info("Using archetype curve target from '%s'", at.get("name", "?"))
        # Build core card set for cost bonus
        for entry in at.get("core_cards", []):
            if isinstance(entry, (list, tuple)) and len(entry) >= 1:
                archetype_core_set.add(entry[0])
        for entry in at.get("flex_cards", []):
            if isinstance(entry, (list, tuple)) and len(entry) >= 1:
                archetype_core_set.add(entry[0])

    # Source distribution: quality-weighted (or uniform if source_temperature is None)
    source = compute_source_distribution(
        seed_cards=seed_cards,
        embeddings=embeddings,
        card_pool=card_pool,
        temperature=cfg.source_temperature,
    )

    # Target distribution: similarity-weighted over candidate pool
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

    # Archetype cost bonus: reduce cost for cards in archetype core/flex
    if archetype_core_set:
        for i, name in enumerate(card_pool):
            if name in archetype_core_set:
                cost_vec[i] *= 0.7  # 30% cost reduction for archetype cards

    # Build pairwise cost matrix for OT
    cost_matrix = _build_pairwise_cost_matrix(
        card_pool=card_pool,
        embeddings=embeddings,
        cost_vec=cost_vec,
    )

    # Solve OT
    unbalanced = cfg.reg_m is not None
    marginal_err = 0.0
    try:
        if unbalanced:
            # Unbalanced OT: allows partial transport.  Cards that are poor
            # matches can be skipped (their mass is "destroyed" with KL penalty).
            transport_plan = pot.sinkhorn_unbalanced(
                source,
                target,
                cost_matrix,
                reg=cfg.sinkhorn_reg,
                reg_m=cfg.reg_m,
                numItermax=cfg.sinkhorn_max_iter,
                stopThr=cfg.sinkhorn_tol,
            )
            # For unbalanced, marginals don't have to match source/target exactly
            row_marginal = transport_plan.sum(axis=1)
            transported_mass = float(transport_plan.sum())
            marginal_err = float(abs(transported_mass - 1.0))
        else:
            # Balanced OT with log-stabilized Sinkhorn
            transport_plan = pot.sinkhorn(
                source,
                target,
                cost_matrix,
                reg=cfg.sinkhorn_reg,
                method="sinkhorn_log",
                numItermax=cfg.sinkhorn_max_iter,
                stopThr=cfg.sinkhorn_tol,
                warn=False,
            )
            # Verify marginal convergence
            row_marginal = transport_plan.sum(axis=1)
            marginal_err = float(np.max(np.abs(row_marginal - source)))
            if marginal_err > 1e-3:
                logger.warning(
                    f"Sinkhorn marginal error {marginal_err:.6f} exceeds tolerance; "
                    "transport plan may be inaccurate"
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

    # For unbalanced OT, renormalize the marginal so it sums to 1.0
    # (total transported mass may be < 1.0)
    marginal_sum = target_marginal.sum()
    if marginal_sum > 1e-10:
        target_marginal_norm = target_marginal / marginal_sum
    else:
        target_marginal_norm = target_marginal

    # Build per-card copy limit overrides from legality data
    per_card_limits: dict[str, int] | None = None
    if cfg.format and cfg.legality_data:
        fmt_key = cfg.format.strip().lower()
        pcl: dict[str, int] = {}
        for cname in card_pool:
            status = cfg.legality_data.get(cname, {}).get(fmt_key)
            if status == "restricted":
                pcl[cname] = 1  # Vintage restricted, YGO limited
            # "banned" cards were already filtered out above; this handles
            # semi-limited (YGO convention: not in Scryfall data but could be
            # supplied by caller).
        if pcl:
            per_card_limits = pcl

    # Round to integer counts
    if cfg.rounding == "ilp":
        additions = _round_transport_plan_ilp(
            plan_marginal=target_marginal_norm,
            card_pool=card_pool,
            deck=deck,
            game=game,
            slots_to_fill=slots_to_fill,
            max_copies=cfg.max_copies,
            per_card_limits=per_card_limits,
            format_constraints=fmt_constraints,
        )
    else:
        additions = _round_transport_plan_greedy(
            plan_marginal=target_marginal_norm,
            card_pool=card_pool,
            deck=deck,
            game=game,
            slots_to_fill=slots_to_fill,
            max_copies=cfg.max_copies,
            per_card_limits=per_card_limits,
            format_constraints=fmt_constraints,
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
                f"Fills roles: {', '.join(filled_roles)}"
                if filled_roles
                else "Embedding similarity"
            )
        else:
            record["reasoning"] = "Embedding similarity"
        addition_records.append(record)

    # Compute OT distance (Wasserstein approximation)
    ot_distance = float(np.sum(transport_plan * cost_matrix))

    metrics: dict[str, Any] = {
        "slots_to_fill": slots_to_fill,
        "current_size": current_size,
        "pool_size": n,
        "cards_added": sum(c for _, c in additions),
        "ot_distance": ot_distance,
        "sinkhorn_reg": cfg.sinkhorn_reg,
        "marginal_error": marginal_err,
        "rounding": cfg.rounding,
        "source_type": "quality_weighted" if cfg.source_temperature is not None else "uniform",
    }
    if unbalanced:
        metrics["reg_m"] = cfg.reg_m
        metrics["transported_mass"] = float(transport_plan.sum())
    if cfg.format:
        metrics["format"] = cfg.format
        metrics["format_filtered"] = format_filtered
    if cfg.archetype_template:
        metrics["archetype"] = cfg.archetype_template.get("name", "unknown")
        metrics["archetype_core_cards_in_pool"] = len(archetype_core_set & set(card_pool))

    return OTCompletionResult(
        deck=deck,
        additions=addition_records,
        transport_plan=transport_plan,
        cost_matrix=cost_matrix,
        metrics=metrics,
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
    "FormatConstraints",
    "OTCompletionConfig",
    "OTCompletionResult",
    "build_cost_matrix",
    "compute_reference_distribution",
    "compute_source_distribution",
    "deck_to_distribution",
    "get_format_constraints",
    "ot_complete_deck",
]
