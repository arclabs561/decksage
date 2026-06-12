#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "requests>=2.31",
# ]
# ///
"""
Download Yu-Gi-Oh card attributes from YGOProDeck API and save as CSV.

Produces a CSV compatible with train_graphsage.py's card attribute feature
loader. Maps YGO-specific fields (attribute, level/rank/linkval, ATK/DEF)
to the generic columns (colors, cmc, power, toughness, keywords).

Output: data/processed/card_attributes_yugioh.csv

Usage:
    uv run scripts/data/download_yugioh_card_attributes.py
    # or:
    PYTHONPATH=src .venv/bin/python scripts/data/download_yugioh_card_attributes.py
"""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from pathlib import Path

import requests


API_URL = "https://db.ygoprodeck.com/api/v7/cardinfo.php?misc=yes"

OUTPUT_PATH = Path("data/processed/card_attributes_yugioh.csv")

# Keywords to text-mine from card descriptions
TEXT_MINE_KEYWORDS = [
    "Quick Effect",
    "Once per turn",
    "negate",
    "destroy",
    "banish",
    "search",
    "Special Summon",
    "draw",
    "discard",
    "send to the GY",
]

# Compile case-insensitive patterns (except "Quick Effect" / "Once per turn"
# which are conventionally capitalized in YGO text)
KEYWORD_PATTERNS = [(kw, re.compile(re.escape(kw), re.IGNORECASE)) for kw in TEXT_MINE_KEYWORDS]

CSV_COLUMNS = [
    "name",
    "type",
    "colors",
    "cmc",
    "rarity",
    "power",
    "toughness",
    "keywords",
    "attribute",
    "race",
    "archetype",
    "oracle_text",
    "image_url",
]


