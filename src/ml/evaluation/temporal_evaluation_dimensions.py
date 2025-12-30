#!/usr/bin/env python3
"""
Temporal Evaluation Dimensions

First-class temporal and context-aware evaluation criteria for recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class TemporalContext:
    """Temporal context for a recommendation."""
    recommendation_timestamp: datetime
    format_state_at_time: dict[str, Any]  # Ban list, legal sets, etc.
    meta_state_at_time: dict[str, Any]  # Top decks, meta share, etc.
    price_state_at_time: dict[str, float]  # Card prices at that time
    format_rotation_dates: list[datetime] | None  # Upcoming rotations
    recent_ban_list_changes: list[dict[str, Any]] | None  # Recent bans/unbans


@dataclass
class TemporalEvaluation:
    """Temporal evaluation of a recommendation."""
    # Temporal appropriateness
    temporal_context_appropriate: bool  # Was it appropriate for its time?
    legal_at_recommendation_time: bool  # Was it legal when recommended?
    price_reasonable_at_time: bool  # Was price reasonable then?
    meta_relevant_at_time: bool  # Was it meta-relevant then?
    
    # Temporal awareness
    accounts_for_meta_shifts: bool  # Does it account for current vs historical meta?
    accounts_for_price_volatility: bool  # Does it account for price changes?
    accounts_for_ban_timeline: bool  # Does it account for ban list changes?
    accounts_for_format_rotation: bool  # Does it account for rotation?
    
    # Context-dependent quality
    quality_in_context: float  # 0-4: Quality in its specific temporal context
    quality_if_recommended_now: float  # 0-4: Quality if recommended today
    
    # Temporal issues
    temporal_issues: list[str]  # Issues like "card was banned 2 weeks after recommendation"
    context_changes_since: list[str]  # What changed since recommendation (bans, price spikes, etc.)


def evaluate_temporal_appropriateness(
    recommendation: dict[str, Any],
    temporal_context: TemporalContext,
    current_state: dict[str, Any],
) -> TemporalEvaluation:
    """
    Evaluate if a recommendation was appropriate for its temporal context.
    
    Args:
        recommendation: The recommendation (should include timestamp, card, etc.)
        temporal_context: State of the game at recommendation time
        current_state: Current state of the game (for comparison)
    
    Returns:
        TemporalEvaluation with all temporal dimensions assessed
    """
    card = recommendation.get("card", "")
    rec_timestamp = temporal_context.recommendation_timestamp
    
    # Check legality at recommendation time
    legal_at_time = _check_legality_at_time(
        card,
        temporal_context.format_state_at_time,
    )
    
    # Check price at recommendation time
    price_at_time = temporal_context.price_state_at_time.get(card)
    price_reasonable = _check_price_reasonable(
        price_at_time,
        recommendation.get("budget_max"),
        card,
        rec_timestamp,
    )
    
    # Check meta relevance at time
    meta_relevant = _check_meta_relevance_at_time(
        card,
        temporal_context.meta_state_at_time,
    )
    
    # Check if accounts for meta shifts
    accounts_for_shifts = _check_meta_shift_awareness(
        recommendation,
        temporal_context.meta_state_at_time,
        current_state.get("meta_state", {}),
    )
    
    # Check price volatility awareness
    accounts_for_volatility = _check_price_volatility_awareness(
        card,
        temporal_context.price_state_at_time,
        current_state.get("price_state", {}),
        rec_timestamp,
    )
    
    # Check ban timeline awareness
    accounts_for_bans = _check_ban_timeline_awareness(
        card,
        temporal_context.format_state_at_time,
        temporal_context.recent_ban_list_changes or [],
    )
    
    # Check format rotation awareness
    accounts_for_rotation = _check_rotation_awareness(
        card,
        temporal_context.format_rotation_dates or [],
        rec_timestamp,
    )
    
    # Calculate quality in context
    quality_in_context = _calculate_quality_in_context(
        legal_at_time,
        price_reasonable,
        meta_relevant,
        accounts_for_shifts,
    )
    
    # Calculate quality if recommended now
    quality_now = _calculate_quality_if_recommended_now(
        card,
        current_state,
    )
    
    # Identify temporal issues
    temporal_issues = _identify_temporal_issues(
        card,
        legal_at_time,
        price_reasonable,
        meta_relevant,
        temporal_context,
        current_state,
    )
    
    # Identify context changes since recommendation
    context_changes = _identify_context_changes(
        card,
        temporal_context,
        current_state,
    )
    
    return TemporalEvaluation(
        temporal_context_appropriate=(
            legal_at_time and price_reasonable and meta_relevant
        ),
        legal_at_recommendation_time=legal_at_time,
        price_reasonable_at_time=price_reasonable,
        meta_relevant_at_time=meta_relevant,
        accounts_for_meta_shifts=accounts_for_shifts,
        accounts_for_price_volatility=accounts_for_volatility,
        accounts_for_ban_timeline=accounts_for_bans,
        accounts_for_format_rotation=accounts_for_rotation,
        quality_in_context=quality_in_context,
        quality_if_recommended_now=quality_now,
        temporal_issues=temporal_issues,
        context_changes_since=context_changes,
    )


def _check_legality_at_time(
    card: str,
    format_state: dict[str, Any],
) -> bool:
    """Check if card was legal at recommendation time."""
    ban_list = format_state.get("ban_list", [])
    return card not in ban_list


def _check_price_reasonable(
    price_at_time: float | None,
    budget_max: float | None,
    card: str,
    timestamp: datetime,
) -> bool:
    """Check if price was reasonable at recommendation time."""
    if price_at_time is None:
        return True  # Can't determine
    
    if budget_max is None:
        return True  # No budget constraint
    
    # Check if price was within budget
    if price_at_time > budget_max:
        return False
    
    # Check if price was stable (not spiking)
    # This would require price history - simplified for now
    return True


def _check_meta_relevance_at_time(
    card: str,
    meta_state: dict[str, Any],
) -> bool:
    """Check if card was meta-relevant at recommendation time."""
    top_decks = meta_state.get("top_decks", [])
    meta_share = meta_state.get("meta_share", {})
    
    # Check if card appears in top decks or has significant meta share
    card_meta_share = meta_share.get(card, 0.0)
    return card_meta_share > 0.01  # 1% meta share threshold


def _check_meta_shift_awareness(
    recommendation: dict[str, Any],
    meta_at_time: dict[str, Any],
    current_meta: dict[str, Any],
) -> bool:
    """Check if recommendation accounts for meta shifts."""
    # Compare meta state at recommendation time vs current
    # If meta shifted significantly, recommendation should reflect that
    card = recommendation.get("card", "")
    
    meta_share_then = meta_at_time.get("meta_share", {}).get(card, 0.0)
    meta_share_now = current_meta.get("meta_share", {}).get(card, 0.0)
    
    # If meta share changed significantly, recommendation might not account for shifts
    shift_magnitude = abs(meta_share_now - meta_share_then)
    
    # If shift is large (>10%), recommendation should account for it
    if shift_magnitude > 0.10:
        # Check if recommendation mentions meta shift or uses recent data
        explanation = recommendation.get("explanation", "").lower()
        recent_keywords = ["recent", "current", "now", "latest", "meta shift"]
        return any(kw in explanation for kw in recent_keywords)
    
    return True  # No significant shift


def _check_price_volatility_awareness(
    card: str,
    price_at_time: dict[str, float],
    current_price: dict[str, float],
    timestamp: datetime,
) -> bool:
    """Check if recommendation accounts for price volatility."""
    price_then = price_at_time.get(card)
    price_now = current_price.get(card)
    
    if price_then is None or price_now is None:
        return True  # Can't determine
    
    # Check if price changed significantly
    if price_then == 0:
        return True
    
    price_change_ratio = price_now / price_then
    
    # If price changed >2x, recommendation should account for volatility
    if price_change_ratio > 2.0 or price_change_ratio < 0.5:
        # Check if recommendation mentions price volatility
        # This would require checking recommendation text
        return False  # Likely doesn't account for volatility
    
    return True


def _check_ban_timeline_awareness(
    card: str,
    format_state: dict[str, Any],
    recent_bans: list[dict[str, Any]],
) -> bool:
    """Check if recommendation accounts for ban timeline."""
    # Check if card was recently banned/unbanned
    for ban_change in recent_bans:
        if ban_change.get("card") == card:
            # Card had recent ban list change
            # Recommendation should account for this
            return False  # Likely doesn't account for ban timeline
    
    return True


def _check_rotation_awareness(
    card: str,
    rotation_dates: list[datetime],
    timestamp: datetime,
) -> bool:
    """Check if recommendation accounts for format rotation."""
    # Check if rotation is coming soon
    for rotation_date in rotation_dates:
        days_until_rotation = (rotation_date - timestamp).days
        if 0 < days_until_rotation < 30:  # Rotation within 30 days
            # Recommendation should mention rotation
            return False  # Likely doesn't account for rotation
    
    return True


def _calculate_quality_in_context(
    legal: bool,
    price_reasonable: bool,
    meta_relevant: bool,
    accounts_for_shifts: bool,
) -> float:
    """Calculate quality score in temporal context."""
    if not legal:
        return 0.0  # Illegal = 0
    
    if not price_reasonable:
        return 1.0  # Price issue = 1
    
    if not meta_relevant:
        return 2.0  # Not meta-relevant = 2
    
    if not accounts_for_shifts:
        return 2.5  # Doesn't account for shifts = 2.5
    
    return 4.0  # All good = 4


def _calculate_quality_if_recommended_now(
    card: str,
    current_state: dict[str, Any],
) -> float:
    """Calculate quality if recommendation was made today."""
    # This would use current evaluation logic
    # Simplified for now
    format_state = current_state.get("format_state", {})
    ban_list = format_state.get("ban_list", [])
    
    if card in ban_list:
        return 0.0
    
    return 3.0  # Default moderate quality


def _identify_temporal_issues(
    card: str,
    legal: bool,
    price_reasonable: bool,
    meta_relevant: bool,
    temporal_context: TemporalContext,
    current_state: dict[str, Any],
) -> list[str]:
    """Identify temporal issues with the recommendation."""
    issues = []
    
    if not legal:
        issues.append(f"Card was not legal at recommendation time")
    
    if not price_reasonable:
        issues.append(f"Price was not reasonable at recommendation time")
    
    if not meta_relevant:
        issues.append(f"Card was not meta-relevant at recommendation time")
    
    # Check if card got banned after recommendation
    current_ban_list = current_state.get("format_state", {}).get("ban_list", [])
    if card in current_ban_list and legal:
        issues.append(f"Card was legal when recommended but got banned later")
    
    # Check if price spiked after recommendation
    price_then = temporal_context.price_state_at_time.get(card)
    price_now = current_state.get("price_state", {}).get(card)
    if price_then and price_now and price_now > price_then * 2:
        issues.append(f"Card price spiked after recommendation ({price_then:.2f} → {price_now:.2f})")
    
    return issues


def _identify_context_changes(
    card: str,
    temporal_context: TemporalContext,
    current_state: dict[str, Any],
) -> list[str]:
    """Identify what changed in context since recommendation."""
    changes = []
    
    # Check ban list changes
    ban_list_then = set(temporal_context.format_state_at_time.get("ban_list", []))
    ban_list_now = set(current_state.get("format_state", {}).get("ban_list", []))
    
    if card in ban_list_now and card not in ban_list_then:
        changes.append(f"Card was banned after recommendation")
    
    # Check price changes
    price_then = temporal_context.price_state_at_time.get(card)
    price_now = current_state.get("price_state", {}).get(card)
    if price_then and price_now:
        if price_now > price_then * 1.5:
            changes.append(f"Price increased significantly ({price_then:.2f} → {price_now:.2f})")
        elif price_now < price_then * 0.67:
            changes.append(f"Price decreased significantly ({price_then:.2f} → {price_now:.2f})")
    
    # Check meta share changes
    meta_share_then = temporal_context.meta_state_at_time.get("meta_share", {}).get(card, 0.0)
    meta_share_now = current_state.get("meta_state", {}).get("meta_share", {}).get(card, 0.0)
    
    if abs(meta_share_now - meta_share_then) > 0.10:
        changes.append(f"Meta share changed ({meta_share_then:.1%} → {meta_share_now:.1%})")
    
    return changes


__all__ = [
    "TemporalContext",
    "TemporalEvaluation",
    "evaluate_temporal_appropriateness",
]

