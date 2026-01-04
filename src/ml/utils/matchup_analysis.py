#!/usr/bin/env python3
"""
Matchup Analysis Utilities

Analyze round-by-round results to compute matchup statistics and win rates.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..scripts.compute_temporal_metadata import compute_matchup_statistics


def analyze_deck_matchups(
    deck: dict[str, Any],
    all_decks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Analyze matchup performance for a deck.
    
    Args:
        deck: Deck dictionary with roundResults
        all_decks: All decks for opponent archetype lookup
    
    Returns:
        Dict with matchup analysis
    """
    matchup_stats = compute_matchup_statistics(deck, all_decks)
    
    if not matchup_stats:
        return {
            "has_round_results": False,
            "message": "No round results available",
        }
    
    # Identify best and worst matchups
    matchup_wr = matchup_stats.get("matchup_win_rates", {})
    
    if not matchup_wr:
        return {
            "has_round_results": True,
            "total_rounds": matchup_stats["total_rounds"],
            "overall_win_rate": matchup_stats["win_rate"],
            "message": "No matchup data (missing opponent archetypes)",
        }
    
    # Sort by win rate
    sorted_matchups = sorted(
        matchup_wr.items(),
        key=lambda x: x[1]["win_rate"],
        reverse=True,
    )
    
    best_matchup = sorted_matchups[0] if sorted_matchups else None
    worst_matchup = sorted_matchups[-1] if sorted_matchups else None
    
    return {
        "has_round_results": True,
        "total_rounds": matchup_stats["total_rounds"],
        "overall_win_rate": matchup_stats["win_rate"],
        "wins": matchup_stats["wins"],
        "losses": matchup_stats["losses"],
        "ties": matchup_stats["ties"],
        "byes": matchup_stats["byes"],
        "best_matchup": {
            "archetype": best_matchup[0],
            "win_rate": best_matchup[1]["win_rate"],
            "record": f"{best_matchup[1]['wins']}-{best_matchup[1]['losses']}-{best_matchup[1]['ties']}",
        } if best_matchup else None,
        "worst_matchup": {
            "archetype": worst_matchup[0],
            "win_rate": worst_matchup[1]["win_rate"],
            "record": f"{worst_matchup[1]['wins']}-{worst_matchup[1]['losses']}-{worst_matchup[1]['ties']}",
        } if worst_matchup else None,
        "matchup_count": len(matchup_wr),
        "matchup_win_rates": matchup_wr,
    }


def aggregate_matchup_data(
    decks: list[dict[str, Any]],
    min_samples: int = 3,
) -> dict[str, dict[str, float]]:
    """
    Aggregate matchup data across multiple decks.
    
    Args:
        decks: List of deck dictionaries with roundResults
        min_samples: Minimum number of matches to include matchup (default: 3)
    
    Returns:
        Dict mapping archetype -> opponent_archetype -> win_rate
    
    Example:
        >>> decks = [
        ...     {"archetype": "Burn", "roundResults": [
        ...         {"opponentDeck": "Jund", "result": "W"},
        ...         {"opponentDeck": "Jund", "result": "W"},
        ...     ]}
        ... ]
        >>> aggregated = aggregate_matchup_data(decks, min_samples=2)
        >>> aggregated["Burn"]["Jund"]
        1.0
    """
    if min_samples < 1:
        min_samples = 1  # Ensure at least 1 sample
    
    archetype_matchups = defaultdict(lambda: defaultdict(lambda: {"wins": 0, "losses": 0, "ties": 0}))
    
    for deck in decks:
        if not isinstance(deck, dict):
            continue
        
        archetype = (
            deck.get("archetype")
            or (deck.get("type", {}).get("inner", {}) if isinstance(deck.get("type"), dict) else {}).get("archetype")
        )
        if not archetype:
            continue
        
        round_results = (
            deck.get("roundResults")
            or (deck.get("type", {}).get("inner", {}) if isinstance(deck.get("type"), dict) else {}).get("roundResults")
        )
        if not round_results or not isinstance(round_results, list):
            continue
        
        for r in round_results:
            if not isinstance(r, dict):
                continue
            
            opponent_deck = r.get("opponentDeck") or r.get("opponent_deck")
            if not opponent_deck:
                continue
            
            result = r.get("result")
            if result == "W":
                archetype_matchups[archetype][opponent_deck]["wins"] += 1
            elif result == "L":
                archetype_matchups[archetype][opponent_deck]["losses"] += 1
            elif result == "T":
                archetype_matchups[archetype][opponent_deck]["ties"] += 1
    
    # Convert to win rates
    aggregated = {}
    for archetype, matchups in archetype_matchups.items():
        aggregated[archetype] = {}
        for opponent, stats in matchups.items():
            total = stats["wins"] + stats["losses"] + stats["ties"]
            if total >= min_samples:
                aggregated[archetype][opponent] = stats["wins"] / total if total > 0 else 0.0
    
    return aggregated

