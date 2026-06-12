# /// script
# requires-python = ">=3.11"
# ///
"""Enrich Pokemon TCG card attributes from PokemonTCG/pokemon-tcg-data GitHub repo.

Fetches per-set JSON files from the GitHub repo (same backing data as pokemontcg.io),
extracts richer attributes than the base download script, and produces an enriched
CSV with additional columns: set_name, set_release_date, attacks_detail, abilities_detail.

The oracle_text is rebuilt to include type line, HP, full attack descriptions
(with costs and damage), ability text, weakness/resistance, and rules text.

Usage:
    uv run scripts/data/enrich_pokemon_cards.py --output data/processed/card_attributes_pokemon_enriched.csv
    uv run scripts/data/enrich_pokemon_cards.py --output out.csv --limit 5  # only 5 sets
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.request
from pathlib import Path


GITHUB_RAW = "https://raw.githubusercontent.com/PokemonTCG/pokemon-tcg-data/master"
GITHUB_API = "https://api.github.com/repos/PokemonTCG/pokemon-tcg-data/contents/cards/en"

POKEMON_TYPES = {
    "Fire",
    "Water",
    "Grass",
    "Lightning",
    "Psychic",
    "Fighting",
    "Darkness",
    "Metal",
    "Dragon",
    "Fairy",
    "Colorless",
}

SUBTYPE_KEYWORDS = {
    "Basic",
    "Stage 1",
    "Stage 2",
    "V",
    "VMAX",
    "VSTAR",
    "ex",
    "GX",
    "EX",
    "Mega",
    "BREAK",
    "Supporter",
    "Item",
    "Stadium",
    "Tool",
    "Restored",
    "Level-Up",
}


def fetch_json(url: str, *, timeout: int = 30, retries: int = 3) -> object:
    """Fetch JSON from a URL with retry logic."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "DeckSage/1.0")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            if attempt == retries - 1:
                raise
            wait = 2**attempt
            print(f"    Attempt {attempt + 1} failed: {e}. Retrying in {wait}s...")
            time.sleep(wait)
    raise RuntimeError("unreachable")


def parse_damage(damage_str: str | None) -> int:
    if not damage_str:
        return 0
    m = re.search(r"(\d+)", damage_str)
    return int(m.group(1)) if m else 0


def build_oracle_text(card: dict) -> str:
    """Build a rich oracle_text combining type line, HP, attacks, abilities, rules."""
    parts: list[str] = []

    # Type line
    supertype = card.get("supertype", "")
    subtypes = card.get("subtypes") or []
    types = card.get("types") or []
    type_line_parts = [supertype, *subtypes]
    if types:
        type_line_parts.append("-")
        type_line_parts.extend(types)
    hp = card.get("hp", "")
    if hp:
        type_line_parts.append(f"- HP {hp}")
    type_line = " ".join(type_line_parts).strip()
    if type_line:
        parts.append(type_line)

    # Abilities
    for ability in card.get("abilities") or []:
        ab_type = ability.get("type", "Ability")
        ab_name = ability.get("name", "")
        ab_text = ability.get("text", "")
        pieces = [f"[{ab_type}]"]
        if ab_name:
            pieces.append(f"{ab_name}:")
        if ab_text:
            pieces.append(ab_text)
        parts.append(" ".join(pieces))

    # Attacks
    for attack in card.get("attacks") or []:
        atk_cost = attack.get("cost") or []
        atk_name = attack.get("name", "")
        atk_dmg = attack.get("damage", "")
        atk_text = attack.get("text", "")
        cost_str = ",".join(atk_cost) if atk_cost else ""
        pieces = []
        if cost_str:
            pieces.append(f"[{cost_str}]")
        if atk_name:
            pieces.append(atk_name)
        if atk_dmg:
            pieces.append(f"({atk_dmg})")
        if atk_text:
            pieces.append(atk_text)
        parts.append(" ".join(pieces))

    # Weakness / Resistance / Retreat
    w_r_parts = []
    for w in card.get("weaknesses") or []:
        w_r_parts.append(f"Weakness: {w.get('type', '')} {w.get('value', '')}")
    for r in card.get("resistances") or []:
        w_r_parts.append(f"Resistance: {r.get('type', '')} {r.get('value', '')}")
    retreat = card.get("convertedRetreatCost", 0) or 0
    if retreat:
        w_r_parts.append(f"Retreat: {retreat}")
    if w_r_parts:
        parts.append(" | ".join(w_r_parts))

    # Rules
    for rule in card.get("rules") or []:
        parts.append(rule)

    return " | ".join(parts)


