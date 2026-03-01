#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""
Enrich Yu-Gi-Oh! card attributes CSV with data from YGOProDeck bulk API.

Downloads the full card database from YGOProDeck (if not cached locally),
then enriches the existing card_attributes_yugioh.csv with:
  - atk, def_stat, level_rank_link (Level/Rank/Link rating)
  - card_category (Monster/Spell/Trap)
  - monster_type (Effect/Fusion/Synchro/XYZ/Link/Pendulum/Normal/...)
  - attribute (DARK/LIGHT/EARTH/WATER/FIRE/WIND/DIVINE)
  - race (Spellcaster/Dragon/Warrior/...)
  - archetype
  - pendulum_scale (for Pendulum monsters)
  - link_markers (for Link monsters)
  - oracle_text_enriched (effect text, with pend/monster split for Pendulums)

Reads:
  - data/processed/card_attributes_yugioh.csv
  - data/raw/ygoprodeck/cardinfo.json (downloaded if missing)

Writes:
  - data/processed/card_attributes_yugioh_enriched.csv

Usage:
    uv run scripts/data/enrich_yugioh_cards.py
    uv run scripts/data/enrich_yugioh_cards.py --output data/processed/card_attributes_yugioh_enriched.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import httpx

API_URL = "https://db.ygoprodeck.com/api/v7/cardinfo.php"


def download_cardinfo(dest: Path) -> None:
    """Download the full YGOProDeck card database."""
    print(f"Downloading YGOProDeck card database to {dest}...")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=120) as client:
        resp = client.get(API_URL)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
    print(f"  Downloaded {dest.stat().st_size / 1_000_000:.1f} MB")


def classify_monster_type(card_type: str) -> str:
    """Extract the monster sub-type from the full type string.

    Examples:
      'Effect Monster' -> 'Effect'
      'Synchro Tuner Monster' -> 'Synchro Tuner'
      'Link Monster' -> 'Link'
      'Pendulum Effect Fusion Monster' -> 'Pendulum Fusion'
    """
    if "Monster" not in card_type:
        return ""
    # Remove 'Monster' suffix and clean up
    base = card_type.replace("Monster", "").strip()
    # Collapse whitespace
    return " ".join(base.split()) if base else "Normal"


def classify_card_category(card_type: str) -> str:
    """Classify into Monster/Spell/Trap."""
    if "Monster" in card_type:
        return "Monster"
    elif "Spell" in card_type:
        return "Spell"
    elif "Trap" in card_type:
        return "Trap"
    elif "Token" in card_type:
        return "Token"
    return card_type


