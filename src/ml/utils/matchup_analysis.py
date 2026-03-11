#!/usr/bin/env python3
"""
Matchup Analysis Utilities

Analyze round-by-round results to compute matchup statistics and win rates.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def _extract_archetype_from_deck(deck: dict[str, Any]) -> str | None:
    """Extract archetype from deck structure."""
    if "archetype" in deck:
        return deck["archetype"]
    if "type" in deck and isinstance(deck["type"], dict):
        inner = deck["type"].get("inner")
        if isinstance(inner, dict) and "archetype" in inner:
            return inner["archetype"]
    return None


def compute_matchup_statistics(
    deck: dict[str, Any],
    all_decks: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """
    Compute matchup statistics from round results.

    Args:
        deck: Deck dictionary with roundResults
        all_decks: All decks for opponent archetype lookup (optional)

    Returns:
        Dict with matchup statistics, or None if no round results
    """
    # Extract round results
    round_results = deck.get("roundResults") or (
        deck.get("type", {}).get("inner", {}) if isinstance(deck.get("type"), dict) else {}
    ).get("roundResults")

    if not round_results or not isinstance(round_results, list):
        return None

    # Create lookup for opponent archetypes if all_decks provided
    opponent_archetypes: dict[str, str] = {}
    if all_decks:
        for d in all_decks:
            if not isinstance(d, dict):
                continue
            player = d.get("player") or (
                d.get("type", {}).get("inner", {}) if isinstance(d.get("type"), dict) else {}
            ).get("player")
            archetype = _extract_archetype_from_deck(d)
            if player and archetype:
                opponent_archetypes[player] = archetype

    # Filter out invalid round results
    valid_rounds = [
        r
        for r in round_results
        if isinstance(r, dict) and r.get("result") in ("W", "L", "T", "BYE")
    ]

    if not valid_rounds:
        return None

    # Compute statistics
    total_rounds = len(valid_rounds)
    wins = sum(1 for r in valid_rounds if r.get("result") == "W")
    losses = sum(1 for r in valid_rounds if r.get("result") == "L")
    ties = sum(1 for r in valid_rounds if r.get("result") == "T")
    byes = sum(1 for r in valid_rounds if r.get("result") == "BYE")

    # Matchup win rates by archetype
    matchup_wr: dict[str, dict[str, int]] = defaultdict(lambda: {"wins": 0, "losses": 0, "ties": 0})
    for r in valid_rounds:
        opponent_deck = r.get("opponentDeck") or r.get("opponent_deck")
        if not opponent_deck:
            # Try to look up from opponent name
            opponent = r.get("opponent")
            if opponent and opponent in opponent_archetypes:
                opponent_deck = opponent_archetypes[opponent]

        if opponent_deck:
            result = r.get("result")
            if result == "W":
                matchup_wr[opponent_deck]["wins"] += 1
            elif result == "L":
                matchup_wr[opponent_deck]["losses"] += 1
            elif result == "T":
                matchup_wr[opponent_deck]["ties"] += 1

    # Convert to win rates
    matchup_win_rates: dict[str, dict[str, Any]] = {}
    for archetype, stats in matchup_wr.items():
        total = stats["wins"] + stats["losses"] + stats["ties"]
        if total > 0:
            matchup_win_rates[archetype] = {
                "win_rate": stats["wins"] / total,
                "wins": stats["wins"],
                "losses": stats["losses"],
                "ties": stats["ties"],
                "total": total,
            }

    return {
        "total_rounds": total_rounds,
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "byes": byes,
        "win_rate": wins / total_rounds if total_rounds > 0 else 0.0,
        "matchup_win_rates": matchup_win_rates,
    }


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
        }
        if best_matchup
        else None,
        "worst_matchup": {
            "archetype": worst_matchup[0],
            "win_rate": worst_matchup[1]["win_rate"],
            "record": f"{worst_matchup[1]['wins']}-{worst_matchup[1]['losses']}-{worst_matchup[1]['ties']}",
        }
        if worst_matchup
        else None,
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

    archetype_matchups = defaultdict(
        lambda: defaultdict(lambda: {"wins": 0, "losses": 0, "ties": 0})
    )

    for deck in decks:
        if not isinstance(deck, dict):
            continue

        archetype = deck.get("archetype") or (
            deck.get("type", {}).get("inner", {}) if isinstance(deck.get("type"), dict) else {}
        ).get("archetype")
        if not archetype:
            continue

        round_results = deck.get("roundResults") or (
            deck.get("type", {}).get("inner", {}) if isinstance(deck.get("type"), dict) else {}
        ).get("roundResults")
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