def format_attacks(attacks: list[dict]) -> str:
    """Compact representation of all attacks."""
    results = []
    for a in attacks:
        cost = ",".join(a.get("cost") or [])
        name = a.get("name", "")
        dmg = a.get("damage", "")
        results.append(f"{cost}:{name}:{dmg}")
    return " // ".join(results)


def format_abilities(abilities: list[dict]) -> str:
    """Compact representation of all abilities."""
    results = []
    for a in abilities:
        ab_type = a.get("type", "Ability")
        name = a.get("name", "")
        text = a.get("text", "")
        results.append(f"{ab_type}:{name}:{text}")
    return " // ".join(results)


def process_card(card: dict) -> dict:
    """Convert API card object to enriched CSV row."""
    supertype = card.get("supertype", "")
    subtypes = card.get("subtypes") or []
    types = card.get("types") or []
    attacks = card.get("attacks") or []
    weaknesses = card.get("weaknesses") or []
    resistances = card.get("resistances") or []
    abilities = card.get("abilities") or []

    type_str = " ".join([supertype, *subtypes]).strip()
    colors = [t for t in types if t in POKEMON_TYPES]

    cmc = 0
    if attacks:
        cmc = max((a.get("convertedEnergyCost") or len(a.get("cost", []))) for a in attacks)

    power = 0
    if attacks:
        power = max(parse_damage(a.get("damage")) for a in attacks)

    hp_raw = card.get("hp", "")
    hp_val = 0
    if hp_raw:
        m = re.search(r"(\d+)", str(hp_raw))
        if m:
            hp_val = int(m.group(1))
    toughness = hp_val if supertype == "Pok\u00e9mon" else 0

    weakness_type = weaknesses[0]["type"] if weaknesses else ""
    resistance_type = resistances[0]["type"] if resistances else ""

    kw = []
    for st in subtypes:
        if st in SUBTYPE_KEYWORDS:
            kw.append(st)
    if abilities:
        kw.append("has_ability")
    if weakness_type:
        kw.append(f"weak_{weakness_type}")
    if resistance_type:
        kw.append(f"resist_{resistance_type}")

    retreat = card.get("convertedRetreatCost", 0) or 0
    reg_mark = card.get("regulationMark", "")

    # Set info (enriched fields, injected before calling process_card)
    set_name = card.get("_set_name", "")
    set_release_date = card.get("_set_release_date", "")

    images = card.get("images") or {}
    image_url = images.get("large", "") or images.get("small", "")

    return {
        "name": card.get("name", ""),
        "type": type_str,
        "colors": ",".join(colors),
        "cmc": cmc,
        "rarity": card.get("rarity", ""),
        "power": power,
        "toughness": toughness,
        "keywords": ",".join(kw),
        "supertype": supertype,
        "subtypes": ",".join(subtypes),
        "hp": hp_val,
        "retreat_cost": retreat,
        "weakness_type": weakness_type,
        "resistance_type": resistance_type,
        "regulation_mark": reg_mark,
        "oracle_text": build_oracle_text(card),
        "image_url": image_url,
        "set_name": set_name,
        "set_release_date": set_release_date,
        "attacks_detail": format_attacks(attacks),
        "abilities_detail": format_abilities(abilities),
        # internal for dedup
        "_set_release": set_release_date,
        "_card_id": card.get("id", ""),
    }


