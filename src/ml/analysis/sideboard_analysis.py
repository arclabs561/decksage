#!/usr/bin/env python3
"""
Sideboard Analysis Tool

Use case: "What do people sideboard in Burn decks?" or "Against what matchups?"

This works because it uses co-occurrence's strength: analyzing card frequency
in specific contexts (sideboard vs mainboard, archetype-specific).
"""

import json
from collections import Counter, defaultdict
from pathlib import Path


def analyze_sideboard_by_archetype(jsonl_path, min_decks=20):
    """Analyze sideboard card frequencies by archetype"""

    archetype_sideboards = defaultdict(list)

    with open(jsonl_path) as f:
        for line in f:
            deck = json.loads(line)
            archetype = deck.get("archetype", "unknown")

            # Extract sideboard cards
            sideboard_cards = []
            for card_entry in deck.get("cards", []):
                if card_entry.get("partition") == "Sideboard":
                    sideboard_cards.append(card_entry["name"])

            if sideboard_cards:
                archetype_sideboards[archetype].append(sideboard_cards)

    # Analyze each archetype
    results = {}

    for archetype, sideboards in archetype_sideboards.items():
        if len(sideboards) < min_decks:
            continue

        # Count card occurrences in sideboards
        card_counts = Counter()
        for sideboard in sideboards:
            unique_cards = set(sideboard)
            card_counts.update(unique_cards)

        # Calculate percentages
        num_decks = len(sideboards)
        common_sb_cards = {}
        for card, count in card_counts.most_common(30):
            percentage = (count / num_decks) * 100
            common_sb_cards[card] = {
                "count": count,
                "percentage": percentage,
                "total_decks": num_decks,
            }

        results[archetype] = {"num_decks_with_sb": num_decks, "common_cards": common_sb_cards}

    return results


def analyze_mainboard_vs_sideboard(jsonl_path):
    """Compare mainboard vs sideboard card usage across all decks"""

    mainboard_cards = Counter()
    sideboard_cards = Counter()
    sb_only_cards = Counter()  # Cards that appear in SB but not MB

    with open(jsonl_path) as f:
        for line in f:
            deck = json.loads(line)

            mb_cards = set()
            sb_cards = set()

            for card_entry in deck.get("cards", []):
                card_name = card_entry["name"]
                partition = card_entry.get("partition", "Main")

                if partition == "Sideboard":
                    sb_cards.add(card_name)
                else:
                    mb_cards.add(card_name)

            mainboard_cards.update(mb_cards)
            sideboard_cards.update(sb_cards)

            # Cards in SB but not MB for this deck
            sb_only = sb_cards - mb_cards
            sb_only_cards.update(sb_only)

    return {
        "mainboard": mainboard_cards,
        "sideboard": sideboard_cards,
        "sideboard_only": sb_only_cards,
    }


def print_sideboard_analysis(archetype, data):
    """Pretty print sideboard analysis"""
    print(f"\n{'=' * 60}")
    print(f"{archetype} - Sideboard Analysis")
    print(f"{'=' * 60}")
    print(f"Decks with sideboard: {data['num_decks_with_sb']}")
    print("\nMost common sideboard cards:")

    for card, stats in list(data["common_cards"].items())[:15]:
        print(f"  {stats['percentage']:5.1f}%  {card}")


def main():
    data_path = Path("../../data/processed/decks_with_metadata.jsonl")

    print("Sideboard Analysis Tool")
    print("=" * 60)
    print("Analyzes what cards players sideboard in different archetypes")
    print()

    # Analyze by archetype
    print("Loading data...")
    results = analyze_sideboard_by_archetype(data_path, min_decks=30)

    # Show top archetypes
    top_archetypes = sorted(results.items(), key=lambda x: -x[1]["num_decks_with_sb"])[:5]

    for archetype, data in top_archetypes:
        print_sideboard_analysis(archetype, data)

    # Mainboard vs Sideboard comparison
    print(f"\n{'=' * 60}")
    print("Mainboard vs Sideboard Card Analysis")
    print(f"{'=' * 60}")

    comparison = analyze_mainboard_vs_sideboard(data_path)

    print("\nTop sideboard-only cards (never in mainboard):")
    for card, count in comparison["sideboard_only"].most_common(20):
        print(f"  {count:4d} decks: {card}")

    print(f"\n{'=' * 60}")
    print("Insights")
    print(f"{'=' * 60}")
    print("This tool works because:")
    print("- Uses partition data (Main vs Sideboard)")
    print("- Frequency analysis shows what people actually board")
    print("- Archetype-specific reveals strategic choices")
    print("- No similarity required - just composition stats")
    print("\nUse cases:")
    print("- 'What should I sideboard in Burn?'")
    print("- 'What hate cards are popular against Affinity?'")
    print("- 'What's the sideboard meta for Modern?'")


if __name__ == "__main__":
    main()
