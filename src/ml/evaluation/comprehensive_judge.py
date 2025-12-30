#!/usr/bin/env python3
"""
Comprehensive Judge System

Integrates all evaluation dimensions including temporal context.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from pydantic import BaseModel, Field
    from pydantic_ai import Agent
    HAS_PYDANTIC_AI = True
except ImportError:
    HAS_PYDANTIC_AI = False
    BaseModel = None
    Field = None

from .expanded_judge_criteria import EXPANDED_DECK_MODIFICATION_JUDGE_PROMPT
from .temporal_evaluation_dimensions import (
    TemporalContext,
    TemporalEvaluation,
    evaluate_temporal_appropriateness,
)
from .deck_balance_calculator import (
    DeckBalance,
    calculate_deck_balance,
    calculate_balance_impact,
)


class ComprehensiveJudgment(BaseModel):
    """Comprehensive judgment including all dimensions."""
    # Core dimensions
    relevance: int = Field(ge=0, le=4)
    explanation_quality: int = Field(ge=0, le=4)
    archetype_match: int | None = Field(None, ge=0, le=4)
    role_fit: int | None = Field(None, ge=0, le=4)
    
    # Missing dimensions
    deck_balance_impact: int = Field(ge=0, le=4)
    power_level_match: int = Field(ge=0, le=4)
    card_availability: int = Field(ge=0, le=4)
    cost_effectiveness: int | None = Field(None, ge=0, le=4)
    meta_positioning: int | None = Field(None, ge=0, le=4)
    consistency_improvement: int | None = Field(None, ge=0, le=4)
    sideboard_appropriateness: int | None = Field(None, ge=0, le=4)
    theme_consistency: int | None = Field(None, ge=0, le=4)
    
    # Temporal dimensions
    temporal_context_appropriate: int = Field(ge=0, le=4)
    meta_shift_awareness: int = Field(ge=0, le=4)
    price_volatility_awareness: int = Field(ge=0, le=4)
    ban_timeline_awareness: int = Field(ge=0, le=4)
    format_rotation_awareness: int | None = Field(None, ge=0, le=4)
    
    # Reasoning
    reasoning: str
    temporal_issues: list[str] = Field(default_factory=list)
    context_changes_since: list[str] = Field(default_factory=list)


def make_comprehensive_judge_agent() -> Agent | None:
    """Create comprehensive judge agent with all dimensions."""
    if not HAS_PYDANTIC_AI:
        return None
    
    from ..utils.pydantic_ai_helpers import make_agent as _make_agent
    from ..utils.pydantic_ai_helpers import get_default_model
    
    model = get_default_model("judge")
    
    # Use expanded prompt that includes all dimensions
    system_prompt = EXPANDED_DECK_MODIFICATION_JUDGE_PROMPT
    
    return _make_agent(model, ComprehensiveJudgment, system_prompt)


def judge_suggestion_comprehensively(
    agent: Agent,
    deck: dict[str, Any],
    suggested_card: str,
    explanation: str,
    recommendation_timestamp: datetime | None = None,
    temporal_context: TemporalContext | None = None,
    current_state: dict[str, Any] | None = None,
    archetype: str | None = None,
    format: str | None = None,
    role_gap: str | None = None,
    budget_max: float | None = None,
    game: str = "magic",
    cmc_fn: callable | None = None,
    color_fn: callable | None = None,
) -> ComprehensiveJudgment:
    """
    Judge a suggestion comprehensively including all dimensions.
    
    Args:
        agent: LLM judge agent
        deck: Current deck
        suggested_card: Card being suggested
        explanation: Explanation for suggestion
        recommendation_timestamp: When recommendation was made (for temporal evaluation)
        temporal_context: Temporal context at recommendation time
        current_state: Current game state (for comparison)
        archetype: Deck archetype
        format: Format
        role_gap: Role gap being filled
        budget_max: Budget constraint
        game: Game type
        cmc_fn: Function to get CMC
        color_fn: Function to get colors
    
    Returns:
        ComprehensiveJudgment with all dimensions
    """
    # Calculate deck balance impact
    deck_before = calculate_deck_balance(deck, game, cmc_fn, color_fn)
    
    # Simulate adding card to deck
    deck_after_dict = json.loads(json.dumps(deck))  # Deep copy
    main_partition = None
    for p in deck_after_dict.get("partitions", []) or []:
        if p.get("name") in ("Main", "Main Deck"):
            main_partition = p
            break
    
    if main_partition:
        cards = main_partition.get("cards", []) or []
        # Add suggested card
        cards.append({"name": suggested_card, "count": 1})
        main_partition["cards"] = cards
    
    deck_after = calculate_deck_balance(deck_after_dict, game, cmc_fn, color_fn)
    balance_impact = calculate_balance_impact(deck_before, deck_after)
    
    # Evaluate temporal appropriateness
    temporal_eval: TemporalEvaluation | None = None
    if recommendation_timestamp and temporal_context and current_state:
        temporal_eval = evaluate_temporal_appropriateness(
            {
                "card": suggested_card,
                "explanation": explanation,
                "budget_max": budget_max,
            },
            temporal_context,
            current_state,
        )
    
    # Build prompt for LLM judge
    prompt = f"""Evaluate this deck modification suggestion:

