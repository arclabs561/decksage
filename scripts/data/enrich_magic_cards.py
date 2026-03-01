#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Enrich Magic card attributes CSV with Scryfall rulings, keyword abilities,
creature types, and color identity strings.

Reads:
  - data/processed/card_attributes_magic_bulk.csv
  - data/raw/scryfall/rulings.json
  - data/raw/scryfall/oracle-cards.json

Writes:
  - data/processed/card_attributes_magic_enriched.csv

Usage:
    uv run scripts/data/enrich_magic_cards.py
    uv run scripts/data/enrich_magic_cards.py --output data/processed/card_attributes_magic_enriched.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

# Canonical MTG keyword abilities (comprehensive list)
KEYWORD_ABILITIES = [
    "Absorb", "Adapt", "Affinity", "Afflict", "Afterlife", "Aftermath",
    "Amass", "Amplify", "Annihilator", "Ascend", "Assist", "Aura swap",
    "Awaken", "Backup", "Banding", "Bargain", "Battalion", "Battle cry",
    "Bestow", "Blitz", "Bloodthirst", "Boast", "Bolster", "Bushido",
    "Buyback", "Cascade", "Casualty", "Champion", "Changeling", "Channel",
    "Cipher", "Cleave", "Companion", "Compleated", "Conjure", "Connive",
    "Conspire", "Convoke", "Corrupted", "Craft", "Crew", "Cumulative upkeep",
    "Cycling", "Dash", "Daybound", "Deathtouch", "Decayed", "Defender",
    "Delve", "Demonstrate", "Descend", "Detain", "Devoid", "Devour",
    "Discover", "Disturb", "Domain", "Double strike", "Dredge", "Echo",
    "Embalm", "Emerge", "Eminence", "Enchant", "Encore", "Enlist",
    "Enrage", "Entwine", "Epic", "Equip", "Escalate", "Escape",
    "Eternalize", "Evoke", "Evolve", "Exalted", "Exert", "Exploit",
    "Explore", "Extort", "Fabricate", "Fading", "Fear", "First strike",
    "Flanking", "Flash", "Flashback", "Flying", "Food", "Forecast",
    "Foretell", "For Mirrodin!", "Fortify", "Frenzy", "Friends forever",
    "Fuse", "Gift", "Goad", "Graft", "Gravestorm", "Haste", "Haunt",
    "Hexproof", "Hidden agenda", "Hideaway", "Horsemanship", "Impending",
    "Improvise", "Incubate", "Indestructible", "Infect", "Ingest",
    "Inspired", "Intimidate", "Investigate", "Jump-start", "Kicker",
    "Landfall", "Landwalk", "Level up", "Lifelink", "Living weapon",
    "Madness", "Magecraft", "Manifest", "Melee", "Menace", "Mentor",
    "Metalcraft", "Mill", "Miracle", "Modular", "Monstrosity", "Morph",
    "Mountainwalk", "Multikicker", "Mutate", "Myriad", "Nightbound",
    "Ninjutsu", "Offering", "Offspring", "Outlast", "Overload",
    "Pack tactics", "Partner", "Persist", "Phasing", "Plainswalk",
    "Poisonous", "Populate", "Proliferate", "Protection", "Prototype",
    "Provoke", "Prowess", "Prowl", "Radiance", "Raid", "Rally",
    "Rampage", "Ravenous", "Reach", "Read ahead", "Rebound", "Reconfigure",
    "Recover", "Reinforce", "Renown", "Replicate", "Retrace", "Revolt",
    "Riot", "Ripple", "Role", "Saddle", "Scavenge", "Scry",
    "Shadow", "Shelter", "Shroud", "Skulk", "Soulbond", "Soulshift",
    "Spectacle", "Spell mastery", "Splice", "Split second", "Squad",
    "Storm", "Strive", "Sunburst", "Support", "Surge", "Surveil",
    "Suspend", "Swampclandestine", "Swampwalk", "Threshold", "Token",
    "Toxic", "Training", "Trample", "Transfigure", "Transform",
    "Transmute", "Treasure", "Tribute", "Undaunted", "Undying",
    "Unearth", "Unleash", "Vanishing", "Vigilance", "Ward", "Wither",
]

# Build a case-insensitive lookup set
_KEYWORD_LOWER = {k.lower() for k in KEYWORD_ABILITIES}

COLOR_MAP = {"W": "W", "U": "U", "B": "B", "R": "R", "G": "G"}
COLOR_ORDER = "WUBRG"


def extract_keyword_abilities(oracle_text: str, keywords_col: str) -> list[str]:
    """Extract keyword abilities from oracle text and the keywords column."""
    found: set[str] = set()

    # From the keywords column (comma-separated)
    if keywords_col:
        for kw in keywords_col.split(","):
            kw_stripped = kw.strip()
            if kw_stripped.lower() in _KEYWORD_LOWER:
                found.add(kw_stripped)

    # From oracle text: check each keyword
    if oracle_text:
        text_lower = oracle_text.lower()
        for kw in KEYWORD_ABILITIES:
            if kw.lower() in text_lower:
                found.add(kw)

    # Sort by canonical order
    return sorted(found, key=lambda k: k.lower())


