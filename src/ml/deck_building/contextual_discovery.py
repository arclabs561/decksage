"""
Contextual card discovery - find synergies, alternatives, upgrades, downgrades.

This module provides functions to discover contextual relationships for cards:
- Synergies: Cards that work well together
- Alternatives: Functional equivalents
- Upgrades: Better versions (more expensive)
- Downgrades: Budget alternatives (cheaper)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..similarity.fusion import WeightedLateFusion


@dataclass
class CardSynergy:
    """A card that synergizes with the query card."""

    card: str
    score: float
    co_occurrence_rate: float  # % of decks with both cards
    reasoning: str


@dataclass
class CardAlternative:
    """A functional alternative to the query card."""

    card: str
    score: float
    reasoning: str


@dataclass
class CardUpgrade:
    """A better version of the query card (more expensive)."""

    card: str
    score: float
    price_delta: float  # Price difference
    reasoning: str


@dataclass
class CardDowngrade:
    """A budget alternative to the query card (cheaper)."""

    card: str
    score: float
    price_delta: float  # Price difference (negative)
    reasoning: str


class ContextualCardDiscovery:
    """Discovers contextual relationships for cards."""

    def __init__(
        self,
        fusion: WeightedLateFusion,
        price_fn: Callable[[str], float | None] | None = None,
        tag_set_fn: Callable[[str], set[str]] | None = None,
        archetype_staples: dict[str, dict[str, float]] | None = None,
        archetype_cooccurrence: dict[str, dict[str, float]] | None = None,
        format_cooccurrence: dict[str, dict[str, dict[str, float]]] | None = None,
    ):
        self.fusion = fusion
        self.price_fn = price_fn
        self.tag_set_fn = tag_set_fn
        self.archetype_staples = archetype_staples or {}
        self.archetype_cooccurrence = archetype_cooccurrence or {}
        self.format_cooccurrence = format_cooccurrence or {}

    def find_synergies(
        self,
        card: str,
        format: str | None = None,
        archetype: str | None = None,
        top_k: int = 10,
    ) -> list[CardSynergy]:
        """
        Find cards that synergize with the query card.

        Uses:
        - Co-occurrence in decks (Jaccard similarity)
        - Archetype co-occurrence (if archetype provided)
        - Format co-occurrence (if format provided)
        """
        synergies: list[CardSynergy] = []

        # Use fusion similarity with "synergy" task type to find synergistic cards
        # First try using fusion.similar() for better task-specific results
        try:
            similar_cards = self.fusion.similar(card, k=top_k * 2, task_type="synergy")
            # Extract card names from similar results
            similar_card_names = {card_name for card_name, _ in similar_cards}
        except Exception:
            similar_card_names = set()

        # Use fusion similarity to find similar cards
        if self.fusion.adj:
            # Get Jaccard similarity (co-occurrence)
            query_neighbors = self.fusion.adj.get(card, set())
            # Combine with fusion.similar() results if available
            if similar_card_names:
                query_neighbors = query_neighbors | similar_card_names
            if query_neighbors:
                # Score by co-occurrence frequency
                for neighbor in query_neighbors:
                    if neighbor == card:
                        continue

                    # Calculate co-occurrence rate (Jaccard)
                    neighbor_neighbors = self.fusion.adj.get(neighbor, set())
                    intersection = len(query_neighbors & neighbor_neighbors)
                    union = len(query_neighbors | neighbor_neighbors)
                    cooccur_rate = intersection / union if union > 0 else 0.0

                    # Boost if in same archetype
                    score = cooccur_rate
                    reasoning_parts = []

                    if archetype and self.archetype_cooccurrence:
                        card_cooccur = self.archetype_cooccurrence.get(card, {})
                        neighbor_cooccur_rate = card_cooccur.get(neighbor, 0.0)
                        if neighbor_cooccur_rate > 0.3:  # Lower threshold
                            score *= 1.0 + neighbor_cooccur_rate * 0.3  # Up to 30% boost
                            reasoning_parts.append(
                                f"high archetype co-occurrence ({neighbor_cooccur_rate:.0%})"
                            )

                    if format and self.format_cooccurrence:
                        format_data = self.format_cooccurrence.get(format, {})
                        card_format = format_data.get(card, {})
                        format_cooccur_rate = card_format.get(neighbor, 0.0)
                        if format_cooccur_rate > 0.3:  # Lower threshold
                            score *= 1.0 + format_cooccur_rate * 0.2  # Up to 20% boost
                            reasoning_parts.append(
                                f"high format co-occurrence ({format_cooccur_rate:.0%})"
                            )

                    if not reasoning_parts:
                        reasoning_parts.append("commonly played together")

                    synergies.append(
                        CardSynergy(
                            card=neighbor,
                            score=score,
                            co_occurrence_rate=cooccur_rate,
                            reasoning=", ".join(reasoning_parts),
                        )
                    )

        # Sort by score
        synergies.sort(key=lambda x: x.score, reverse=True)

        # Limit to top_k
        if len(synergies) > top_k:
            synergies = synergies[:top_k]

        return synergies

    def find_alternatives(
        self,
        card: str,
        top_k: int = 10,
    ) -> list[CardAlternative]:
        """
        Find functional alternatives to the query card.

        Uses:
        - Functional tag similarity (same role)
        - Embedding similarity (similar function)
        """
        alternatives: list[CardAlternative] = []

        # Get current card's role
        current_role: set[str] = set()
        if self.tag_set_fn:
            current_role = self.tag_set_fn(card)

        # Use fusion to find similar cards with "similar" task type for alternatives
        try:
            # Use fusion.similar() with task_type="similar" for finding alternatives
            similar = self.fusion.similar(card, k=top_k * 2, task_type="similar")

            for alt_card, embed_score in similar:
                if alt_card == card:
                    continue

                # Check role overlap
                alt_role: set[str] = set()
                if self.tag_set_fn:
                    alt_role = self.tag_set_fn(alt_card)

                role_overlap = (
                    len(current_role & alt_role) / len(current_role | alt_role)
                    if (current_role | alt_role)
                    else 0.0
                )

                # Score combines embedding similarity and role overlap
                score = float(embed_score) * 0.7 + role_overlap * 0.3

                if role_overlap > 0.5:
                    reasoning = f"functional equivalent (similar role: {', '.join(current_role & alt_role)})"
                else:
                    reasoning = "similar effect"

                alternatives.append(
                    CardAlternative(
                        card=alt_card,
                        score=score,
                        reasoning=reasoning,
                    )
                )
        except (KeyError, AttributeError):
            pass

        # Sort by score
        alternatives.sort(key=lambda x: x.score, reverse=True)

        # Limit to top_k
        if len(alternatives) > top_k:
            alternatives = alternatives[:top_k]

        return alternatives

    def find_upgrades(
        self,
        card: str,
        top_k: int = 10,
    ) -> list[CardUpgrade]:
        """
        Find better versions of the query card (more expensive).

        Uses:
        - Functional similarity (must fill same role)
        - Price comparison (must be more expensive)
        - Archetype staple status (prefer staples)
        """
        upgrades: list[CardUpgrade] = []

        if not self.price_fn:
            return upgrades

        current_price = self.price_fn(card)
        if current_price is None:
            return upgrades

        # Get current card's role
        current_role: set[str] = set()
        if self.tag_set_fn:
            current_role = self.tag_set_fn(card)

        # Find alternatives that are more expensive
        alternatives = self.find_alternatives(card, top_k=top_k * 3)

        for alt in alternatives:
            alt_price = self.price_fn(alt.card)
            if alt_price is None or alt_price <= current_price:
                continue

            # Must fill similar role
            alt_role: set[str] = set()
            if self.tag_set_fn:
                alt_role = self.tag_set_fn(alt.card)

            role_overlap = (
                len(current_role & alt_role) / len(current_role | alt_role)
                if (current_role | alt_role)
                else 0.0
            )
            if role_overlap < 0.3:
                continue  # Not similar enough

            # Score based on similarity and price delta
            price_delta = alt_price - current_price
            score = alt.score * (
                1.0 + min(price_delta / 10.0, 0.3)
            )  # Up to 30% boost for expensive upgrades

            # Boost if archetype staple
            if self.archetype_staples:
                alt_staples = self.archetype_staples.get(alt.card, {})
                if alt_staples:
                    max_inclusion = max(alt_staples.values())
                    if max_inclusion > 0.7:
                        score *= 1.2
                        reasoning = f"upgrade (${current_price:.2f} → ${alt_price:.2f}), archetype staple ({max_inclusion:.0%})"
                    else:
                        reasoning = f"upgrade (${current_price:.2f} → ${alt_price:.2f})"
                else:
                    reasoning = f"upgrade (${current_price:.2f} → ${alt_price:.2f})"
            else:
                reasoning = f"upgrade (${current_price:.2f} → ${alt_price:.2f})"

            upgrades.append(
                CardUpgrade(
                    card=alt.card,
                    score=score,
                    price_delta=price_delta,
                    reasoning=reasoning,
                )
            )

        # Sort by score
        upgrades.sort(key=lambda x: x.score, reverse=True)

        # Limit to top_k
        if len(upgrades) > top_k:
            upgrades = upgrades[:top_k]

        return upgrades

    def find_downgrades(
        self,
        card: str,
        top_k: int = 10,
    ) -> list[CardDowngrade]:
        """
        Find budget alternatives to the query card (cheaper).

        Uses:
        - Functional similarity (must fill same role)
        - Price comparison (must be cheaper)
        - Accepts lower similarity for significant savings
        """
        downgrades: list[CardDowngrade] = []

        if not self.price_fn:
            return downgrades

        current_price = self.price_fn(card)
        if current_price is None:
            return downgrades

        # Get current card's role
        current_role: set[str] = set()
        if self.tag_set_fn:
            current_role = self.tag_set_fn(card)

        # Find alternatives that are cheaper
        alternatives = self.find_alternatives(card, top_k=top_k * 3)

        for alt in alternatives:
            alt_price = self.price_fn(alt.card)
            if alt_price is None or alt_price >= current_price:
                continue

            # Must fill similar role
            alt_role: set[str] = set()
            if self.tag_set_fn:
                alt_role = self.tag_set_fn(alt.card)

            role_overlap = (
                len(current_role & alt_role) / len(current_role | alt_role)
                if (current_role | alt_role)
                else 0.0
            )
            if role_overlap < 0.3:
                continue  # Not similar enough

            # Score based on similarity and price savings
            price_delta = alt_price - current_price  # Negative
            savings_pct = abs(price_delta) / current_price if current_price > 0 else 0.0

            # Boost for significant savings
            score = alt.score * (
                1.0 + min(savings_pct * 0.5, 0.4)
            )  # Up to 40% boost for big savings

            reasoning = f"budget alternative (${current_price:.2f} → ${alt_price:.2f}, save ${abs(price_delta):.2f})"

            downgrades.append(
                CardDowngrade(
                    card=alt.card,
                    score=score,
                    price_delta=price_delta,
                    reasoning=reasoning,
                )
            )

        # Sort by score
        downgrades.sort(key=lambda x: x.score, reverse=True)

        # Limit to top_k
        if len(downgrades) > top_k:
            downgrades = downgrades[:top_k]

        return downgrades


__all__ = [
    "CardAlternative",
    "CardDowngrade",
    "CardSynergy",
    "CardUpgrade",
    "ContextualCardDiscovery",
]