Deck: {json.dumps(deck, indent=2)[:500]}...
Suggested Card: {suggested_card}
Explanation: {explanation}
Archetype: {archetype or "Not specified"}
Format: {format or "Not specified"}
Role Gap: {role_gap or "Not specified"}
Budget Max: {budget_max or "Not specified"}

Deck Balance Impact: {balance_impact['impact_score']:.1f}/4.0
  - CMC improvement: {balance_impact['cmc_improvement']:.2f}
  - Land improvement: {balance_impact['land_improvement']:.1f}

"""
    
    if temporal_eval:
        prompt += f"""
Temporal Context:
  - Legal at recommendation time: {temporal_eval.legal_at_recommendation_time}
  - Price reasonable at time: {temporal_eval.price_reasonable_at_time}
  - Meta relevant at time: {temporal_eval.meta_relevant_at_time}
  - Temporal issues: {', '.join(temporal_eval.temporal_issues) if temporal_eval.temporal_issues else 'None'}
"""
    
    # Get LLM judgment
    if agent:
        try:
            result = agent.run_sync(prompt)
            judgment_data = result.data if hasattr(result, 'data') else result.output
            
            # Extract judgment
            judgment = ComprehensiveJudgment(**judgment_data)
            
            # Add calculated dimensions
            judgment.deck_balance_impact = int(balance_impact['impact_score'])
            
            if temporal_eval:
                judgment.temporal_context_appropriate = int(temporal_eval.quality_in_context)
                judgment.meta_shift_awareness = 4 if temporal_eval.accounts_for_meta_shifts else 2
                judgment.price_volatility_awareness = 4 if temporal_eval.accounts_for_price_volatility else 2
                judgment.ban_timeline_awareness = 4 if temporal_eval.accounts_for_ban_timeline else 2
                judgment.temporal_issues = temporal_eval.temporal_issues
                judgment.context_changes_since = temporal_eval.context_changes_since
            
            return judgment
        except Exception as e:
            # Fallback judgment
            pass
    
    # Fallback: return default judgment
    return ComprehensiveJudgment(
        relevance=2,
        explanation_quality=2,
        archetype_match=2 if archetype else None,
        role_fit=2 if role_gap else None,
        deck_balance_impact=int(balance_impact['impact_score']),
        power_level_match=2,
        card_availability=3,
        cost_effectiveness=2 if budget_max else None,
        meta_positioning=None,
        consistency_improvement=None,
        sideboard_appropriateness=None,
        theme_consistency=None,
        temporal_context_appropriate=3 if temporal_eval else 2,
        meta_shift_awareness=2,
        price_volatility_awareness=2,
        ban_timeline_awareness=2,
        format_rotation_awareness=None,
        reasoning="Fallback judgment - LLM evaluation failed",
        temporal_issues=temporal_eval.temporal_issues if temporal_eval else [],
        context_changes_since=temporal_eval.context_changes_since if temporal_eval else [],
    )


__all__ = [
    "ComprehensiveJudgment",
    "make_comprehensive_judge_agent",
    "judge_suggestion_comprehensively",
]

