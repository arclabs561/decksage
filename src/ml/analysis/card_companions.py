#!/usr/bin/env python3
"""
Card Companions Analysis

Use case: "What cards appear together with Lightning Bolt?"
         "What does Ledger Shredder enable?"

This is co-occurrence analysis done right - not trying to find "similar" cards,
but finding what cards actually work together in successful decks.
"""

import json
from collections import Counter
from pathlib import Path


def analyze_card_companions(jsonl_path, focus_card, min_cooccurrence=5):
    """Find cards that frequently appear with a specific card"""

    # Find all decks containing the focus card
    decks_with_card = []
    total_decks = 0

    with open(jsonl_path) as f:
        for line in f:
            total_decks += 1
            deck = json.loads(line)
            cards = [c["name"] for c in deck.get("cards", [])]

            if focus_card in cards:
                decks_with_card.append(
                    {
                        "cards": cards,
                        "archetype": deck.get("archetype", "unknown"),
                        "format": deck.get("format", "unknown"),
                    }
                )

    if not decks_with_card:
        return None

    # Count co-occurring cards
    cooccurrence = Counter()
    archetypes = Counter()
    formats = Counter()

    for deck in decks_with_card:
        # Count each card once per deck (not multiple copies)
        unique_cards = set(deck["cards"]) - {focus_card}
        cooccurrence.update(unique_cards)
        archetypes[deck["archetype"]] += 1
        formats[deck["format"]] += 1

    # Filter by minimum co-occurrence
    common_companions = {
        card: count for card, count in cooccurrence.items() if count >= min_cooccurrence
    }

    # Calculate percentages
    num_decks = len(decks_with_card)
    companion_stats = {}
    for card, count in common_companions.items():
        percentage = (count / num_decks) * 100
        companion_stats[card] = {"count": count, "percentage": percentage}

    return {
        "focus_card": focus_card,
        "num_decks_total": total_decks,
        "num_decks_with_card": num_decks,
        "play_rate": (num_decks / total_decks) * 100,
        "companions": companion_stats,
        "top_archetypes": archetypes.most_common(5),
        "top_formats": formats.most_common(5),
    }


def print_companion_analysis(result):
    """Pretty print companion analysis"""
    if not result:
        print("Card not found in dataset")
        return

    print(f"\n{'=' * 60}")
    print(f"Card Companions: {result['focus_card']}")
    print(f"{'=' * 60}")
    print(
        f"Appears in {result['num_decks_with_card']}/{result['num_decks_total']} decks ({result['play_rate']:.1f}%)"
    )

    print("\nTop formats:")
    for fmt, count in result["top_formats"]:
        pct = (count / result["num_decks_with_card"]) * 100
        print(f"  {pct:5.1f}%  {fmt} ({count} decks)")

    print("\nTop archetypes:")
    for arch, count in result["top_archetypes"]:
        pct = (count / result["num_decks_with_card"]) * 100
        print(f"  {pct:5.1f}%  {arch} ({count} decks)")

    print("\nMost common companions:")
    sorted_companions = sorted(result["companions"].items(), key=lambda x: -x[1]["percentage"])

    for card, stats in sorted_companions[:30]:
        print(f"  {stats['percentage']:5.1f}%  {card}")


def main():
    data_path = Path("../../data/processed/decks_with_metadata.jsonl")

    print("Card Companions Analysis Tool")
    print("=" * 60)
    print("Find what cards appear together in successful decks")
    print()

    # Example analyses
    test_cards = ["Lightning Bolt", "Brainstorm", "Sol Ring", "Force of Will", "Thoughtseize"]

    for card in test_cards:
        result = analyze_card_companions(data_path, card, min_cooccurrence=10)
        if result:
            print_companion_analysis(result)

    print(f"\n{'=' * 60}")
    print("Why This Works")
    print(f"{'=' * 60}")
    print("This is NOT trying to find 'similar' cards")
    print("It's showing what actually works together in winning decks")
    print()
    print("Use cases:")
    print("- 'I'm building around Card X, what should I include?'")
    print("- 'What does Card Y enable?'")
    print("- 'What's the package around Card Z?'")
    print()
    print("This uses co-occurrence correctly: composition, not similarity")


if __name__ == "__main__":
    main()