def build_oracle_text_enriched(card: dict) -> str:
    """Build an enriched oracle text combining all relevant text fields."""
    parts = []

    # For Pendulum monsters, include both pendulum and monster effects
    pend_desc = card.get("pend_desc", "")
    monster_desc = card.get("monster_desc", "")

    if pend_desc and monster_desc:
        parts.append(f"[Pendulum Effect]\n{pend_desc}")
        parts.append(f"[Monster Effect]\n{monster_desc}")
    else:
        desc = card.get("desc", "")
        if desc:
            parts.append(desc)

    # Add type/stat summary line for embedding context
    stat_parts = []
    card_type = card.get("type", "")
    if "Monster" in card_type:
        atk = card.get("atk")
        def_val = card.get("def")
        level = card.get("level")
        linkval = card.get("linkval")
        attribute = card.get("attribute", "")
        race = card.get("race", "")

        if race:
            stat_parts.append(race)
        if attribute:
            stat_parts.append(attribute)
        if linkval is not None:
            stat_parts.append(f"Link-{linkval}")
        elif level is not None:
            if "XYZ" in card_type or "Xyz" in card_type:
                stat_parts.append(f"Rank {level}")
            else:
                stat_parts.append(f"Level {level}")
        if atk is not None:
            stat_parts.append(f"ATK {atk}")
        if def_val is not None:
            stat_parts.append(f"DEF {def_val}")

    if stat_parts:
        parts.append("---\n" + " / ".join(stat_parts))

    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description="Enrich YGO card attributes")
    parser.add_argument(
        "--input",
        default="data/processed/card_attributes_yugioh.csv",
        help="Input CSV path",
    )
    parser.add_argument(
        "--cardinfo",
        default="data/raw/ygoprodeck/cardinfo.json",
        help="YGOProDeck cardinfo.json path",
    )
    parser.add_argument(
        "--output",
        default="data/processed/card_attributes_yugioh_enriched.csv",
        help="Output CSV path",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent.parent
    input_path = root / args.input
    cardinfo_path = root / args.cardinfo
    output_path = root / args.output

    # --- Download if needed ---
    if not cardinfo_path.exists():
        download_cardinfo(cardinfo_path)

    # --- Load YGOProDeck data: name -> card dict ---
    print(f"Loading YGOProDeck data from {cardinfo_path}...")
    with open(cardinfo_path) as f:
        raw = json.load(f)
    api_cards = raw.get("data", raw) if isinstance(raw, dict) else raw

    # Index by lowercase name
    api_by_name: dict[str, dict] = {}
    for card in api_cards:
        name = card.get("name", "")
        if name:
            api_by_name[name.lower()] = card
    print(f"  {len(api_by_name)} API cards indexed")

    # --- Read input CSV ---
    print(f"Reading input CSV from {input_path}...")
    with open(input_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        input_fields = list(reader.fieldnames or [])
        rows = list(reader)
    print(f"  {len(rows)} cards loaded")

    # --- Define enriched columns ---
    new_cols = [
        "atk",
        "def_stat",
        "level_rank_link",
        "card_category",
        "monster_type",
        "attribute_enriched",
        "race_enriched",
        "archetype_enriched",
        "pendulum_scale",
        "link_markers",
        "oracle_text_enriched",
    ]
    output_fields = input_fields + new_cols

    # --- Enrich ---
    matched = 0
    unmatched_names = []

    for row in rows:
        name = row.get("name", "")
        api_card = api_by_name.get(name.lower())

        if api_card:
            matched += 1
            card_type = api_card.get("type", "")

            row["atk"] = str(api_card["atk"]) if api_card.get("atk") is not None else ""
            row["def_stat"] = str(api_card["def"]) if api_card.get("def") is not None else ""

            # Level/Rank/Link
            if api_card.get("linkval") is not None:
                row["level_rank_link"] = str(api_card["linkval"])
            elif api_card.get("level") is not None:
                row["level_rank_link"] = str(api_card["level"])
            else:
                row["level_rank_link"] = ""

            row["card_category"] = classify_card_category(card_type)
            row["monster_type"] = classify_monster_type(card_type)
            row["attribute_enriched"] = api_card.get("attribute", "") or ""
            row["race_enriched"] = api_card.get("race", "") or ""
            row["archetype_enriched"] = api_card.get("archetype", "") or ""
            row["pendulum_scale"] = str(api_card["scale"]) if api_card.get("scale") is not None else ""
            markers = api_card.get("linkmarkers", [])
            row["link_markers"] = ", ".join(markers) if markers else ""
            row["oracle_text_enriched"] = build_oracle_text_enriched(api_card)
        else:
            unmatched_names.append(name)
            # Fill with empty
            for col in new_cols:
                row[col] = ""
            # Still generate card_category from existing type column
            existing_type = row.get("type", "")
            row["card_category"] = classify_card_category(existing_type)
            row["monster_type"] = classify_monster_type(existing_type)

    # --- Stats ---
    categories = {}
    monster_types = {}
    attributes = {}
    for row in rows:
        cat = row.get("card_category", "")
        if cat:
            categories[cat] = categories.get(cat, 0) + 1
        mt = row.get("monster_type", "")
        if mt:
            monster_types[mt] = monster_types.get(mt, 0) + 1
        attr = row.get("attribute_enriched", "")
        if attr:
            attributes[attr] = attributes.get(attr, 0) + 1

    # --- Write output ---
    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Writing enriched CSV to {output_path}...")
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=output_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nEnrichment complete:")
    print(f"  Total cards: {len(rows)}")
    print(f"  Matched to API: {matched}")
    print(f"  Unmatched: {len(unmatched_names)}")
    if unmatched_names[:5]:
        print(f"  Sample unmatched: {unmatched_names[:5]}")

    print(f"\n  Card categories:")
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"    {cat}: {count}")

    print(f"\n  Top monster types:")
    for mt, count in sorted(monster_types.items(), key=lambda x: -x[1])[:10]:
        print(f"    {mt}: {count}")

    print(f"\n  Attributes:")
    for attr, count in sorted(attributes.items(), key=lambda x: -x[1]):
        print(f"    {attr}: {count}")

    print(f"\n  Output: {output_path}")


if __name__ == "__main__":
    main()
