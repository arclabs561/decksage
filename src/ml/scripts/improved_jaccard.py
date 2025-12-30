#!/usr/bin/env python3
"""
Improved Jaccard with land filtering.

Problem: Basic lands (Mountain, Island) appear in every deck and dominate similarity.
Solution: Filter out lands before computing similarity.
"""

from collections import defaultdict

import pandas as pd

# Common basics and fetches to filter
LANDS = {
    "Plains",
    "Island",
    "Swamp",
    "Mountain",
    "Forest",
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
    "Prismatic Vista",
    "Fabled Passage",
    "Evolving Wilds",
    "Terramorphic Expanse",
    "Command Tower",
    "City of Brass",
    "Mana Confluence",
}


def improved_jaccard(pairs_csv):
    """Jaccard with land filtering"""
    df = pd.read_csv(pairs_csv)

    # Build adjacency, excluding lands
    adj = defaultdict(set)
    for _, row in df.iterrows():
        c1, c2 = row["NAME_1"], row["NAME_2"]

        # Skip if either is a land
        if c1 in LANDS or c2 in LANDS:
            continue

        adj[c1].add(c2)
        adj[c2].add(c1)

    def jaccard_similarity(card1, card2):
        n1, n2 = adj[card1], adj[card2]
        if not n1 or not n2:
            return 0.0
        return len(n1 & n2) / len(n1 | n2)

    def find_similar(card, k=10):
        if card not in adj:
            return []
        similarities = []
        for other in adj:
            if other != card:
                sim = jaccard_similarity(card, other)
                similarities.append((other, sim))
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:k]

    return find_similar


if __name__ == "__main__":
    find_similar = improved_jaccard("../backend/pairs_500decks.csv")

    queries = ["Lightning Bolt", "Brainstorm", "Dark Ritual"]

    print("Improved Jaccard (lands filtered):\n")
    for query in queries:
        results = find_similar(query, k=5)
        print(f"{query}:")
        for i, (card, score) in enumerate(results, 1):
            print(f"  {i}. {card:40s} {score:.4f}")
        print()
