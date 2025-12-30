#!/usr/bin/env python3
"""
Quick hack: Extract card types from our deck data.

Instead of waiting for Scryfall, parse type info from what we have.
"""

import json
from collections import defaultdict

import pandas as pd


def extract_card_types_from_decks(data_dir):
    """Extract card types by analyzing deck JSONs"""
    # In MTG JSON, we might have type info embedded
    # For now, simple heuristic:
    # - If appears with many other cards → likely spell/creature
    # - If appears in almost ALL decks → likely land

    df = pd.read_csv("../backend/pairs_500decks.csv")

    # Count how many unique cards each card appears with
    connections = defaultdict(set)
    deck_count = defaultdict(int)

    for _, row in df.iterrows():
        c1, c2 = row["NAME_1"], row["NAME_2"]
        connections[c1].add(c2)
        connections[c2].add(c1)
        deck_count[c1] += 1
        deck_count[c2] += 1

    # Heuristic: If appears in >80% of decks, probably a land
    total_decks = 500  # We know this
    likely_lands = set()

    for card, count in deck_count.items():
        if count > total_decks * 0.6:  # In 60%+ of decks
            likely_lands.add(card)

    # Save
    card_types = {}
    for card in connections:
        if card in likely_lands:
            card_types[card] = "Land"
        else:
            card_types[card] = "Spell/Creature"  # Can't distinguish without metadata

    with open("card_types_inferred.json", "w") as f:
        json.dump(card_types, f, indent=2)

    print(f"✓ Inferred types for {len(card_types):,} cards")
    print(f"  Likely lands: {len(likely_lands)}")
    print("\nTop likely lands:")
    for card in sorted(likely_lands)[:20]:
        print(f"  - {card}")

    return card_types


if __name__ == "__main__":
    card_types = extract_card_types_from_decks("../backend/data-full/games/magic")
