"""
Deck refinement system - incremental improvements to decks.

This module provides:
- Add suggestions (what to add)
- Remove suggestions (what to remove)
- Replace suggestions (what to replace)
- Move suggestions (main ↔ sideboard)
- Explanation generation (why these suggestions?)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Literal, Optional

from ..similarity.fusion import WeightedLateFusion

try:
    from ..utils.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


@dataclass
class RefinementConstraints:
    """Constraints for deck refinement."""
    budget_max: Optional[float] = None
    format: Optional[str] = None
    archetype: Optional[str] = None
    preserve_roles: bool = True
    max_suggestions: int = 10


@dataclass
class CardSuggestion:
    """A single card suggestion with reasoning."""
    card: str
    action: Literal["add", "remove", "replace_with", "move_to_sideboard", "move_to_main"]
    score: float
    reasoning: str
    impact: dict[str, Any]
    target: Optional[str] = None  # For replace/move actions


@dataclass
class DeckStats:
    """Deck statistics for before/after comparison."""
    size: int
    archetype_coverage: float
    role_coverage: dict[str, float]
    budget_total: Optional[float] = None


class DeckRefiner:
    """Refines decks with contextual, role-aware suggestions."""
    
    def __init__(
        self,
        fusion: WeightedLateFusion,
        price_fn: Optional[Callable[[str], Optional[float]]] = None,
        tag_set_fn: Optional[Callable[[str], set[str]]] = None,
    ):
        self.fusion = fusion
        self.price_fn = price_fn
        self.tag_set_fn = tag_set_fn
    
    def suggest_additions(
        self,
        game: Literal["magic", "yugioh", "pokemon"],
        deck: dict,
        constraints: RefinementConstraints,
    ) -> list[CardSuggestion]:
        """
        Suggest cards to add to the deck.
        
        Strategy:
        1. Identify role gaps (missing removal, threats, etc.)
        2. Find archetype staples not in deck
        3. Use similarity to find synergistic cards
        4. Filter by budget/format constraints
        5. Limit to top-k with clear reasoning
        """
        from ..deck_building.deck_completion import suggest_additions as completion_suggest_additions
        from ..data.card_resolver import CardResolver
        
        resolver = CardResolver()
        suggestions: list[CardSuggestion] = []
        
        # Get current deck cards
        # Handle two deck formats:
        # 1. partitions format: {"partitions": [{"name": "Main", "cards": [...]}]}
        # 2. cards format: {"cards": [{"name": "...", "partition": "Main", ...}]}
        main_partition = "Main" if game == "magic" else "Main Deck"
        current_cards: set[str] = set()
        
        # Try partitions format first
        for p in deck.get("partitions", []) or []:
            if p.get("name") == main_partition:
                for c in p.get("cards", []) or []:
                    # Handle both dict format {"name": "...", "count": ...} and string format
                    if isinstance(c, dict):
                        card_name = str(c.get("name", ""))
                    else:
                        card_name = str(c)
                    if card_name:
                        current_cards.add(resolver.canonical(card_name))
        
        # Try cards format (cards with partition field)
        if not current_cards and "cards" in deck:
            for c in deck["cards"]:
                if isinstance(c, dict):
                    partition = c.get("partition", "")
                    # Handle various partition name formats
                    # Magic: "Main" or "Main Deck" both acceptable
                    # Yu-Gi-Oh/Pokemon: "Main Deck" 
                    partition_lower = partition.lower().strip()
                    if game == "magic":
                        # Accept "Main" or "Main Deck" for Magic
                        if partition_lower in ("main", "main deck"):
                            card_name = str(c.get("name", ""))
                            if card_name:
                                current_cards.add(resolver.canonical(card_name))
                    else:
                        # For other games, use exact match
                        if partition == main_partition or partition_lower == main_partition.lower():
                            card_name = str(c.get("name", ""))
                            if card_name:
                                current_cards.add(resolver.canonical(card_name))
        
        logger.debug(f"Found {len(current_cards)} cards in deck for {game}")
        if not current_cards:
            logger.warning(f"No cards found in deck for {game} - cannot generate suggestions")
            return suggestions
        
        # 1. Detect role gaps (if functional tags available)
        role_gaps = {}
        if self.tag_set_fn:
            role_gaps = _detect_role_gaps(deck, self.tag_set_fn)
        
        # 2. Find archetype staples not in deck
        archetype_staples_list: list[tuple[str, float]] = []
        if constraints.archetype:
            archetype_staples_list = _find_archetype_staples(
                constraints.archetype,
                constraints.format,
            )
            # Filter to cards not already in deck
            archetype_staples_list = [
                (card, rate) for card, rate in archetype_staples_list
                if resolver.canonical(card) not in current_cards
            ]
        
        # 3. Use fusion similarity for synergistic cards
        # Pick multiple representative cards from deck as seeds
        seed_cards = list(current_cards)[:5] if current_cards else []
        fusion_suggestions: list[tuple[str, float]] = []
        
        logger.debug(f"Using {len(seed_cards)} seed cards for fusion: {seed_cards[:3]}")
        
        if seed_cards and self.fusion:
            try:
                # Aggregate suggestions from multiple seed cards
                candidate_scores: dict[str, float] = {}
                for seed_card in seed_cards:
                    try:
                        # Get top candidates from fusion using completion task type
                        candidates = self.fusion.similar(seed_card, k=constraints.max_suggestions * 3, task_type="completion")
                        for card, score in candidates:
                            canonical_card = resolver.canonical(card)
                            if canonical_card not in current_cards:
                                # Aggregate scores (max or average)
                                candidate_scores[canonical_card] = max(
                                    candidate_scores.get(canonical_card, 0.0),
                                    float(score)
                                )
                    except Exception:
                        # Card might not be in embeddings, skip
                        continue
                
                # Convert to list of tuples
                fusion_suggestions = [
                    (card, score) for card, score in candidate_scores.items()
                ]
                # Sort by score descending
                fusion_suggestions.sort(key=lambda x: x[1], reverse=True)
                logger.debug(f"Generated {len(fusion_suggestions)} fusion suggestions")
            except Exception as e:
                from ..utils.logging_config import log_exception
                log_exception(logger, "Failed to get fusion suggestions", e, level="warning", include_context=True)
                pass
        
        # Combine and score suggestions
        scored: dict[str, tuple[float, str]] = {}
        
        # Boost archetype staples
        for card, inclusion_rate in archetype_staples_list[:constraints.max_suggestions]:
            score = inclusion_rate * 1.5  # Boost archetype staples
            reason = f"Archetype staple ({inclusion_rate:.0%} inclusion in {constraints.archetype})"
            scored[card] = (score, reason)
        
        # Boost cards that fill role gaps (if functional tags available)
        if role_gaps and self.tag_set_fn:
            for card, score in fusion_suggestions:
                card_tags = self.tag_set_fn(resolver.canonical(card))
                for role, gap_size in role_gaps.items():
                    if role in card_tags:
                        boost = 1.0 + (gap_size / 10.0) * 0.5
                        new_score = score * boost
                        reason = f"Fills {role} gap (deck has {gap_size} too few {role} cards)"
                        if card in scored:
                            old_score, old_reason = scored[card]
                            if new_score > old_score:
                                scored[card] = (new_score, reason)
                        else:
                            scored[card] = (new_score, reason)
        
        # Add remaining fusion suggestions (even if no role gaps or archetype)
        # This ensures we always have some suggestions - CRITICAL FALLBACK
        if not scored and fusion_suggestions:
            # If we have no scored suggestions yet, use fusion as primary source
            for card, score in fusion_suggestions[:constraints.max_suggestions]:
                scored[card] = (score, "Synergistic with deck")
        else:
            # Add fusion suggestions that weren't already scored
            for card, score in fusion_suggestions[:constraints.max_suggestions * 2]:
                if card not in scored:
                    scored[card] = (score, "Synergistic with deck")
        
        # Filter by budget
        if constraints.budget_max and self.price_fn:
            filtered: dict[str, tuple[float, str]] = {}
            for card, (score, reason) in scored.items():
                price = self.price_fn(card)
                if price is None or price <= constraints.budget_max:
                    filtered[card] = (score, reason)
            scored = filtered
        
        # Convert to CardSuggestion objects
        sorted_scored = sorted(scored.items(), key=lambda x: x[1][0], reverse=True)[:constraints.max_suggestions]
        logger.debug(f"Final scored suggestions: {len(sorted_scored)} (from {len(scored)} total scored)")
        
        for card, (score, reason) in sorted_scored:
            suggestions.append(CardSuggestion(
                card=card,
                action="add",
                score=score,
                reasoning=reason,
                impact={"role_gaps_filled": role_gaps, "archetype_match": constraints.archetype or "none"},
            ))
        
        if not suggestions:
            logger.warning(f"No suggestions generated - scored={len(scored)}, fusion={len(fusion_suggestions)}, archetype={len(archetype_staples_list)}")
        
        return suggestions
    
    def suggest_removals(
        self,
        game: Literal["magic", "yugioh", "pokemon"],
        deck: dict,
        constraints: RefinementConstraints,
    ) -> list[CardSuggestion]:
        """
        Suggest cards to remove from the deck.
        
        Strategy:
        1. Identify weak cards (low archetype match)
        2. Identify redundant cards (multiple filling same role)
        3. Consider format legality
        4. Preserve role coverage if requested
        """
        from ..deck_building.deck_completion import suggest_removals as completion_suggest_removals
        from ..data.card_resolver import CardResolver
        
        resolver = CardResolver()
        
        # Use completion module's suggest_removals which is already implemented
        archetype_staples: Optional[dict[str, dict[str, float]]] = None
        if constraints.archetype and hasattr(self.fusion, 'archetype_staples'):
            archetype_staples = self.fusion.archetype_staples
        
        removal_tuples = completion_suggest_removals(
            game=game,
            deck=deck,
            candidate_fn=lambda card, k: [],  # Not needed for removals
            archetype=constraints.archetype,
            archetype_staples=archetype_staples,
            tag_set_fn=self.tag_set_fn,
            preserve_roles=constraints.preserve_roles,
            max_suggestions=constraints.max_suggestions,
        )
        
        # Convert to CardSuggestion objects
        suggestions: list[CardSuggestion] = []
        for card, score, reason in removal_tuples:
            suggestions.append(CardSuggestion(
                card=card,
                action="remove",
                score=score,
                reasoning=reason,
                impact={"preserves_roles": constraints.preserve_roles},
            ))
        
        return suggestions
    
    def suggest_replacements(
        self,
        game: Literal["magic", "yugioh", "pokemon"],
        deck: dict,
        card: str,
        constraints: RefinementConstraints,
    ) -> list[CardSuggestion]:
        """
        Suggest replacements for a specific card.
        
        Strategy:
        1. Find functional alternatives (similar role)
        2. Consider upgrades (better, more expensive)
        3. Consider downgrades (worse, cheaper)
        4. Maintain role coverage
        """
        from ..deck_building.deck_completion import suggest_replacements as completion_suggest_replacements
        from ..data.card_resolver import CardResolver
        
        resolver = CardResolver()
        
        # Create candidate function from fusion using substitution task type
        def candidate_fn(query_card: str, k: int) -> list[tuple[str, float]]:
            if not self.fusion:
                return []
            try:
                return self.fusion.similar(query_card, k=k, task_type="substitution")
            except Exception:
                return []
        
        archetype_staples: Optional[dict[str, dict[str, float]]] = None
        if constraints.archetype and hasattr(self.fusion, 'archetype_staples'):
            archetype_staples = self.fusion.archetype_staples
        
        # Determine if upgrade or downgrade based on budget
        current_price = self.price_fn(card) if self.price_fn else None
        upgrade = False
        downgrade = False
        if constraints.budget_max and current_price:
            # If budget is tight, prefer downgrades
            if constraints.budget_max < current_price * 2:
                downgrade = True
            else:
                upgrade = True
        
        replacement_tuples = completion_suggest_replacements(
            game=game,
            deck=deck,
            card=card,
            candidate_fn=candidate_fn,
            top_k=constraints.max_suggestions,
            price_fn=self.price_fn,
            max_unit_price=constraints.budget_max,
            tag_set_fn=self.tag_set_fn,
            archetype=constraints.archetype,
            archetype_staples=archetype_staples,
            upgrade=upgrade,
            downgrade=downgrade,
        )
        
        # Convert to CardSuggestion objects
        suggestions: list[CardSuggestion] = []
        for replacement, score, reason in replacement_tuples:
            suggestions.append(CardSuggestion(
                card=replacement,
                action="replace_with",
                target=card,
                score=score,
                reasoning=reason,
                impact={"upgrade": upgrade, "downgrade": downgrade},
            ))
        
        return suggestions
    
    def suggest_moves(
        self,
        game: Literal["magic", "yugioh", "pokemon"],
        deck: dict,
        constraints: RefinementConstraints,
    ) -> list[CardSuggestion]:
        """
        Suggest moving cards between main and sideboard.
        
        Strategy:
        1. Identify main deck cards that are sideboard material (narrow answers, meta calls)
        2. Identify sideboard cards that should be main (broad answers, format staples)
        3. Consider format-specific patterns
        """
        from ..data.card_resolver import CardResolver
        
        resolver = CardResolver()
        suggestions: list[CardSuggestion] = []
        
        main_partition = "Main" if game == "magic" else "Main Deck"
        sideboard_partition = "Sideboard" if game == "magic" else "Side Deck"
        
        # Get cards in each partition
        main_cards: dict[str, int] = {}  # card -> count
        sideboard_cards: dict[str, int] = {}
        
        for p in deck.get("partitions", []) or []:
            if p.get("name") == main_partition:
                for card_obj in p.get("cards", []) or []:
                    card_name = resolver.canonical(str(card_obj.get("name", "")))
                    main_cards[card_name] = int(card_obj.get("count", 1))
            elif p.get("name") == sideboard_partition:
                for card_obj in p.get("cards", []) or []:
                    card_name = resolver.canonical(str(card_obj.get("name", "")))
                    sideboard_cards[card_name] = int(card_obj.get("count", 1))
        
        # 1. Identify main deck cards that should be sideboard
        # Sideboard material: narrow answers, meta-specific hate, cards that are too slow for main
        if self.tag_set_fn:
            for card, count in main_cards.items():
                tags = self.tag_set_fn(card)
                score = 0.0
                reason_parts = []
                
                # Narrow hate cards (graveyard hate, artifact hate, etc.) should be sideboard
                narrow_hate_tags = {"graveyard_hate", "artifact_hate", "enchantment_hate", "land_hate"}
                if tags & narrow_hate_tags:
                    score = 0.7
                    reason_parts.append("narrow hate card (better in sideboard)")
                
                # High CMC cards that are situational (if we had CMC info)
                # For now, use tag heuristics
                if "board_wipe" in tags and count > 2:
                    score = max(score, 0.6)
                    reason_parts.append("too many board wipes for main (move extras to sideboard)")
                
                if score > 0.0:
                    suggestions.append(CardSuggestion(
                        card=card,
                        action="move_to_sideboard",
                        score=score,
                        reasoning=", ".join(reason_parts) if reason_parts else "better suited for sideboard",
                        impact={"current_location": "main", "target_location": "sideboard"},
                    ))
        
        # 2. Identify sideboard cards that should be main
        # Main deck material: broad answers, format staples, core engine pieces
        if self.tag_set_fn:
            for card, count in sideboard_cards.items():
                tags = self.tag_set_fn(card)
                score = 0.0
                reason_parts = []
                
                # Broad answers should be main
                broad_answer_tags = {"removal", "counter", "card_draw", "threat"}
                if tags & broad_answer_tags:
                    score = 0.8
                    reason_parts.append("broad answer (should be in main)")
                
                # Format staples should be main
                if constraints.archetype and hasattr(self.fusion, 'archetype_staples'):
                    if self.fusion.archetype_staples:
                        card_staples = self.fusion.archetype_staples.get(card, {})
                        if constraints.archetype in card_staples:
                            inclusion_rate = card_staples[constraints.archetype]
                            if inclusion_rate > 0.7:  # High inclusion rate
                                score = max(score, 0.9)
                                reason_parts.append(f"archetype staple ({inclusion_rate:.0%} inclusion)")
                
                if score > 0.0:
                    suggestions.append(CardSuggestion(
                        card=card,
                        action="move_to_main",
                        score=score,
                        reasoning=", ".join(reason_parts) if reason_parts else "should be in main deck",
                        impact={"current_location": "sideboard", "target_location": "main"},
                    ))
        
        # Sort by score (highest = most important to move)
        suggestions.sort(key=lambda x: x.score, reverse=True)
        
        # Limit to max_suggestions
        if len(suggestions) > constraints.max_suggestions:
            suggestions = suggestions[:constraints.max_suggestions]
        
        return suggestions


def _detect_role_gaps(
    deck: dict,
    tag_set_fn: Optional[Callable[[str], set[str]]],
) -> dict[str, int]:
    """
    Detect functional role gaps in deck.
    
    Returns dict mapping role -> gap size (target - current).
    """
    if not tag_set_fn:
        return {}
    
    from ..data.card_resolver import CardResolver
    resolver = CardResolver()
    
    main_partition = "Main"  # Default to MTG, adjust if needed
    role_counts: dict[str, int] = {}
    
    # Count cards by functional role
    # Handle partitions format
    for p in deck.get("partitions", []) or []:
        if p.get("name") != main_partition:
            continue
        for card_obj in p.get("cards", []) or []:
            if isinstance(card_obj, dict):
                card_name = resolver.canonical(str(card_obj.get("name", "")))
            else:
                card_name = resolver.canonical(str(card_obj))
            tags = tag_set_fn(card_name)
            count = int(card_obj.get("count", 1)) if isinstance(card_obj, dict) else 1
            for role in ["removal", "threat", "card_draw", "ramp", "counter", "tutor"]:
                if role in tags:
                    role_counts[role] = role_counts.get(role, 0) + count
    
    # Handle cards format (cards with partition field)
    if "cards" in deck:
        for card_obj in deck["cards"]:
            if isinstance(card_obj, dict):
                partition = card_obj.get("partition", "")
                if partition == main_partition:
                    card_name = resolver.canonical(str(card_obj.get("name", "")))
                    tags = tag_set_fn(card_name)
                    count = int(card_obj.get("count", 1))
                    for role in ["removal", "threat", "card_draw", "ramp", "counter", "tutor"]:
                        if role in tags:
                            role_counts[role] = role_counts.get(role, 0) + count
    
    # Identify gaps (roles with low counts)
    role_targets = {
        "removal": 10,
        "threat": 14,
        "card_draw": 6,
        "ramp": 4,
        "counter": 6,
        "tutor": 2,
    }
    
    gaps: dict[str, int] = {}
    for role, target in role_targets.items():
        current = role_counts.get(role, 0)
        if current < target:
            gaps[role] = target - current
    
    return gaps


def _find_archetype_staples(
    archetype: str,
    format: Optional[str],
) -> list[tuple[str, float]]:
    """
    Find archetype staples with inclusion rates.
    
    Returns list of (card, inclusion_rate) tuples.
    """
    from ..utils.paths import PATHS
    import json
    from pathlib import Path
    
    # Try to load from signals directory
    signals_dir = PATHS.data / "signals"
    archetype_staples_path = signals_dir / "archetype_staples.json"
    
    if not archetype_staples_path.exists():
        # Fallback to computed location
        archetype_staples_path = PATHS.processed / "archetype_staples.json"
    
    if not archetype_staples_path.exists():
        return []
    
    try:
        with open(archetype_staples_path) as f:
            staples_data = json.load(f)
        
        # Extract cards for this archetype
        results: list[tuple[str, float]] = []
        for card, archetypes in staples_data.items():
            if archetype in archetypes:
                inclusion_rate = archetypes[archetype]
                results.append((card, inclusion_rate))
        
        # Sort by inclusion rate (highest first)
        results.sort(key=lambda x: x[1], reverse=True)
        return results
    except Exception:
        return []


def _generate_explanation(
    card: str,
    action: str,
    reason_type: str,
    context: dict[str, Any],
) -> str:
    """
    Generate human-readable explanation for suggestion.
    
    Templates:
    - "Archetype staple - appears in {rate}% of {archetype} decks"
    - "Fills {role} gap - deck currently has {count} {role} cards"
    - "Budget alternative to {target} - similar effect, ${price} cheaper"
    - "Synergistic with {synergy_card} - commonly played together"
    """
    if reason_type == "archetype_staple":
        rate = context.get("inclusion_rate", 0.0)
        archetype = context.get("archetype", "this archetype")
        return f"Archetype staple - appears in {rate:.0%} of {archetype} decks"
    
    elif reason_type == "role_gap":
        role = context.get("role", "role")
        gap_size = context.get("gap_size", 0)
        return f"Fills {role} gap - deck needs {gap_size} more {role} cards"
    
    elif reason_type == "budget_alternative":
        target = context.get("target", "target card")
        price_diff = context.get("price_diff", 0.0)
        return f"Budget alternative to {target} - similar effect, ${price_diff:.2f} cheaper"
    
    elif reason_type == "upgrade":
        target = context.get("target", "target card")
        price_diff = context.get("price_diff", 0.0)
        return f"Upgrade from {target} - better effect, ${price_diff:.2f} more expensive"
    
    elif reason_type == "synergy":
        synergy_card = context.get("synergy_card", "deck cards")
        return f"Synergistic with {synergy_card} - commonly played together"
    
    else:
        return f"{action} {card} - {reason_type}"


# Placeholder for future implementation
__all__ = [
    "DeckRefiner",
    "RefinementConstraints",
    "CardSuggestion",
    "DeckStats",
]