FIELDNAMES = [
    "name",
    "type",
    "colors",
    "cmc",
    "rarity",
    "power",
    "toughness",
    "keywords",
    "supertype",
    "subtypes",
    "hp",
    "retreat_cost",
    "weakness_type",
    "resistance_type",
    "regulation_mark",
    "oracle_text",
    "image_url",
    # enriched columns
    "set_name",
    "set_release_date",
    "attacks_detail",
    "abilities_detail",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrich Pokemon card attributes from GitHub data")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/card_attributes_pokemon_enriched.csv"),
        help="Output CSV path",
    )
    parser.add_argument("--limit", type=int, default=0, help="Max sets to fetch (0 = all)")
    args = parser.parse_args()

    output_path: Path = args.output
    if not output_path.is_absolute():
        output_path = Path(__file__).resolve().parent.parent.parent / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Step 1: Fetch set metadata (release dates + names)
    print("Fetching set metadata...")
    sets_url = f"{GITHUB_RAW}/sets/en.json"
    sets_data = fetch_json(sets_url)
    set_info: dict[str, dict] = {}
    for s in sets_data:
        set_info[s["id"]] = {
            "name": s.get("name", ""),
            "releaseDate": s.get("releaseDate", "0000/00/00"),
        }
    print(f"  {len(set_info)} sets loaded.")

    # Step 2: List all set card files
    print("Listing card set files...")
    dir_listing = fetch_json(GITHUB_API)
    set_files = [f["name"] for f in dir_listing if f["name"].endswith(".json")]
    print(f"  {len(set_files)} set files found.")

    if args.limit:
        set_files = set_files[: args.limit]
        print(f"  Limited to {args.limit} sets.")

    # Step 3: Fetch all card data
    print("Fetching card data from all sets...")
    all_rows: list[dict] = []
    total_raw = 0

    for i, filename in enumerate(set_files, 1):
        set_id = filename.replace(".json", "")
        url = f"{GITHUB_RAW}/cards/en/{filename}"
        try:
            cards = fetch_json(url)
        except Exception as e:
            print(f"  WARN: Failed to fetch {filename}: {e}")
            continue

        si = set_info.get(set_id, {"name": "", "releaseDate": "0000/00/00"})
        count = len(cards)
        total_raw += count

        for card in cards:
            # Inject set info into card dict for process_card
            card["_set_name"] = si["name"]
            card["_set_release_date"] = si["releaseDate"]
            row = process_card(card)
            all_rows.append(row)

        if i % 20 == 0 or i == len(set_files):
            print(
                f"  [{i}/{len(set_files)}] {filename}: {count} cards (running total: {total_raw})"
            )

        time.sleep(0.05)

    print(f"\nFetched {total_raw} total card records from {len(set_files)} sets.")

    # Deduplicate by name (keep latest set printing)
    by_name: dict[str, dict] = {}
    for row in all_rows:
        name = row["name"]
        if not name:
            continue
        key = (row["_set_release"], row["_card_id"])
        if name not in by_name:
            by_name[name] = row
        else:
            existing_key = (by_name[name]["_set_release"], by_name[name]["_card_id"])
            if key > existing_key:
                by_name[name] = row

    print(f"Unique card names after dedup: {len(by_name)}")

    # Write CSV
    rows = []
    for name in sorted(by_name.keys()):
        row = by_name[name]
        clean = {k: row[k] for k in FIELDNAMES}
        rows.append(clean)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nSaved {len(rows)} cards to {output_path}")

    # Summary stats
    supertypes: dict[str, int] = {}
    has_attacks = 0
    has_ability = 0
    has_set_info = 0

    for row in rows:
        st = row["supertype"]
        supertypes[st] = supertypes.get(st, 0) + 1
        if row["power"] > 0:
            has_attacks += 1
        if "has_ability" in row["keywords"]:
            has_ability += 1
        if row["set_name"]:
            has_set_info += 1

    print("\n--- Enrichment Summary ---")
    print(f"Total unique cards: {len(rows)}")
    print(f"Cards with attacks (power > 0): {has_attacks}")
    print(f"Cards with abilities: {has_ability}")
    print(f"Cards with set info: {has_set_info}")
    print("New columns: set_name, set_release_date, attacks_detail, abilities_detail")
    print("\nBy supertype:")
    for st, count in sorted(supertypes.items(), key=lambda x: -x[1]):
        print(f"  {st}: {count}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
