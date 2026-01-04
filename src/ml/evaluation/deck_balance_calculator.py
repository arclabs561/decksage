#!/usr/bin/env python3
"""
Deck Balance Calculator

Calculates deck balance metrics: curve, land count, color distribution.
Used for evaluating if suggestions maintain/improve deck balance.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any


@dataclass
class DeckBalance:
    """Deck balance metrics."""

    avg_cmc: float
    land_count: int
    color_distribution: dict[str, float]  # Color -> percentage
    curve: dict[int, int]  # CMC -> count
    total_cards: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict."""
        return {
            "avg_cmc": self.avg_cmc,
            "land_count": self.land_count,
            "color_distribution": self.color_distribution,
            "curve": self.curve,
            "total_cards": self.total_cards,
        }


def calculate_deck_balance(
    deck: dict[str, Any],
    game: str = "magic",
    cmc_fn: callable | None = None,
    color_fn: callable | None = None,
) -> DeckBalance:
    """
    Calculate deck balance metrics.

    Args:
        deck: Deck dict with partitions and cards
        game: Game type ("magic", "yugioh", "pokemon")
        cmc_fn: Function to get CMC/mana cost for a card
        color_fn: Function to get colors for a card

    Returns:
        DeckBalance with all metrics
    """
    # Get main partition
    main_partition = None
    for p in deck.get("partitions", []) or []:
        if p.get("name") in ("Main", "Main Deck"):
            main_partition = p
            break

    if not main_partition:
        return DeckBalance(
            avg_cmc=0.0,
            land_count=0,
            color_distribution={},
            curve={},
            total_cards=0,
        )

    cards = main_partition.get("cards", []) or []

    # Calculate totals
    total_cards = sum(c.get("count", 0) for c in cards)

    # Calculate curve (CMC distribution)
    curve: dict[int, int] = defaultdict(int)
    total_cmc = 0
    total_nonland_cmc = 0
    nonland_count = 0
    land_count = 0

    color_counts: Counter = Counter()

    for card_data in cards:
        card_name = card_data.get("name", "")
        count = card_data.get("count", 0)

        # Get CMC
        if cmc_fn:
            cmc = cmc_fn(card_name) or 0
        else:
            cmc = card_data.get("cmc") or card_data.get("mana_cost") or 0

        # Update curve
        curve[cmc] += count
        total_cmc += cmc * count

        # Check if land (simplified - would need better detection)
        is_land = _is_land(card_name, game)

        if is_land:
            land_count += count
        else:
            total_nonland_cmc += cmc * count
            nonland_count += count

        # Get colors
        if color_fn:
            colors = color_fn(card_name) or []
        else:
            colors = card_data.get("colors", []) or []

        for color in colors:
            color_counts[color] += count

    # Calculate average CMC (excluding lands)
    avg_cmc = total_nonland_cmc / nonland_count if nonland_count > 0 else 0.0

    # Calculate color distribution
    total_colored = sum(color_counts.values())
    color_distribution = {
        color: (count / total_colored * 100) if total_colored > 0 else 0.0
        for color, count in color_counts.items()
    }

    return DeckBalance(
        avg_cmc=avg_cmc,
        land_count=land_count,
        color_distribution=color_distribution,
        curve=dict(curve),
        total_cards=total_cards,
    )


def _is_land(card_name: str, game: str) -> bool:
    """Check if card is a land (simplified)."""
    if game != "magic":
        return False  # Other games don't have lands

    # Basic land names
    basic_lands = {
        "Plains",
        "Island",
        "Swamp",
        "Mountain",
        "Forest",
        "Snow-Covered Plains",
        "Snow-Covered Island",
        "Snow-Covered Swamp",
        "Snow-Covered Mountain",
        "Snow-Covered Forest",
    }

    if card_name in basic_lands:
        return True

    # Check if name contains "Land" (simplified)
    if "Land" in card_name.lower():
        return True

    return False


def calculate_balance_impact(
    deck_before: DeckBalance,
    deck_after: DeckBalance,
    archetype_norms: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Calculate how adding/removing cards impacts deck balance.

    Args:
        deck_before: Balance before change
        deck_after: Balance after change
        archetype_norms: Normal values for archetype (avg_cmc, land_count, etc.)

    Returns:
        Dict with impact scores and analysis
    """
    # Compare to archetype norms if available
    if archetype_norms:
        target_avg_cmc = archetype_norms.get("avg_cmc", 2.5)
        target_land_count = archetype_norms.get("land_count", 20)
        target_land_percentage = archetype_norms.get("land_percentage", 0.33)
    else:
        # Default norms (Magic: The Gathering)
        target_avg_cmc = 2.5
        target_land_count = 20
        target_land_percentage = 0.33

    # Calculate deviations from norms
    cmc_deviation_before = abs(deck_before.avg_cmc - target_avg_cmc)
    cmc_deviation_after = abs(deck_after.avg_cmc - target_avg_cmc)
    cmc_improvement = cmc_deviation_before - cmc_deviation_after

    land_deviation_before = abs(deck_before.land_count - target_land_count)
    land_deviation_after = abs(deck_after.land_count - target_land_count)
    land_improvement = land_deviation_before - land_deviation_after

    # Calculate overall impact score (0-4)
    # 4: Significantly improves balance
    # 3: Maintains good balance
    # 2: Neutral
    # 1: Slightly hurts
    # 0: Significantly hurts

    improvements = []
    if cmc_improvement > 0.2:
        improvements.append("cmc")
    if land_improvement > 2:
        improvements.append("land")

    if len(improvements) >= 2:
        impact_score = 4.0
    elif len(improvements) == 1:
        impact_score = 3.0
    elif cmc_improvement < -0.2 or land_improvement < -2:
        impact_score = 1.0
    elif cmc_improvement < -0.5 or land_improvement < -5:
        impact_score = 0.0
    else:
        impact_score = 2.0

    return {
        "impact_score": impact_score,
        "cmc_improvement": cmc_improvement,
        "land_improvement": land_improvement,
        "improvements": improvements,
        "before": deck_before.to_dict(),
        "after": deck_after.to_dict(),
    }


__all__ = [
    "DeckBalance",
    "calculate_balance_impact",
    "calculate_deck_balance",
]
