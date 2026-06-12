#!/usr/bin/env python3
"""
Build card database from Scryfall data.

Extract: name, type_line, colors, cmc for all cards.
"""

import json
import subprocess


def build_card_database():
    """Extract card metadata from Scryfall"""
    print("Extracting Scryfall card data...")

    # Use dataset cat to get all cards
    cmd = [
        "../backend/dataset",
        "cat",
        "magic/scryfall",
        "--bucket",
        "file://../backend/data-full",
        "--section",
        "cards",
    ]

    result = subprocess.run(cmd, check=False, cwd=".", capture_output=True, text=True)

    card_db = {}
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue  # Skip malformed JSON lines

        try:
            card = data.get("card", {})
            name = card.get("name")
            type_line = card.get("type_line", "")

            if name:
                card_db[name] = {
                    "type_line": type_line,
                    "colors": card.get("colors", []),
                    "cmc": card.get("cmc", 0),
                    "is_land": "Land" in type_line,
                    "is_creature": "Creature" in type_line,
                    "is_instant": "Instant" in type_line,
                    "is_sorcery": "Sorcery" in type_line,
                }
        except (KeyError, TypeError) as e:
            print(f"Warning: Skipping card {name if 'name' in locals() else 'unknown'}: {e}")
            continue

    # Save
    with open("scryfall_card_db.json", "w") as f:
        json.dump(card_db, f, indent=2)

    print(f"✓ Built database: {len(card_db):,} cards")

    # Stats
    lands = sum(1 for c in card_db.values() if c["is_land"])
    creatures = sum(1 for c in card_db.values() if c["is_creature"])
    instants = sum(1 for c in card_db.values() if c["is_instant"])
    sorceries = sum(1 for c in card_db.values() if c["is_sorcery"])

    print(f"  Lands: {lands:,}")
    print(f"  Creatures: {creatures:,}")
    print(f"  Instants: {instants:,}")
    print(f"  Sorceries: {sorceries:,}")

    return card_db


if __name__ == "__main__":
    db = build_card_database()

    # Test
    if "Lightning Bolt" in db:
        print("\nLightning Bolt metadata:")
        print(json.dumps(db["Lightning Bolt"], indent=2))
