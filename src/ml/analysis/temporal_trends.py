#!/usr/bin/env python3
"""
Temporal Trend Analysis

Tracks how card popularity and co-occurrence patterns change over time.
Reveals meta shifts, emerging synergies, and ban list impacts.

Implicit signals:
- Cards that rise/fall together = meta-relevant
- New co-occurrences = emerging synergies
- Temporal correlation = format-dependent relationships
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


def parse_deck_date(deck: dict[str, Any]) -> datetime | None:
    """Extract date from deck metadata."""
    date_str = deck.get("date") or deck.get("scraped_at") or deck.get("created_at")
    if not date_str:
        return None

    # Try various date formats
    formats = [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str[:19], fmt)
        except ValueError:
            continue

    return None


def compute_monthly_cooccurrence(
    decks_jsonl: Path | str,
    min_decks_per_month: int = 10,
) -> dict[str, dict[str, dict[str, float]]]:
    """
    Compute co-occurrence by month.

    Returns:
        Dict mapping month (YYYY-MM) -> card -> co-occurring card -> frequency
    """
    monthly_decks: defaultdict[str, list[dict]] = defaultdict(list)

    with open(decks_jsonl) as f:
        for line in f:
            deck = json.loads(line)
            date = parse_deck_date(deck)
            if not date:
                continue

            month_key = date.strftime("%Y-%m")
            monthly_decks[month_key].append(deck)

    monthly_cooccurrence: dict[str, dict[str, dict[str, float]]] = {}

    for month, decks in monthly_decks.items():
        if len(decks) < min_decks_per_month:
            continue

        # Compute co-occurrence for this month
        card_pairs: defaultdict[str, Counter] = defaultdict(Counter)
        card_counts: Counter = Counter()

        for deck in decks:
            cards = [c["name"] for c in deck.get("cards", [])]
            unique_cards = set(cards)

            for card in unique_cards:
                card_counts[card] += 1
                for other in unique_cards:
                    if card != other:
                        card_pairs[card][other] += 1

        # Convert to frequencies
        month_cooccur: dict[str, dict[str, float]] = {}
        for card, cooccurrences in card_pairs.items():
            total = card_counts[card]
            if total < 5:  # Minimum threshold
                continue

            month_cooccur[card] = {
                other: count / total
                for other, count in cooccurrences.items()
                if card_counts[other] >= 5
            }

        monthly_cooccurrence[month] = month_cooccur

    return monthly_cooccurrence


def find_trending_pairs(
    monthly_cooccurrence: dict[str, dict[str, dict[str, float]]],
    min_months: int = 3,
) -> list[tuple[str, str, float]]:
    """
    Find card pairs that are trending (rising co-occurrence).

    Returns:
        List of (card1, card2, trend_score) tuples
        trend_score > 0 = rising, < 0 = falling
    """
    # Get all months sorted
    months = sorted(monthly_cooccurrence.keys())

    if len(months) < min_months:
        return []

    # Track pairs across months
    pair_trends: defaultdict[tuple[str, str], list[float]] = defaultdict(list)

    for month in months:
        cooccur = monthly_cooccurrence[month]
        for card1, others in cooccur.items():
            for card2, freq in others.items():
                # Normalize pair (alphabetical order)
                pair = tuple(sorted([card1, card2]))
                pair_trends[pair].append(freq)

    # Compute trends (simple linear regression slope)
    trending: list[tuple[str, str, float]] = []

    for (card1, card2), frequencies in pair_trends.items():
        if len(frequencies) < min_months:
            continue

        # Simple trend: (last - first) / (num_months - 1)
        trend = (frequencies[-1] - frequencies[0]) / (len(frequencies) - 1)

        # Only include significant trends
        if abs(trend) > 0.01:  # At least 1% change per month
            trending.append((card1, card2, trend))

    # Sort by trend (descending)
    trending.sort(key=lambda x: x[2], reverse=True)
    return trending


def compute_card_popularity_trends(
    decks_jsonl: Path | str,
    min_decks_per_month: int = 10,
) -> dict[str, list[tuple[str, float]]]:
    """
    Compute card popularity over time.

    Returns:
        Dict mapping card -> list of (month, popularity) tuples
    """
    monthly_decks: defaultdict[str, list[dict]] = defaultdict(list)

    with open(decks_jsonl) as f:
        for line in f:
            deck = json.loads(line)
            date = parse_deck_date(deck)
            if not date:
                continue

            month_key = date.strftime("%Y-%m")
            monthly_decks[month_key].append(deck)

    card_trends: dict[str, list[tuple[str, float]]] = defaultdict(list)

    for month in sorted(monthly_decks.keys()):
        decks = monthly_decks[month]
        if len(decks) < min_decks_per_month:
            continue

        # Count card appearances
        card_counts: Counter = Counter()
        for deck in decks:
            cards = [c["name"] for c in deck.get("cards", [])]
            card_counts.update(set(cards))

        total_decks = len(decks)
        for card, count in card_counts.items():
            popularity = count / total_decks
            card_trends[card].append((month, popularity))

    return dict(card_trends)


def temporal_similarity_signal(
    query: str,
    candidates: list[str],
    monthly_cooccurrence: dict[str, dict[str, dict[str, float]]],
    trending_pairs: list[tuple[str, str, float]] | None = None,
) -> list[tuple[str, float]]:
    """
    Compute temporal similarity signal.

    Boosts candidates that:
    1. Co-occur with query in recent months (recency)
    2. Are trending together (rising popularity)
    3. Show consistent co-occurrence over time (stability)

    Args:
        query: Query card
        candidates: Candidate cards
        monthly_cooccurrence: Monthly co-occurrence data
        trending_pairs: Optional pre-computed trending pairs

    Returns:
        List of (candidate, score) tuples
    """
    if not monthly_cooccurrence:
        return [(c, 0.0) for c in candidates]

    # Get recent months (last 3 months)
    months = sorted(monthly_cooccurrence.keys())
    recent_months = months[-3:] if len(months) >= 3 else months

    scores = []
    trending_dict = (
        {tuple(sorted([c1, c2])): trend for c1, c2, trend in trending_pairs}
        if trending_pairs
        else {}
    )

    for candidate in candidates:
        # Recent co-occurrence (weighted by recency)
        recent_score = 0.0
        total_weight = 0.0

        for i, month in enumerate(recent_months):
            weight = i + 1  # More recent = higher weight
            cooccur = monthly_cooccurrence[month].get(query, {})
            freq = cooccur.get(candidate, 0.0)
            recent_score += freq * weight
            total_weight += weight

        recent_score = recent_score / total_weight if total_weight > 0 else 0.0

        # Trending boost
        pair_key = tuple(sorted([query, candidate]))
        trend_boost = trending_dict.get(pair_key, 0.0) * 0.2  # Scale trend

        # Stability (co-occurrence across all months)
        all_freqs = []
        for month in months:
            cooccur = monthly_cooccurrence[month].get(query, {})
            freq = cooccur.get(candidate, 0.0)
            if freq > 0:
                all_freqs.append(freq)

        stability = sum(all_freqs) / len(all_freqs) if all_freqs else 0.0  # Average across months

        # Combined score
        score = recent_score * 0.5 + stability * 0.3 + trend_boost
        scores.append((candidate, score))

    # Sort by score descending
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores


if __name__ == "__main__":
    import json

    decks_path = Path("../../data/processed/decks_with_metadata.jsonl")

    print("Computing monthly co-occurrence...")
    monthly_cooccur = compute_monthly_cooccurrence(decks_path, min_decks_per_month=20)

    print(f"Found {len(monthly_cooccur)} months of data")

    print("\nFinding trending pairs...")
    trending = find_trending_pairs(monthly_cooccur, min_months=3)

    print("\nTop 10 trending pairs:")
    for card1, card2, trend in trending[:10]:
        print(f"  {card1} + {card2}: {trend:+.3f} per month")

    print("\nComputing card popularity trends...")
    popularity_trends = compute_card_popularity_trends(decks_path)

    # Example: Lightning Bolt popularity
    if "Lightning Bolt" in popularity_trends:
        print("\nLightning Bolt popularity over time:")
        for month, pop in popularity_trends["Lightning Bolt"][-6:]:
            print(f"  {month}: {pop:.1%}")