def fetch_cards() -> list[dict]:
    """Download all cards from YGOProDeck API."""
    print(f"Fetching cards from {API_URL} ...")
    resp = requests.get(API_URL, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    cards = data.get("data", [])
    print(f"  Received {len(cards)} cards")
    return cards


def most_common_rarity(card: dict) -> str:
    """Extract the most common rarity from card_sets entries."""
    sets = card.get("card_sets") or []
    if not sets:
        return "common"
    rarities = [s.get("set_rarity", "Common") for s in sets if s.get("set_rarity")]
    if not rarities:
        return "common"
    # Normalize to lowercase
    counter = Counter(r.strip().lower() for r in rarities)
    return counter.most_common(1)[0][0]


def extract_level(card: dict) -> str:
    """Extract level/rank/linkval as the CMC equivalent."""
    # Link monsters use linkval
    if "linkval" in card and card["linkval"] is not None:
        return str(card["linkval"])
    # Xyz monsters use rank (stored in 'level' field by API, but let's check)
    if "level" in card and card["level"] is not None:
        return str(card["level"])
    return ""


def extract_keywords(card: dict) -> list[str]:
    """Build keyword list from type, race, and text-mined desc patterns."""
    keywords = []

    # From card type -- split into individual type tokens
    card_type = card.get("type", "")
    if card_type:
        keywords.append(card_type)

    # From race (monster subtype)
    race = card.get("race", "")
    if race:
        keywords.append(race)

    # Text-mine the description
    desc = card.get("desc", "")
    if desc:
        for kw, pattern in KEYWORD_PATTERNS:
            if pattern.search(desc):
                keywords.append(kw)

    return keywords


def map_attribute_to_colors(attribute: str | None) -> str:
    """Map YGO attribute to a single-letter color code (like WUBRG for Magic).

    Mapping:
      LIGHT  -> L
      DARK   -> D
      EARTH  -> E
      WATER  -> W
      FIRE   -> F
      WIND   -> N  (W is taken by WATER)
      DIVINE -> V
    """
    if not attribute:
        return ""
    mapping = {
        "LIGHT": "L",
        "DARK": "D",
        "EARTH": "E",
        "WATER": "W",
        "FIRE": "F",
        "WIND": "N",
        "DIVINE": "V",
    }
    return mapping.get(attribute.upper(), "")


def process_card(card: dict) -> dict:
    """Convert a single API card object to our CSV row."""
    name = card.get("name", "").strip()
    card_type = card.get("type", "")
    attribute = card.get("attribute") or ""
    race = card.get("race") or ""
    archetype = card.get("archetype") or ""

    colors = map_attribute_to_colors(attribute)
    cmc = extract_level(card)
    rarity = most_common_rarity(card)

    # ATK/DEF -- only for monsters
    atk = card.get("atk")
    defense = card.get("def")
    power = str(atk) if atk is not None else ""
    toughness = str(defense) if defense is not None else ""

    # For spell/trap cards, clear power/toughness
    if "Monster" not in card_type:
        power = ""
        toughness = ""

    keywords = extract_keywords(card)

    # Full card description (oracle text equivalent)
    oracle_text = card.get("desc", "").strip()

    # Image URL (first image from card_images array)
    image_url = ""
    card_images = card.get("card_images", [])
    if card_images:
        image_url = card_images[0].get("image_url", "")

    return {
        "name": name,
        "type": card_type,
        "colors": colors,
        "cmc": cmc,
        "rarity": rarity,
        "power": power,
        "toughness": toughness,
        "keywords": ",".join(keywords),
        "attribute": attribute,
        "race": race,
        "archetype": archetype,
        "oracle_text": oracle_text,
        "image_url": image_url,
    }


def print_summary(rows: list[dict]) -> None:
    """Print summary statistics."""
    print(f"\n{'=' * 60}")
    print(f"Summary: {len(rows)} cards total")
    print(f"{'=' * 60}")

    # Type distribution
    type_counts = Counter(r["type"] for r in rows)
    print(f"\nTop card types ({len(type_counts)} unique):")
    for t, c in type_counts.most_common(15):
        print(f"  {t:40s} {c:>5d}")

    # Attribute distribution
    attr_counts = Counter(r["attribute"] for r in rows if r["attribute"])
    print(f"\nAttributes ({len(attr_counts)} unique):")
    for a, c in attr_counts.most_common():
        print(f"  {a:20s} {c:>5d}")

    # Rarity distribution
    rarity_counts = Counter(r["rarity"] for r in rows)
    print(f"\nTop rarities ({len(rarity_counts)} unique):")
    for r, c in rarity_counts.most_common(10):
        print(f"  {r:40s} {c:>5d}")

    # Race distribution
    race_counts = Counter(r["race"] for r in rows if r["race"])
    print(f"\nTop races/subtypes ({len(race_counts)} unique):")
    for r, c in race_counts.most_common(15):
        print(f"  {r:30s} {c:>5d}")

    # Keyword frequency (text-mined)
    kw_counts: Counter = Counter()
    for row in rows:
        for kw in row["keywords"].split(","):
            kw = kw.strip()
            if kw in {k for k, _ in KEYWORD_PATTERNS}:
                kw_counts[kw] += 1
    print("\nText-mined keyword frequencies:")
    for k, c in kw_counts.most_common():
        print(f"  {k:30s} {c:>5d}")

    # Cards with archetypes
    with_arch = sum(1 for r in rows if r["archetype"])
    print(f"\nCards with archetype: {with_arch}/{len(rows)} ({with_arch / len(rows) * 100:.1f}%)")

    # Level/CMC distribution
    level_counts = Counter()
    for r in rows:
        if r["cmc"]:
            level_counts[int(r["cmc"])] += 1
    print("\nLevel distribution (monsters):")
    for lv in sorted(level_counts):
        print(f"  Level {lv:2d}: {level_counts[lv]:>5d}")


def main() -> int:
    cards = fetch_cards()

    rows = [process_card(c) for c in cards]

    # Remove any cards with empty names (shouldn't happen, but be safe)
    rows = [r for r in rows if r["name"]]

    # Ensure output directory exists
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} rows to {OUTPUT_PATH}")

    print_summary(rows)

    return 0


if __name__ == "__main__":
    sys.exit(main())