def extract_creature_types(type_line: str) -> list[str]:
    """Extract creature subtypes from the type line (after the em dash)."""
    if not type_line:
        return []
    # Type lines use an em dash or double dash to separate supertypes from subtypes
    for sep in ["\u2014", "—", "--", "-"]:
        if sep in type_line:
            subtypes_part = type_line.split(sep, 1)[1].strip()
            # Split on spaces, filter out empty
            types = [t.strip() for t in subtypes_part.split() if t.strip()]
            return types
    return []


def color_identity_str(colors: str) -> str:
    """Convert a colors string like '['W', 'U']' or 'WU' to a sorted WUBRG string."""
    if not colors:
        return "C"  # Colorless
    # Handle various formats
    found = []
    for c in COLOR_ORDER:
        if c in colors:
            found.append(c)
    return "".join(found) if found else "C"


def main():
    parser = argparse.ArgumentParser(description="Enrich Magic card attributes")
    parser.add_argument(
        "--input",
        default="data/processed/card_attributes_magic_bulk.csv",
        help="Input CSV path",
    )
    parser.add_argument(
        "--rulings",
        default="data/raw/scryfall/rulings.json",
        help="Scryfall rulings JSON path",
    )
    parser.add_argument(
        "--oracle-cards",
        default="data/raw/scryfall/oracle-cards.json",
        help="Scryfall oracle cards JSON path",
    )
    parser.add_argument(
        "--output",
        default="data/processed/card_attributes_magic_enriched.csv",
        help="Output CSV path",
    )
    parser.add_argument(
        "--max-rulings",
        type=int,
        default=3,
        help="Max rulings to include per card (default: 3)",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent.parent
    input_path = root / args.input
    rulings_path = root / args.rulings
    oracle_path = root / args.oracle_cards
    output_path = root / args.output

    # --- Load oracle cards: oracle_id -> card name ---
    print(f"Loading oracle cards from {oracle_path}...")
    with open(oracle_path) as f:
        oracle_cards = json.load(f)

    oracle_id_to_name: dict[str, str] = {}
    name_to_oracle_id: dict[str, str] = {}
    for card in oracle_cards:
        oid = card.get("oracle_id", "")
        name = card.get("name", "")
        if oid and name:
            oracle_id_to_name[oid] = name
            # Use lowercase for matching
            name_to_oracle_id[name.lower()] = oid

    print(f"  {len(oracle_id_to_name)} oracle cards loaded")

    # --- Load rulings: oracle_id -> list of ruling comments ---
    print(f"Loading rulings from {rulings_path}...")
    with open(rulings_path) as f:
        rulings_raw = json.load(f)

    rulings_by_oracle_id: dict[str, list[str]] = defaultdict(list)
    for ruling in rulings_raw:
        oid = ruling.get("oracle_id", "")
        comment = ruling.get("comment", "")
        if oid and comment:
            rulings_by_oracle_id[oid].append(comment)

    print(f"  {len(rulings_raw)} total rulings for {len(rulings_by_oracle_id)} cards")

    # --- Build rulings by card name (lowercase) ---
    rulings_by_name: dict[str, list[str]] = {}
    for oid, comments in rulings_by_oracle_id.items():
        name = oracle_id_to_name.get(oid, "")
        if name:
            rulings_by_name[name.lower()] = comments

    # --- Read input CSV ---
    print(f"Reading input CSV from {input_path}...")
    with open(input_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        input_fields = list(reader.fieldnames or [])
        rows = list(reader)
    print(f"  {len(rows)} cards loaded")

    # --- Enrich ---
    output_fields = input_fields + [
        "oracle_text_enriched",
        "keyword_abilities",
        "creature_types",
        "color_identity_str",
    ]

    cards_with_rulings = 0
    cards_with_keywords = 0
    cards_with_creature_types = 0

    for row in rows:
        name = row.get("name", "")
        oracle_text = row.get("oracle_text", "")
        type_line = row.get("type", "")
        colors = row.get("colors", "")
        keywords_col = row.get("keywords", "")

        # Rulings
        card_rulings = rulings_by_name.get(name.lower(), [])
        if card_rulings:
            top_rulings = card_rulings[: args.max_rulings]
            rulings_text = "\n".join(f"- {r}" for r in top_rulings)
            enriched = f"{oracle_text}\n---\nRulings:\n{rulings_text}" if oracle_text else f"Rulings:\n{rulings_text}"
            cards_with_rulings += 1
        else:
            enriched = oracle_text

        row["oracle_text_enriched"] = enriched

        # Keyword abilities
        kws = extract_keyword_abilities(oracle_text, keywords_col)
        row["keyword_abilities"] = ", ".join(kws)
        if kws:
            cards_with_keywords += 1

        # Creature types
        ctypes = extract_creature_types(type_line)
        row["creature_types"] = ", ".join(ctypes)
        if ctypes:
            cards_with_creature_types += 1

        # Color identity string
        row["color_identity_str"] = color_identity_str(colors)

    # --- Write output ---
    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Writing enriched CSV to {output_path}...")
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=output_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nEnrichment complete:")
    print(f"  Total cards: {len(rows)}")
    print(f"  Cards with rulings: {cards_with_rulings}")
    print(f"  Cards with keyword abilities: {cards_with_keywords}")
    print(f"  Cards with creature types: {cards_with_creature_types}")
    print(f"  Output: {output_path}")


if __name__ == "__main__":
    main()
