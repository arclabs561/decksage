#!/usr/bin/env python3
"""
Deck Composition Statistics

Use cases:
- "What's the average mana curve in Burn?"
- "How many lands do Reanimator decks play?"
- "What's the creature count in Affinity?"

This analyzes deck structure patterns - another thing co-occurrence data enables.
"""

import json
import statistics
from collections import defaultdict
from pathlib import Path


def analyze_deck_composition(jsonl_path, min_decks=30):
    """Analyze deck composition statistics by archetype"""

    archetype_stats = defaultdict(
        lambda: {
            "deck_sizes": [],
            "mainboard_sizes": [],
            "sideboard_sizes": [],
            "unique_cards": [],
            "avg_copies": [],
        }
    )

    with open(jsonl_path) as f:
        for line in f:
            deck = json.loads(line)
            archetype = deck.get("archetype", "unknown")

            cards = deck.get("cards", [])
            mainboard = [c for c in cards if c.get("partition") != "Sideboard"]
            sideboard = [c for c in cards if c.get("partition") == "Sideboard"]

            # Calculate stats
            total_cards = sum(c["count"] for c in cards)
            mb_size = sum(c["count"] for c in mainboard)
            sb_size = sum(c["count"] for c in sideboard)
            unique = len({c["name"] for c in cards})
            avg_copies = total_cards / unique if unique > 0 else 0

            archetype_stats[archetype]["deck_sizes"].append(total_cards)
            archetype_stats[archetype]["mainboard_sizes"].append(mb_size)
            archetype_stats[archetype]["sideboard_sizes"].append(sb_size)
            archetype_stats[archetype]["unique_cards"].append(unique)
            archetype_stats[archetype]["avg_copies"].append(avg_copies)

    # Calculate summary statistics
    results = {}
    for archetype, stats in archetype_stats.items():
        if len(stats["deck_sizes"]) < min_decks:
            continue

        results[archetype] = {
            "num_decks": len(stats["deck_sizes"]),
            "deck_size": {
                "mean": statistics.mean(stats["deck_sizes"]),
                "median": statistics.median(stats["deck_sizes"]),
                "stdev": statistics.stdev(stats["deck_sizes"])
                if len(stats["deck_sizes"]) > 1
                else 0,
            },
            "mainboard_size": {
                "mean": statistics.mean(stats["mainboard_sizes"]),
                "median": statistics.median(stats["mainboard_sizes"]),
            },
            "sideboard_size": {
                "mean": statistics.mean(stats["sideboard_sizes"]),
                "median": statistics.median(stats["sideboard_sizes"]),
            },
            "unique_cards": {
                "mean": statistics.mean(stats["unique_cards"]),
                "median": statistics.median(stats["unique_cards"]),
            },
            "avg_copies_per_card": {
                "mean": statistics.mean(stats["avg_copies"]),
                "median": statistics.median(stats["avg_copies"]),
            },
        }

    return results


def compare_formats(jsonl_path):
    """Compare deck construction patterns across formats"""

    format_stats = defaultdict(lambda: {"deck_sizes": [], "sideboards": []})

    with open(jsonl_path) as f:
        for line in f:
            deck = json.loads(line)
            fmt = deck.get("format", "unknown")

            cards = deck.get("cards", [])
            mainboard = [c for c in cards if c.get("partition") != "Sideboard"]
            sideboard = [c for c in cards if c.get("partition") == "Sideboard"]

            mb_size = sum(c["count"] for c in mainboard)
            sb_size = sum(c["count"] for c in sideboard)

            format_stats[fmt]["deck_sizes"].append(mb_size)
            if sb_size > 0:
                format_stats[fmt]["sideboards"].append(sb_size)

    results = {}
    for fmt, stats in format_stats.items():
        if len(stats["deck_sizes"]) < 20:
            continue

        has_sb = len(stats["sideboards"])
        results[fmt] = {
            "num_decks": len(stats["deck_sizes"]),
            "avg_deck_size": statistics.mean(stats["deck_sizes"]),
            "decks_with_sideboard": has_sb,
            "sideboard_pct": (has_sb / len(stats["deck_sizes"])) * 100,
            "avg_sideboard_size": statistics.mean(stats["sideboards"])
            if stats["sideboards"]
            else 0,
        }

    return results


def print_archetype_stats(archetype, stats):
    """Pretty print archetype statistics"""
    print(f"\n{'=' * 60}")
    print(f"{archetype}")
    print(f"{'=' * 60}")
    print(f"Sample: {stats['num_decks']} decks")
    print("\nDeck composition:")
    print(f"  Total cards:  {stats['deck_size']['median']:.0f} (median)")
    print(f"  Mainboard:    {stats['mainboard_size']['median']:.0f}")
    print(f"  Sideboard:    {stats['sideboard_size']['median']:.0f}")
    print(f"  Unique cards: {stats['unique_cards']['median']:.0f}")
    print(f"  Avg copies:   {stats['avg_copies_per_card']['median']:.1f}x per card")


def main():
    data_path = Path("../../data/processed/decks_with_metadata.jsonl")

    print("Deck Composition Statistics")
    print("=" * 60)
    print("Analyze deck structure patterns by archetype and format")
    print()

    # Archetype analysis
    print("Analyzing archetypes...")
    archetype_stats = analyze_deck_composition(data_path, min_decks=30)

    top_archetypes = sorted(archetype_stats.items(), key=lambda x: -x[1]["num_decks"])[:8]

    for archetype, stats in top_archetypes:
        print_archetype_stats(archetype, stats)

    # Format comparison
    print(f"\n{'=' * 60}")
    print("Format Comparison")
    print(f"{'=' * 60}")

    format_stats = compare_formats(data_path)

    for fmt in ["Modern", "Legacy", "Pauper", "cEDH", "Standard", "Vintage"]:
        if fmt in format_stats:
            stats = format_stats[fmt]
            print(f"\n{fmt}:")
            print(f"  Decks analyzed: {stats['num_decks']}")
            print(f"  Avg deck size:  {stats['avg_deck_size']:.0f} cards")
            print(
                f"  Has sideboard:  {stats['sideboard_pct']:.0f}% ({stats['decks_with_sideboard']} decks)"
            )
            if stats["avg_sideboard_size"] > 0:
                print(f"  Avg sideboard:  {stats['avg_sideboard_size']:.0f} cards")

    print(f"\n{'=' * 60}")
    print("Use Cases")
    print(f"{'=' * 60}")
    print("- Deck building guides: 'Typical Burn deck is 60 cards, 20 lands'")
    print("- Format comparison: 'Legacy decks average 60, Commander 100'")
    print("- Archetype insights: 'Affinity plays 55 unique cards (high variance)'")
    print("- Validation: Check if user's deck matches archetype norms")
    print("\nThis works because: frequency-based analysis of structure")


if __name__ == "__main__":
    main()
