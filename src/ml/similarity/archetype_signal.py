#!/usr/bin/env python3
"""
Archetype Staples Signal for Similarity

Uses archetype frequency analysis to boost similarity scores.
Cards that are staples together in archetypes = strong similarity signal.

This leverages co-occurrence's strength: archetype analysis works well.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def compute_archetype_staples(
    decks_jsonl: Path | str,
    min_decks: int = 20,
    staple_threshold: float = 0.7,
) -> dict[str, dict[str, float]]:
    """
    Compute archetype staple frequencies.
    
    Returns:
        Dict mapping card -> dict of archetype -> frequency (0-1)
        Frequency = percentage of decks in that archetype containing the card
    """
    decks_by_archetype: defaultdict[str, list[set[str]]] = defaultdict(list)
    
    with open(decks_jsonl) as f:
        for line in f:
            deck = json.loads(line)
            archetype = deck.get("archetype", "unknown")
            if not archetype or archetype == "unknown":
                continue
                
            cards = {c["name"] for c in deck.get("cards", [])}
            if cards:
                decks_by_archetype[archetype].append(cards)
    
    # Compute card frequencies per archetype
    card_archetype_freq: dict[str, dict[str, float]] = defaultdict(dict)
    
    for archetype, decks in decks_by_archetype.items():
        if len(decks) < min_decks:
            continue
        
        # Count card occurrences
        card_counts = Counter()
        for deck in decks:
            card_counts.update(deck)
        
        # Calculate frequencies
        num_decks = len(decks)
        for card, count in card_counts.items():
            freq = count / num_decks
            if freq >= staple_threshold:  # Only include staples
                card_archetype_freq[card][archetype] = freq
    
    return dict(card_archetype_freq)


def compute_archetype_cooccurrence(
    decks_jsonl: Path | str,
    min_decks: int = 20,
) -> dict[str, dict[str, float]]:
    """
    Compute co-occurrence within archetypes.
    
    Returns:
        Dict mapping card -> dict of co-occurring cards -> frequency
        Frequency = how often they appear together in the same archetype
    """
    decks_by_archetype: defaultdict[str, list[set[str]]] = defaultdict(list)
    
    with open(decks_jsonl) as f:
        for line in f:
            deck = json.loads(line)
            archetype = deck.get("archetype", "unknown")
            if not archetype or archetype == "unknown":
                continue
                
            cards = {c["name"] for c in deck.get("cards", [])}
            if cards:
                decks_by_archetype[archetype].append(cards)
    
    # Compute co-occurrence within archetypes
    card_cooccurrence: defaultdict[str, Counter] = defaultdict(Counter)
    card_archetype_counts: Counter = Counter()
    
    for archetype, decks in decks_by_archetype.items():
        if len(decks) < min_decks:
            continue
        
        for deck in decks:
            for card in deck:
                card_archetype_counts[card] += 1
                for other in deck:
                    if card != other:
                        card_cooccurrence[card][other] += 1
    
    # Convert to frequencies
    results: dict[str, dict[str, float]] = {}
    for card, cooccurrences in card_cooccurrence.items():
        total = card_archetype_counts[card]
        if total >= min_decks:
            results[card] = {
                other: count / total
                for other, count in cooccurrences.items()
                if card_archetype_counts[other] >= min_decks
            }
    
    return results


def archetype_similarity(
    query: str,
    candidate: str,
    archetype_staples: dict[str, dict[str, float]],
    archetype_cooccurrence: dict[str, dict[str, float]],
) -> float:
    """
    Compute archetype-based similarity.
    
    Combines:
    1. Shared archetype membership (both are staples in same archetypes)
    2. Co-occurrence within archetypes
    """
    score = 0.0
    
    # 1. Shared archetype membership
    query_archetypes = set(archetype_staples.get(query, {}).keys())
    candidate_archetypes = set(archetype_staples.get(candidate, {}).keys())
    shared_archetypes = query_archetypes & candidate_archetypes
    
    if shared_archetypes:
        # Average frequency in shared archetypes
        shared_scores = []
        for arch in shared_archetypes:
            query_freq = archetype_staples[query][arch]
            cand_freq = archetype_staples[candidate][arch]
            shared_scores.append((query_freq + cand_freq) / 2.0)
        score += sum(shared_scores) / len(shared_scores) * 0.6  # 60% weight
    
    # 2. Co-occurrence within archetypes
    query_cooccur = archetype_cooccurrence.get(query, {})
    cooccur_score = query_cooccur.get(candidate, 0.0)
    score += cooccur_score * 0.4  # 40% weight
    
    return min(score, 1.0)  # Cap at 1.0


if __name__ == "__main__":
    from ..utils.paths import PATHS
    
    decks_path = PATHS.decks_with_metadata
    
    if not decks_path.exists():
        print(f"Error: {decks_path} not found")
        exit(1)
    
    print("Computing archetype staples...")
    staples = compute_archetype_staples(decks_path, min_decks=20)
    print(f"✓ Found {len(staples)} cards with archetype staple data")
    
    print("\nComputing archetype co-occurrence...")
    cooccur = compute_archetype_cooccurrence(decks_path, min_decks=20)
    print(f"✓ Found {len(cooccur)} cards with archetype co-occurrence data")
    
    # Example
    query = "Lightning Bolt"
    candidate = "Chain Lightning"
    
    if query in staples and candidate in staples:
        sim = archetype_similarity(query, candidate, staples, cooccur)
        print(f"\nArchetype similarity ({query}, {candidate}): {sim:.3f}")

