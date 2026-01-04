#!/usr/bin/env python3
"""
Format-Specific Signal for Similarity

Uses format-specific co-occurrence patterns.
Cards that co-occur across formats = strong universal synergy.
Cards that only co-occur in one format = format-specific tech.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path


def compute_format_cooccurrence(
    decks_jsonl: Path | str,
    min_decks_per_format: int = 10,
) -> dict[str, dict[str, dict[str, float]]]:
    """
    Compute co-occurrence by format.

    Returns:
        Dict mapping format -> card -> co-occurring card -> frequency
    """
    decks_by_format: defaultdict[str, list[set[str]]] = defaultdict(list)

    with open(decks_jsonl) as f:
        for line in f:
            deck = json.loads(line)
            fmt = deck.get("format", "unknown")
            if not fmt or fmt == "unknown":
                continue

            cards = {c["name"] for c in deck.get("cards", [])}
            if cards:
                decks_by_format[fmt].append(cards)

    # Compute co-occurrence per format
    format_cooccurrence: dict[str, dict[str, dict[str, float]]] = {}

    for fmt, decks in decks_by_format.items():
        if len(decks) < min_decks_per_format:
            continue

        card_pairs: defaultdict[str, Counter] = defaultdict(Counter)
        card_counts: Counter = Counter()

        for deck in decks:
            card_counts.update(deck)
            for card1 in deck:
                for card2 in deck:
                    if card1 != card2:
                        card_pairs[card1][card2] += 1

        # Convert to frequencies
        fmt_cooccur: dict[str, dict[str, float]] = {}
        for card1, cooccurrences in card_pairs.items():
            total = card_counts[card1]
            if total >= 5:  # Minimum threshold
                fmt_cooccur[card1] = {
                    card2: count / total
                    for card2, count in cooccurrences.items()
                    if card_counts[card2] >= 5
                }

        format_cooccurrence[fmt] = fmt_cooccur

    return format_cooccurrence


def compute_format_transition_patterns(
    format_cooccurrence: dict[str, dict[str, dict[str, float]]],
) -> dict[str, dict[str, float]]:
    """
    Find cards that co-occur across multiple formats (universal synergy).

    Returns:
        Dict mapping card -> co-occurring card -> cross-format frequency
    """
    # Count how many formats each pair appears in
    pair_format_counts: defaultdict[tuple[str, str], int] = defaultdict(int)
    pair_scores: defaultdict[tuple[str, str], list[float]] = defaultdict(list)

    for fmt, cooccur in format_cooccurrence.items():
        for card1, others in cooccur.items():
            for card2, freq in others.items():
                pair = tuple(sorted([card1, card2]))
                pair_format_counts[pair] += 1
                pair_scores[pair].append(freq)

    # Compute cross-format scores (average across formats, weighted by format count)
    results: dict[str, dict[str, float]] = defaultdict(dict)

    for (card1, card2), format_count in pair_format_counts.items():
        if format_count >= 2:  # Must appear in at least 2 formats
            avg_score = sum(pair_scores[(card1, card2)]) / len(pair_scores[(card1, card2)])
            # Boost score by number of formats (universal = stronger)
            cross_format_score = avg_score * (1.0 + format_count * 0.1)
            results[card1][card2] = min(cross_format_score, 1.0)
            results[card2][card1] = min(cross_format_score, 1.0)

    return dict(results)


def format_similarity(
    query: str,
    candidate: str,
    format_cooccurrence: dict[str, dict[str, dict[str, float]]],
    cross_format_patterns: dict[str, dict[str, float]] | None = None,
) -> float:
    """
    Compute format-based similarity.

    Combines:
    1. Cross-format co-occurrence (universal synergy)
    2. Format-specific co-occurrence (weighted average)
    """
    score = 0.0

    # 1. Cross-format patterns (universal synergy)
    if cross_format_patterns:
        cross_score = cross_format_patterns.get(query, {}).get(candidate, 0.0)
        score += cross_score * 0.5  # 50% weight

    # 2. Format-specific co-occurrence (average across formats)
    format_scores = []
    for fmt, cooccur in format_cooccurrence.items():
        fmt_data = cooccur.get(query, {})
        fmt_score = fmt_data.get(candidate, 0.0)
        if fmt_score > 0:
            format_scores.append(fmt_score)

    if format_scores:
        avg_format_score = sum(format_scores) / len(format_scores)
        score += avg_format_score * 0.5  # 50% weight

    return min(score, 1.0)


if __name__ == "__main__":
    from ..utils.paths import PATHS

    decks_path = PATHS.decks_with_metadata

    if not decks_path.exists():
        print(f"Error: {decks_path} not found")
        exit(1)

    print("Computing format-specific co-occurrence...")
    format_cooccur = compute_format_cooccurrence(decks_path, min_decks_per_format=10)
    print(f"✓ Found {len(format_cooccur)} formats")

    print("\nComputing cross-format patterns...")
    cross_format = compute_format_transition_patterns(format_cooccur)
    print(f"✓ Found {len(cross_format)} cards with cross-format patterns")

    # Example
    query = "Lightning Bolt"
    candidate = "Chain Lightning"

    sim = format_similarity(query, candidate, format_cooccur, cross_format)
    print(f"\nFormat similarity ({query}, {candidate}): {sim:.3f}")
