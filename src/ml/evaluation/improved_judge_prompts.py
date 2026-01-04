#!/usr/bin/env python3
"""
Improved Judge Prompts

Based on meta-evaluation findings, these are improved prompts that:
1. Measure what we actually care about
2. Have clear calibration
3. Include all relevant criteria
4. Are aligned with actual goals
5. Include all expanded dimensions (deck balance, power level, availability, etc.)
6. Include temporal and context-aware evaluation (first-class concern)
"""

from .expanded_judge_criteria import (
    EXPANDED_CONTEXTUAL_DISCOVERY_JUDGE_PROMPT,
    EXPANDED_DECK_MODIFICATION_JUDGE_PROMPT,
    EXPANDED_SIMILARITY_JUDGE_PROMPT,
)


# Use expanded prompts as the default
DECK_MODIFICATION_JUDGE_PROMPT = EXPANDED_DECK_MODIFICATION_JUDGE_PROMPT
SIMILARITY_JUDGE_PROMPT = EXPANDED_SIMILARITY_JUDGE_PROMPT
CONTEXTUAL_DISCOVERY_JUDGE_PROMPT = EXPANDED_CONTEXTUAL_DISCOVERY_JUDGE_PROMPT

# All prompts now use expanded versions from expanded_judge_criteria.py
# See that file for full prompt definitions

# Calibration Test Cases (expanded to include temporal and other dimensions)
CALIBRATION_TEST_CASES = [
    {
        "name": "perfect_archetype_staple",
        "scenario": "Burn deck, suggest Lightning Bolt (95% inclusion, fills removal gap, legal, fits budget)",
        "expected": {
            "relevance": 4,
            "explanation_quality": 4,
            "archetype_match": 4,
            "role_fit": 4,
            "deck_balance_impact": 3,
            "power_level_match": 4,
            "card_availability": 4,
            "temporal_context_appropriateness": 4,
        },
        "tests": "Ideal case recognition",
    },
    {
        "name": "wrong_archetype",
        "scenario": "Burn deck, suggest Counterspell (blue control, doesn't fit red aggro)",
        "expected": {
            "relevance": 0,
            "archetype_match": 0,
        },
        "tests": "Clear mismatch recognition",
    },
    {
        "name": "budget_violation",
        "scenario": "Budget deck (max $2), suggest $10 card (fits archetype but exceeds budget)",
        "expected": {
            "relevance": 0,  # MUST be 0 if budget violated
            "cost_effectiveness": 0,
        },
        "tests": "Budget constraint enforcement",
    },
    {
        "name": "format_illegal",
        "scenario": "Modern deck, suggest Chain Lightning (Legacy-only card)",
        "expected": {
            "relevance": 0,  # MUST be 0 if illegal
            "temporal_context_appropriateness": 0,
            "ban_timeline_awareness": 0,
        },
        "tests": "Format legality enforcement",
    },
    {
        "name": "synergy_awareness",
        "scenario": "Goblin deck, suggest removing Goblin Guide (tribal synergy)",
        "expected": {
            "relevance": 1,  # Low - breaks synergy
            "theme_consistency": 1,
        },
        "tests": "Synergy awareness in removal",
    },
    {
        "name": "temporal_issue_banned_soon_after",
        "scenario": "Recommendation made in Sept 2019 for Oko, Thief of Crowns (banned in Oct 2019)",
        "expected": {
            "temporal_context_appropriateness": 1,  # Poor - banned soon after
            "ban_timeline_awareness": 0,  # No awareness of upcoming ban
            "meta_shift_awareness": 0,  # Didn't account for meta shift
        },
        "tests": "Temporal awareness - ban timeline",
    },
    {
        "name": "price_volatility_spike",
        "scenario": "Recommendation made during price spike (card doubled in price week after)",
        "expected": {
            "price_volatility_awareness": 0,  # Didn't account for volatility
            "card_availability": 1,  # Poor availability due to spike
            "cost_effectiveness": 1,  # Poor value due to spike
        },
        "tests": "Price volatility awareness",
    },
]


def get_improved_prompt(task: str) -> str:
    """Get improved prompt for a task."""
    prompts = {
        "add": DECK_MODIFICATION_JUDGE_PROMPT,
        "remove": DECK_MODIFICATION_JUDGE_PROMPT,
        "replace": DECK_MODIFICATION_JUDGE_PROMPT,
        "contextual": CONTEXTUAL_DISCOVERY_JUDGE_PROMPT,
        "similarity": SIMILARITY_JUDGE_PROMPT,
    }
    return prompts.get(task, DECK_MODIFICATION_JUDGE_PROMPT)


__all__ = [
    "CALIBRATION_TEST_CASES",
    "CONTEXTUAL_DISCOVERY_JUDGE_PROMPT",
    "DECK_MODIFICATION_JUDGE_PROMPT",
    "SIMILARITY_JUDGE_PROMPT",
    "get_improved_prompt",
]
