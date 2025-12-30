#!/usr/bin/env python3
"""
Sideboard Signal for Similarity

Extracts sideboard frequency as a similarity signal.
Cards that appear frequently in sideboards together = strong synergy signal.

This leverages co-occurrence's strength: sideboard patterns reveal
meta-dependent relationships and matchup-specific tech.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd


def compute_sideboard_cooccurrence(
    decks_jsonl: Path | str,
    min_decks: int = 5,
) -> dict[str, dict[str, float]]:
    """
    Compute sideboard co-occurrence frequencies.

    Returns:
        Dict mapping card -> dict of co-occurring cards -> frequency (0-1)
    """
    sideboard_pairs: defaultdict[str, Counter] = defaultdict(Counter)
    card_sideboard_counts: Counter = Counter()

    with open(decks_jsonl) as f:
        for line in f:
            deck = json.loads(line)
            cards = deck.get("cards", [])

            # Extract sideboard cards
            sideboard_cards = [
                c["name"]
                for c in cards
                if c.get("partition", "").lower() == "sideboard"
            ]

            if len(sideboard_cards) < 2:
                continue

            # Count co-occurrences in sideboard
            unique_sb = set(sideboard_cards)
            for card in unique_sb:
                card_sideboard_counts[card] += 1
                for other in unique_sb:
                    if card != other:
                        sideboard_pairs[card][other] += 1

    # Convert to frequencies
    sideboard_similarity: dict[str, dict[str, float]] = {}
    for card, cooccurrences in sideboard_pairs.items():
        total_decks = card_sideboard_counts[card]
        if total_decks < min_decks:
            continue

        sideboard_similarity[card] = {
            other: count / total_decks
            for other, count in cooccurrences.items()
            if card_sideboard_counts[other] >= min_decks
        }

    return sideboard_similarity


def compute_mainboard_vs_sideboard_signal(
    decks_jsonl: Path | str,
) -> dict[str, dict[str, float]]:
    """
    Compute mainboard-sideboard transition signal.

    Cards that appear in both mainboard and sideboard = flexible/flex slots.
    Cards only in sideboard = matchup-specific tech.

    Returns:
        Dict mapping card -> {"flexibility": float, "sideboard_only_freq": float}
    """
    import json

    card_stats: defaultdict[str, dict[str, int]] = defaultdict(
        lambda: {"mainboard": 0, "sideboard": 0, "both": 0}
    )

    with open(decks_jsonl) as f:
        for line in f:
            deck = json.loads(line)
            cards = deck.get("cards", [])

            mainboard_cards = set()
            sideboard_cards = set()

            for c in cards:
                card = c["name"]
                partition = c.get("partition", "").lower()
                if partition == "sideboard":
                    sideboard_cards.add(card)
                else:
                    mainboard_cards.add(card)

            # Count occurrences
            for card in mainboard_cards:
                card_stats[card]["mainboard"] += 1
            for card in sideboard_cards:
                card_stats[card]["sideboard"] += 1
            for card in mainboard_cards & sideboard_cards:
                card_stats[card]["both"] += 1

    # Compute signals
    signals: dict[str, dict[str, float]] = {}
    for card, stats in card_stats.items():
        total = stats["mainboard"] + stats["sideboard"] - stats["both"]
        if total == 0:
            continue

        flexibility = stats["both"] / total if total > 0 else 0.0
        sideboard_only_freq = (
            (stats["sideboard"] - stats["both"]) / total if total > 0 else 0.0
        )

        signals[card] = {
            "flexibility": flexibility,  # Appears in both = flexible
            "sideboard_only_freq": sideboard_only_freq,  # Only SB = tech
        }

    return signals


def sideboard_similarity(
    query: str,
    candidates: list[str],
    sideboard_cooccurrence: dict[str, dict[str, float]],
    mainboard_sb_signals: dict[str, dict[str, float]] | None = None,
) -> list[tuple[str, float]]:
    """
    Compute sideboard-based similarity scores.

    Args:
        query: Query card
        candidates: Candidate cards
        sideboard_cooccurrence: Sideboard co-occurrence frequencies
        mainboard_sb_signals: Optional mainboard-sideboard transition signals

    Returns:
        List of (candidate, score) tuples, sorted by score descending
    """
    scores = []

    query_sb_cooccur = sideboard_cooccurrence.get(query, {})

    for candidate in candidates:
        # Direct sideboard co-occurrence
        sb_score = query_sb_cooccur.get(candidate, 0.0)

        # Boost if both are flexible (appear in both MB and SB)
        if mainboard_sb_signals:
            query_flex = mainboard_sb_signals.get(query, {}).get("flexibility", 0.0)
            cand_flex = mainboard_sb_signals.get(candidate, {}).get(
                "flexibility", 0.0
            )
            flexibility_boost = (query_flex + cand_flex) / 2.0 * 0.1
            sb_score += flexibility_boost

        scores.append((candidate, sb_score))

    # Sort by score descending
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores


if __name__ == "__main__":
    import json

    # Example usage
    decks_path = Path("../../data/processed/decks_with_metadata.jsonl")

    print("Computing sideboard co-occurrence...")
    sb_cooccur = compute_sideboard_cooccurrence(decks_path, min_decks=5)

    print("Computing mainboard-sideboard signals...")
    mb_sb_signals = compute_mainboard_vs_sideboard_signal(decks_path)

    # Example query
    query = "Lightning Bolt"
    candidates = ["Chain Lightning", "Lava Spike", "Rift Bolt", "Shock"]

    scores = sideboard_similarity(query, candidates, sb_cooccur, mb_sb_signals)

    print(f"\nSideboard similarity for '{query}':")
    for card, score in scores:
        print(f"  {card}: {score:.3f}")

