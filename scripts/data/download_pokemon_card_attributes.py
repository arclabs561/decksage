# /// script
# requires-python = ">=3.11"
# ///
"""Download all Pokemon TCG card attributes from the PokemonTCG/pokemon-tcg-data
GitHub repository.

Fetches per-set JSON files from the GitHub repo (the same data that backed
pokemontcg.io), deduplicates by card name (keeping the latest set printing),
and saves a CSV matching the format expected by train_graphsage.py's
load_card_features.

Output: data/processed/card_attributes_pokemon.csv

Usage:
    uv run scripts/data/download_pokemon_card_attributes.py
    # or
    python scripts/data/download_pokemon_card_attributes.py
"""

from __future__ import annotations

import csv
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

# GitHub raw content base for the pokemon-tcg-data repo
GITHUB_RAW = "https://raw.githubusercontent.com/PokemonTCG/pokemon-tcg-data/master"
GITHUB_API = "https://api.github.com/repos/PokemonTCG/pokemon-tcg-data/contents/cards/en"

# Pokemon types -> color mapping for the "colors" column
POKEMON_TYPES = {
    "Fire", "Water", "Grass", "Lightning", "Psychic",
    "Fighting", "Darkness", "Metal", "Dragon", "Fairy", "Colorless",
}

# Keywords to extract from subtypes
SUBTYPE_KEYWORDS = {
    "Basic", "Stage 1", "Stage 2", "V", "VMAX", "VSTAR",
    "ex", "GX", "EX", "Mega", "BREAK", "Supporter", "Item",
    "Stadium", "Tool", "Restored", "Level-Up",
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
            wait = 2 ** attempt
            print(f"    Attempt {attempt + 1} failed: {e}. Retrying in {wait}s...")
            time.sleep(wait)
    raise RuntimeError("unreachable")


def parse_damage(damage_str: str | None) -> int:
    """Extract numeric damage from a damage string like '120', '30+', '10x'."""
    if not damage_str:
        return 0
    m = re.search(r"(\d+)", damage_str)
    return int(m.group(1)) if m else 0


def parse_attack_cost(attack: dict) -> int:
    """Get the converted energy cost of an attack."""
    cost = attack.get("convertedEnergyCost")
    if cost is not None:
        return int(cost)
    # Fallback: count the cost list
    return len(attack.get("cost", []))


def process_card(card: dict, set_release: str) -> dict:
    """Convert a raw card object to our CSV row format."""
    supertype = card.get("supertype", "")
    subtypes = card.get("subtypes") or []
    types = card.get("types") or []
    attacks = card.get("attacks") or []
    weaknesses = card.get("weaknesses") or []
    resistances = card.get("resistances") or []
    abilities = card.get("abilities") or []

    # type: combine supertype + subtypes
    type_parts = [supertype] + subtypes
    type_str = " ".join(type_parts).strip()

    # colors: map Pokemon types
    colors = [t for t in types if t in POKEMON_TYPES]

    # cmc: max attack converted energy cost
    cmc = 0
    if attacks:
        cmc = max(parse_attack_cost(a) for a in attacks)

    # rarity
    rarity = card.get("rarity", "")

    # power: max attack damage
    power = 0
    if attacks:
        power = max(parse_damage(a.get("damage")) for a in attacks)

    # toughness: HP (for Pokemon only)
    hp_raw = card.get("hp", "")
    hp_val = 0
    if hp_raw:
        m = re.search(r"(\d+)", str(hp_raw))
        if m:
            hp_val = int(m.group(1))
    toughness = hp_val if supertype == "Pok\u00e9mon" else 0

    # weakness / resistance
    weakness_type = weaknesses[0]["type"] if weaknesses else ""
    resistance_type = resistances[0]["type"] if resistances else ""

    # keywords
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

    # retreat cost
    retreat = card.get("convertedRetreatCost", 0) or 0

    # regulation mark
    reg_mark = card.get("regulationMark", "")

    # Oracle text: combine abilities + attacks into one text block
    oracle_parts = []
    for ability in abilities:
        ab_name = ability.get("name", "")
        ab_text = ability.get("text", "")
        ab_type = ability.get("type", "Ability")
        if ab_name or ab_text:
            oracle_parts.append(f"[{ab_type}] {ab_name}: {ab_text}".strip())
    for attack in attacks:
        atk_name = attack.get("name", "")
        atk_text = attack.get("text", "")
        atk_dmg = attack.get("damage", "")
        atk_cost = attack.get("cost", [])
        cost_str = ",".join(atk_cost) if atk_cost else ""
        parts = [f"[{cost_str}]" if cost_str else "", atk_name]
        if atk_dmg:
            parts.append(f"({atk_dmg})")
        if atk_text:
            parts.append(atk_text)
        oracle_parts.append(" ".join(p for p in parts if p).strip())
    # Add rules text if present
    rules = card.get("rules") or []
    for rule in rules:
        oracle_parts.append(rule)
    oracle_text = " | ".join(oracle_parts)

    # Image URL: prefer large image
    images = card.get("images") or {}
    image_url = images.get("large", "") or images.get("small", "")

    return {
        "name": card.get("name", ""),
        "type": type_str,
        "colors": ",".join(colors),
        "cmc": cmc,
        "rarity": rarity,
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
        "oracle_text": oracle_text,
        "image_url": image_url,
        "_set_release": set_release,  # internal, used for dedup
        "_card_id": card.get("id", ""),
    }


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent.parent
    output_path = project_root / "data" / "processed" / "card_attributes_pokemon.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # -- Step 1: Fetch set metadata (release dates) --
    print("Fetching set metadata...")
    sets_url = f"{GITHUB_RAW}/sets/en.json"
    sets_data = fetch_json(sets_url)
    set_releases: dict[str, str] = {}
    for s in sets_data:
        set_releases[s["id"]] = s.get("releaseDate", "0000/00/00")
    print(f"  {len(set_releases)} sets loaded.")

    # -- Step 2: List all set card files --
    print("Listing card set files...")
    dir_listing = fetch_json(GITHUB_API)
    set_files = [
        f["name"] for f in dir_listing
        if f["name"].endswith(".json")
    ]
    print(f"  {len(set_files)} set files found.")

    # -- Step 3: Fetch all card data --
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

        release = set_releases.get(set_id, "0000/00/00")
        count = len(cards)
        total_raw += count

        for card in cards:
            row = process_card(card, release)
            all_rows.append(row)

        if i % 20 == 0 or i == len(set_files):
            print(f"  [{i}/{len(set_files)}] {filename}: {count} cards (running total: {total_raw})")

        # Small delay to be polite to GitHub
        time.sleep(0.05)

    print(f"\nFetched {total_raw} total card records from {len(set_files)} sets.")

    # -- Step 4: Deduplicate by name (keep latest set release, highest card ID) --
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

    # -- Step 5: Write CSV (remove internal fields) --
    fieldnames = [
        "name", "type", "colors", "cmc", "rarity", "power", "toughness",
        "keywords", "supertype", "subtypes", "hp", "retreat_cost",
        "weakness_type", "resistance_type", "regulation_mark",
        "oracle_text", "image_url",
    ]

    rows = []
    for name in sorted(by_name.keys()):
        row = by_name[name]
        # Drop internal fields
        clean = {k: row[k] for k in fieldnames}
        rows.append(clean)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nSaved {len(rows)} cards to {output_path}")

    # -- Step 6: Summary stats --
    supertypes: dict[str, int] = {}
    rarities: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    has_attacks = 0
    has_ability = 0

    for row in rows:
        st = row["supertype"]
        supertypes[st] = supertypes.get(st, 0) + 1
        r = row["rarity"] or "(none)"
        rarities[r] = rarities.get(r, 0) + 1
        for c in row["colors"].split(","):
            if c:
                type_counts[c] = type_counts.get(c, 0) + 1
        if row["power"] > 0:
            has_attacks += 1
        if "has_ability" in row["keywords"]:
            has_ability += 1

    print("\n--- Summary ---")
    print(f"Total unique cards: {len(rows)}")
    print(f"Cards with attacks (power > 0): {has_attacks}")
    print(f"Cards with abilities: {has_ability}")
    print(f"\nBy supertype:")
    for st, count in sorted(supertypes.items(), key=lambda x: -x[1]):
        print(f"  {st}: {count}")
    print(f"\nBy Pokemon type (colors):")
    for t, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {t}: {count}")
    print(f"\nBy rarity (top 10):")
    for r, count in sorted(rarities.items(), key=lambda x: -x[1])[:10]:
        print(f"  {r}: {count}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
