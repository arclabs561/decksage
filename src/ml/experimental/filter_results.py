#!/usr/bin/env python3
"""
Result filtering to remove obviously bad predictions.

Issues found:
1. Jaccard returns basic lands (Mountain, Island)
2. Node2Vec sometimes returns completely wrong types
3. Need: Card type filtering

Quick fix: Hardcoded filter lists
Proper fix: Use Scryfall type_line metadata
"""

# Cards that should never be similarity results (too generic)
FILTER_LIST = {
    # Basic lands
    "Plains",
    "Island",
    "Swamp",
    "Mountain",
    "Forest",
    # Common fetches
    "Arid Mesa",
    "Scalding Tarn",
    "Polluted Delta",
    "Verdant Catacombs",
    "Marsh Flats",
    "Misty Rainforest",
    "Bloodstained Mire",
    "Wooded Foothills",
    "Flooded Strand",
    "Windswept Heath",
    # Shocklands (too common)
    "Sacred Foundry",
    "Steam Vents",
    "Watery Grave",
    "Overgrown Tomb",
    "Temple Garden",
    "Godless Shrine",
    "Stomping Ground",
    "Blood Crypt",
    "Breeding Pool",
    "Hallowed Fountain",
    # Generic utility lands
    "Command Tower",
    "Path of Ancestry",
    "City of Brass",
    "Mana Confluence",
    "Exotic Orchard",
    "Reflecting Pool",
    "Forbidden Orchard",
}


def filter_predictions(predictions, query_card=None):
    """Filter out generic cards"""
    filtered = []

    for card, score in predictions:
        # Skip if in filter list
        if card in FILTER_LIST:
            continue

        # Skip if same as query (shouldn't happen but just in case)
        if card == query_card:
            continue

        filtered.append((card, score))

    return filtered


def test_filtering():
    """Test the filter"""
    test_cases = [
        (
            "Lightning Bolt",
            [
                ("Mountain", 0.69),
                ("Chain Lightning", 0.85),
                ("Arid Mesa", 0.66),
                ("Fireblast", 0.83),
            ],
        )
    ]

    for query, predictions in test_cases:
        print(f"{query}:")
        print(f"  Before: {[c for c, _ in predictions]}")
        filtered = filter_predictions(predictions, query)
        print(f"  After:  {[c for c, _ in filtered]}")
        print()


if __name__ == "__main__":
    test_filtering()
