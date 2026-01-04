#!/usr/bin/env python3
"""
Beam search for deck completion.

Replaces greedy algorithm with beam search for better multi-step optimization.
Uses multi-objective scoring: similarity + coverage + mana curve fit.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from typing import Callable, Literal, Optional

from .deck_completion import (
    CompletionConfig,
    CandidateFn,
    TagSetFn,
    CMCFn,
    _main_partition_name,
    _current_size,
    _cards_in_partition,
    _legal_add,
)
try:
    from .deck_patch import DeckPatch, apply_deck_patch
except ImportError:
    DeckPatch = None
    apply_deck_patch = None

logger = logging.getLogger("decksage.beam_search")


@dataclass
class BeamState:
    """State in beam search."""
    deck: dict
    score: float
    step: int
    path: list[str]  # Cards added so far


def compute_coverage_bonus(
    deck: dict,
    tag_set_fn: TagSetFn | None,
    main_partition: str,
    coverage_weight: float,
) -> float:
    """
    Compute bonus for adding new functional tags.
    
    Args:
        deck: Current deck state
        tag_set_fn: Function to get tags for a card
        main_partition: Name of main partition
        coverage_weight: Weight for coverage bonus
    
    Returns:
        Coverage bonus score
    """
    if tag_set_fn is None or coverage_weight == 0:
        return 0.0
    
    # Get all tags in current deck
    deck_tags: set[str] = set()
    for p in deck.get("partitions", []) or []:
        if p.get("name") != main_partition:
            continue
        for c in p.get("cards", []) or []:
            card_name = c.get("name", "")
            if card_name:
                deck_tags |= tag_set_fn(card_name)
    
    # Bonus proportional to number of unique tags
    return len(deck_tags) * coverage_weight * 0.01


def compute_curve_bonus(
    deck: dict,
    cmc_fn: CMCFn | None,
    curve_target: Optional[dict[int, float]],
    main_partition: str,
    curve_weight: float,
) -> float:
    """
    Compute bonus for matching target mana curve.
    
    Args:
        deck: Current deck state
        cmc_fn: Function to get CMC for a card
        curve_target: Target curve (CMC -> fraction of deck)
        main_partition: Name of main partition
        curve_weight: Weight for curve bonus
    
    Returns:
        Curve fit bonus score
    """
    if cmc_fn is None or curve_target is None or curve_weight == 0:
        return 0.0
    
    # Compute current curve
    current_curve: dict[int, int] = {}
    total_cards = 0
    
    for p in deck.get("partitions", []) or []:
        if p.get("name") != main_partition:
            continue
        for c in p.get("cards", []) or []:
            card_name = c.get("name", "")
            count = c.get("count", 0)
            cmc = cmc_fn(card_name)
            if cmc is not None:
                current_curve[cmc] = current_curve.get(cmc, 0) + count
                total_cards += count
    
    if total_cards == 0:
        return 0.0
    
    # Compare to target
    bonus = 0.0
    for cmc, target_frac in curve_target.items():
        current_frac = current_curve.get(cmc, 0) / total_cards
        # Bonus for being closer to target
        diff = abs(current_frac - target_frac)
        bonus += (1.0 - diff) * curve_weight * 0.1
    
    return bonus


def beam_search_completion(
    initial_deck: dict,
    candidate_fn: CandidateFn,
    config: CompletionConfig,
    *,
    beam_width: int = 3,
    tag_set_fn: TagSetFn | None = None,
    cmc_fn: CMCFn | None = None,
    curve_target: dict[int, float] | None = None,
) -> dict:
    """
    Complete deck using beam search.
    
    Args:
        initial_deck: Starting deck state
        candidate_fn: Function to generate candidates (card, score) tuples
        config: Completion configuration
        beam_width: Number of beams to maintain
        tag_set_fn: Optional function to get functional tags
        cmc_fn: Optional function to get CMC
        curve_target: Optional target mana curve
    
    Returns:
        Completed deck
    """
    main_partition = _main_partition_name(config.game)
    target_size = config.target_main_size
    
    # Initialize beam with initial deck
    beam = [BeamState(
        deck=initial_deck,
        score=0.0,
        step=0,
        path=[],
    )]
    
    for step in range(config.max_steps):
        next_beam: list[BeamState] = []
        
        for state in beam:
            current_size = _current_size(state.deck, main_partition)
            
            # Check if done
            if target_size is not None and current_size >= target_size:
                next_beam.append(state)
                continue
            
            # Generate candidates - need seed card from deck
            seed_card = None
            main_partition = _main_partition_name(config.game)
            for p in state.deck.get("partitions", []) or []:
                if p.get("name") == main_partition:
                    cards = p.get("cards", []) or []
                    if cards:
                        seed_card = cards[0].get("name")
                        break
            
            if not seed_card:
                continue
            
            try:
                candidates = candidate_fn(seed_card, config.top_k_per_gap)
            except Exception as e:
                logger.warning(f"Error generating candidates: {e}")
                continue
            
            # Expand each candidate
            for card, sim_score in candidates:
                # Check legality
                if not _legal_add(config.game, state.deck, card):
                    continue
                
                # Create patch to add card
                if DeckPatch is None or apply_deck_patch is None:
                    logger.warning("DeckPatch not available, skipping beam search")
                    continue
                
                patch = DeckPatch(ops=[{
                    "op": "add_card",
                    "partition": main_partition,
                    "card": card,
                    "count": 1,
                }])
                
                # Apply patch
                result = apply_deck_patch(config.game, state.deck, patch)
                
                if not result.is_valid or not result.deck:
                    continue
                
                new_deck = result.deck
                
                # Compute multi-objective score
                new_score = state.score + sim_score
                
                # Coverage bonus
                new_score += compute_coverage_bonus(
                    new_deck,
                    tag_set_fn,
                    main_partition,
                    config.coverage_weight,
                )
                
                # Curve bonus
                new_score += compute_curve_bonus(
                    new_deck,
                    cmc_fn,
                    curve_target,
                    main_partition,
                    0.1,  # curve_weight (could be config param)
                )
                
                # Create new state
                next_beam.append(BeamState(
                    deck=new_deck,
                    score=new_score,
                    step=step + 1,
                    path=state.path + [card],
                ))
        
        if not next_beam:
            break
        
        # Sort by score and keep top-k
        next_beam.sort(key=lambda s: s.score, reverse=True)
        beam = next_beam[:beam_width]
        
        # Check if any beam is complete
        if target_size is not None:
            complete = [
                s for s in beam
                if _current_size(s.deck, main_partition) >= target_size
            ]
            if complete:
                # Return best complete deck
                return complete[0].deck
    
    # Return best deck from final beam
    if beam:
        return beam[0].deck
    
    # Fallback to initial deck
    return initial_deck


__all__ = ["beam_search_completion", "BeamState"]







