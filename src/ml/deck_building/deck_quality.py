#!/usr/bin/env python3
"""
Deck Quality Metrics

Validates completed decks against tournament deck patterns:
- Mana curve fit (KL divergence from archetype average)
- Tag diversity (Shannon entropy of tag distribution)
- Synergy coherence (functional tag pairs that co-occur)
- Overall quality score

Usage:
    from ml.deck_building.deck_quality import DeckQualityMetrics, assess_deck_quality
    
    metrics = assess_deck_quality(
        deck=completed_deck,
        game="magic",
        archetype="Burn",
        tag_set_fn=functional_tagger.tag_card,
        cmc_fn=get_cmc,
        reference_decks=tournament_decks_in_archetype,
    )
    
    print(f"Quality score: {metrics.overall_score:.1f}/10.0")
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Callable

from ..data.card_resolver import CardResolver


@dataclass
class DeckQualityMetrics:
    """Quality metrics for a completed deck"""

    # Mana curve fit (0-1, higher is better)
    # KL divergence from archetype average (lower is better, so we invert)
    mana_curve_score: float

    # Tag diversity (0-1, higher is better)
    # Shannon entropy of functional tag distribution
    tag_balance_score: float

    # Synergy coherence (0-1, higher is better)
    # Average pairwise functional tag overlap with reference decks
    synergy_score: float

    # Overall quality score (0-10, higher is better)
    overall_score: float

    # Metadata
    num_cards: int
    num_unique_tags: int
    avg_tags_per_card: float


def compute_mana_curve(
    deck: dict,
    game: str,
    cmc_fn: Callable[[str], int | None],
    partition_name: str | None = None,
) -> dict[int, float]:
    """
    Compute normalized mana curve (CMC distribution).

    Returns dict mapping CMC -> proportion of deck.
    """
    if partition_name is None:
        if game == "magic":
            partition_name = "Main"
        elif game == "yugioh":
            partition_name = "Main Deck"
        else:  # pokemon
            partition_name = "Main Deck"

    resolver = CardResolver()
    cmc_counts: Counter[int] = Counter()
    total = 0

    for p in deck.get("partitions", []) or []:
        if p.get("name") != partition_name:
            continue
        for card in p.get("cards", []) or []:
            card_name = resolver.canonical(str(card.get("name", "")))
            count = int(card.get("count", 0))
            cmc = cmc_fn(card_name)
            if cmc is not None:
                cmc_counts[cmc] += count
                total += count

    if total == 0:
        return {}

    # Normalize to proportions
    return {cmc: count / total for cmc, count in cmc_counts.items()}


def kl_divergence(p: dict[int, float], q: dict[int, float]) -> float:
    """
    Compute KL divergence D_KL(P || Q).

    Returns 0 if distributions are identical, higher values indicate more divergence.
    """
    # Smooth distributions (add small epsilon to avoid log(0))
    epsilon = 1e-10
    all_keys = set(p.keys()) | set(q.keys())

    kl = 0.0
    for k in all_keys:
        p_k = p.get(k, 0.0) + epsilon
        q_k = q.get(k, 0.0) + epsilon
        kl += p_k * math.log(p_k / q_k)

    return kl


def compute_archetype_curve(
    reference_decks: list[dict],
    game: str,
    cmc_fn: Callable[[str], int | None],
) -> dict[int, float]:
    """
    Compute average mana curve from reference tournament decks.

    Returns normalized CMC distribution.
    """
    if not reference_decks:
        return {}

    resolver = CardResolver()
    cmc_counts: Counter[int] = Counter()
    total = 0

    partition_name = "Main" if game == "magic" else "Main Deck"

    for deck in reference_decks:
        for p in deck.get("partitions", []) or []:
            if p.get("name") != partition_name:
                continue
            for card in p.get("cards", []) or []:
                card_name = resolver.canonical(str(card.get("name", "")))
                count = int(card.get("count", 0))
                cmc = cmc_fn(card_name)
                if cmc is not None:
                    cmc_counts[cmc] += count
                    total += count

    if total == 0:
        return {}

    return {cmc: count / total for cmc, count in cmc_counts.items()}


def compute_tag_distribution(
    deck: dict,
    game: str,
    tag_set_fn: Callable[[str], set[str]],
    partition_name: str | None = None,
) -> dict[str, int]:
    """
    Compute functional tag distribution in deck.

    Returns dict mapping tag -> count of cards with that tag.
    """
    if partition_name is None:
        if game == "magic":
            partition_name = "Main"
        elif game == "yugioh":
            partition_name = "Main Deck"
        else:  # pokemon
            partition_name = "Main Deck"

    resolver = CardResolver()
    tag_counts: Counter[str] = Counter()

    for p in deck.get("partitions", []) or []:
        if p.get("name") != partition_name:
            continue
        for card in p.get("cards", []) or []:
            card_name = resolver.canonical(str(card.get("name", "")))
            tags = tag_set_fn(card_name)
            for tag in tags:
                tag_counts[tag] += int(card.get("count", 0))

    return dict(tag_counts)


def shannon_entropy(distribution: dict[str, int]) -> float:
    """
    Compute Shannon entropy of a distribution.

    Higher entropy = more diversity.
    """
    total = sum(distribution.values())
    if total == 0:
        return 0.0

    entropy = 0.0
    for count in distribution.values():
        if count > 0:
            p = count / total
            entropy -= p * math.log2(p)

    return entropy


def compute_synergy_score(
    deck: dict,
    game: str,
    tag_set_fn: Callable[[str], set[str]],
    reference_decks: list[dict],
    partition_name: str | None = None,
) -> float:
    """
    Compute synergy coherence score.

    Measures how well functional tags in deck match patterns from reference decks.
    Uses average pairwise tag overlap.
    """
    if not reference_decks:
        return 0.5  # Neutral score if no reference

    if partition_name is None:
        if game == "magic":
            partition_name = "Main"
        elif game == "yugioh":
            partition_name = "Main Deck"
        else:  # pokemon
            partition_name = "Main Deck"

    resolver = CardResolver()

    # Get deck's tag set
    deck_tags: set[str] = set()
    for p in deck.get("partitions", []) or []:
        if p.get("name") != partition_name:
            continue
        for card in p.get("cards", []) or []:
            card_name = resolver.canonical(str(card.get("name", "")))
            deck_tags |= tag_set_fn(card_name)

    if not deck_tags:
        return 0.0

    # Get reference deck tag sets
    reference_tag_sets: list[set[str]] = []
    for ref_deck in reference_decks:
        ref_tags: set[str] = set()
        for p in ref_deck.get("partitions", []) or []:
            if p.get("name") != partition_name:
                continue
            for card in p.get("cards", []) or []:
                card_name = resolver.canonical(str(card.get("name", "")))
                ref_tags |= tag_set_fn(card_name)
        if ref_tags:
            reference_tag_sets.append(ref_tags)

    if not reference_tag_sets:
        return 0.5

    # Compute average Jaccard similarity with reference decks
    similarities = []
    for ref_tags in reference_tag_sets:
        intersection = len(deck_tags & ref_tags)
        union = len(deck_tags | ref_tags)
        if union > 0:
            jaccard = intersection / union
            similarities.append(jaccard)

    if not similarities:
        return 0.5

    return sum(similarities) / len(similarities)


def assess_deck_quality(
    deck: dict,
    game: str,
    tag_set_fn: Callable[[str], set[str]],
    cmc_fn: Callable[[str], int | None],
    reference_decks: list[dict] | None = None,
    archetype: str | None = None,
    *,
    curve_weight: float = 0.35,
    tag_balance_weight: float = 0.30,
    synergy_weight: float = 0.35,
) -> DeckQualityMetrics:
    """
    Assess quality of a completed deck.

    Args:
        deck: Completed deck dict
        game: 'magic', 'pokemon', or 'yugioh'
        tag_set_fn: Function to get functional tags for a card
        cmc_fn: Function to get CMC for a card (returns None if unknown)
        reference_decks: List of tournament decks for comparison (optional)
        archetype: Archetype name (for logging, optional)
        curve_weight: Weight for mana curve score (default 0.35)
        tag_balance_weight: Weight for tag balance score (default 0.30)
        synergy_weight: Weight for synergy score (default 0.35)

    Returns:
        DeckQualityMetrics with all scores
    """
    # Normalize weights
    total_weight = curve_weight + tag_balance_weight + synergy_weight
    if total_weight > 0:
        curve_weight /= total_weight
        tag_balance_weight /= total_weight
        synergy_weight /= total_weight

    # Compute mana curve score
    deck_curve = compute_mana_curve(deck, game, cmc_fn)
    if reference_decks and deck_curve:
        archetype_curve = compute_archetype_curve(reference_decks, game, cmc_fn)
        if archetype_curve:
            kl = kl_divergence(deck_curve, archetype_curve)
            # Convert KL divergence to score (0-1)
            # KL typically ranges 0-2 for reasonable distributions
            # Use exponential decay: score = exp(-kl)
            curve_score = math.exp(-min(kl, 2.0))  # Cap at 2.0 for stability
        else:
            curve_score = 0.5  # Neutral if no reference curve
    else:
        curve_score = 0.5  # Neutral if no curve or no reference

    # Compute tag balance score
    tag_dist = compute_tag_distribution(deck, game, tag_set_fn)
    if tag_dist:
        entropy = shannon_entropy(tag_dist)
        # Normalize entropy (max entropy for n tags is log2(n))
        max_entropy = math.log2(len(tag_dist)) if len(tag_dist) > 1 else 1.0
        tag_balance_score = entropy / max_entropy if max_entropy > 0 else 0.0
    else:
        tag_balance_score = 0.0

    # Compute synergy score
    if reference_decks:
        synergy_score = compute_synergy_score(deck, game, tag_set_fn, reference_decks)
    else:
        synergy_score = 0.5  # Neutral if no reference

    # Compute overall score (0-10 scale)
    overall = (
        curve_score * curve_weight
        + tag_balance_score * tag_balance_weight
        + synergy_score * synergy_weight
    ) * 10.0

    # Collect metadata
    partition_name = "Main" if game == "magic" else "Main Deck"
    num_cards = sum(
        int(c.get("count", 0))
        for p in deck.get("partitions", []) or []
        if p.get("name") == partition_name
        for c in p.get("cards", []) or []
    )

    all_tags: set[str] = set()
    for p in deck.get("partitions", []) or []:
        if p.get("name") == partition_name:
            for card in p.get("cards", []) or []:
                from ..data.card_resolver import CardResolver

                resolver = CardResolver()
                card_name = resolver.canonical(str(card.get("name", "")))
                all_tags |= tag_set_fn(card_name)

    avg_tags = len(all_tags) / num_cards if num_cards > 0 else 0.0

    return DeckQualityMetrics(
        mana_curve_score=curve_score,
        tag_balance_score=tag_balance_score,
        synergy_score=synergy_score,
        overall_score=overall,
        num_cards=num_cards,
        num_unique_tags=len(all_tags),
        avg_tags_per_card=avg_tags,
    )


__all__ = [
    "DeckQualityMetrics",
    "assess_deck_quality",
    "compute_mana_curve",
    "compute_tag_distribution",
    "shannon_entropy",
    "kl_divergence",
]

