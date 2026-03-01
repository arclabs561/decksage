# /// script
# requires-python = ">=3.11"
# ///
"""Scrape all Digimon TCG card attributes from digimoncard.io public API.

Fetches the full card catalog, deduplicates by card name (keeping the latest
printing by date_added), and outputs a CSV matching the format expected by
DeckSage's card feature loading (train_graphsage.py / load_card_features).

Output: data/processed/card_attributes_digimon.csv

Usage:
    uv run scripts/data/scrape_digimon_cards.py
"""
from __future__ import annotations

import csv
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

SEARCH_API = (
    "https://digimoncard.io/api-public/search.php"
    "?sort=name&series=Digimon+Card+Game&sortdirection=asc&limit=10000"
)

OUT_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "processed"
OUT_FILE = OUT_DIR / "card_attributes_digimon.csv"

# Digimon colors map to the "colors" column
DIGIMON_COLORS = {
    "Red", "Blue", "Yellow", "Green", "Black", "Purple", "White",
}

# Keywords to extract from effects text
KEYWORD_PATTERNS = [
    r"<([A-Z][A-Za-z\s]+?)>",           # <Blocker>, <Reboot>, etc.
    r"\uff1c([A-Za-z\s]+?)\uff1e",       # fullwidth angle brackets
    r"\[(?:On Play|When Digivolving|When Attacking|End of Attack|"
    r"On Deletion|Start of Your Turn|Start of Your Main Phase|"
    r"Security|Main|All Turns|Your Turn|Opponent's Turn)\]",
]


def fetch_all_cards(*, timeout: int = 60, retries: int = 3) -> list[dict]:
    """Fetch the full card list from digimoncard.io search API."""
    req = urllib.request.Request(
        SEARCH_API,
        headers={"User-Agent": "DeckSage/1.0 (research project)"},
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode())
                if isinstance(data, list):
                    return data
                print(f"Unexpected response type: {type(data)}", file=sys.stderr)
                return []
        except Exception as exc:
            if attempt < retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"  Retry {attempt + 1}: {exc} -- waiting {wait}s")
                time.sleep(wait)
            else:
                raise
    return []


def extract_keywords(card: dict) -> list[str]:
    """Extract gameplay keywords from card effects."""
    keywords: set[str] = []
    text = " ".join(
        card.get(f, "") or ""
        for f in ("main_effect", "source_effect", "alt_effect", "xros_req")
    )
    # Card type
    ctype = card.get("type", "")
    if ctype:
        keywords = [ctype]
    else:
        keywords = []

    kw_set: set[str] = set()
    for pat in KEYWORD_PATTERNS:
        for m in re.finditer(pat, text):
            kw = m.group(0).strip("<>\uff1c\uff1e[]")
            if kw and kw not in kw_set:
                kw_set.add(kw)
                keywords.append(kw)

    # Add form/stage if present
    form = card.get("form") or card.get("stage")
    if form:
        keywords.append(form)

    return keywords


def build_oracle_text(card: dict) -> str:
    """Build oracle_text from main_effect, source_effect, and inherited effect."""
    parts: list[str] = []
    for field, label in [
        ("main_effect", ""),
        ("source_effect", ""),
        ("alt_effect", "Alt: "),
    ]:
        text = (card.get(field) or "").strip()
        if text:
            parts.append(f"{label}{text}" if label else text)

    # Add xros/assembly requirements
    xros = (card.get("xros_req") or "").strip()
    if xros:
        parts.append(xros)

    return " | ".join(parts)


def build_colors(card: dict) -> str:
    """Build colors string from color and color2 fields."""
    colors = []
    for f in ("color", "color2"):
        c = card.get(f)
        if c and c in DIGIMON_COLORS:
            colors.append(c)
    return ",".join(colors) if colors else ""


def deduplicate_by_name(cards: list[dict]) -> list[dict]:
    """Keep only the latest printing per card name (by date_added)."""
    best: dict[str, dict] = {}
    for card in cards:
        name = card.get("name", "").strip()
        if not name:
            continue
        existing = best.get(name)
        if existing is None:
            best[name] = card
        else:
            # Keep the one with the later date_added
            new_date = card.get("date_added", "")
            old_date = existing.get("date_added", "")
            if new_date > old_date:
                best[name] = card
    return list(best.values())


def main() -> None:
    print("Fetching Digimon cards from digimoncard.io API...")
    raw_cards = fetch_all_cards()
    print(f"  Raw entries: {len(raw_cards)}")

    cards = deduplicate_by_name(raw_cards)
    cards.sort(key=lambda c: c.get("name", ""))
    print(f"  Unique cards (by name): {len(cards)}")

    # Count by type
    type_counts: dict[str, int] = {}
    for c in cards:
        t = c.get("type", "Unknown")
        type_counts[t] = type_counts.get(t, 0) + 1
    for t, n in sorted(type_counts.items()):
        print(f"    {t}: {n}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "name", "type", "colors", "cmc", "rarity",
        "power", "toughness", "keywords",
        "attribute", "race", "archetype", "oracle_text", "image_url",
    ]

    written = 0
    with open(OUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for card in cards:
            name = card.get("name", "").strip()
            if not name:
                continue

            ctype = card.get("type", "")
            colors = build_colors(card)
            level = card.get("level")
            play_cost = card.get("play_cost")
            dp = card.get("dp")
            rarity = card.get("rarity", "")
            keywords = extract_keywords(card)
            oracle_text = build_oracle_text(card)

            # Map Digimon fields to the shared schema:
            # - cmc -> play_cost (closest analog to mana cost)
            # - power -> dp (digimon power)
            # - toughness -> level
            # - attribute -> Digimon attribute (Vaccine, Virus, Data, etc.)
            # - race -> digi_type (Dragon, Beast, etc.)
            # - archetype -> not a native concept; leave empty
            digi_types = []
            for dt_field in ("digi_type", "digi_type2", "digi_type3", "digi_type4"):
                dt = card.get(dt_field)
                if dt:
                    digi_types.append(dt)

            writer.writerow({
                "name": name,
                "type": ctype,
                "colors": colors,
                "cmc": play_cost if play_cost is not None else "",
                "rarity": rarity,
                "power": dp if dp is not None else "",
                "toughness": level if level is not None else "",
                "keywords": ",".join(keywords),
                "attribute": card.get("attribute") or "",
                "race": "/".join(digi_types),
                "archetype": "",
                "oracle_text": oracle_text,
                "image_url": "",
            })
            written += 1

    print(f"Wrote {written} cards to {OUT_FILE}")


if __name__ == "__main__":
    main()
