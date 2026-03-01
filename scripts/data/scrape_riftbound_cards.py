# /// script
# requires-python = ">=3.11"
# ///
"""Scrape all Riftbound card attributes from the Riftcodex public API.

Fetches the full card catalog with pagination, deduplicates by clean_name
(keeping the canonical non-alternate-art version), and outputs a CSV matching
the format expected by DeckSage's card feature loading.

API: https://api.riftcodex.com/cards (no key required)
Docs: https://riftcodex.com/docs/category/riftcodex-api

Output: data/processed/card_attributes_riftbound.csv

Usage:
    uv run scripts/data/scrape_riftbound_cards.py
"""
from __future__ import annotations

import csv
import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

API_BASE = "https://api.riftcodex.com/cards"
PAGE_SIZE = 100  # API max

OUT_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "processed"
OUT_FILE = OUT_DIR / "card_attributes_riftbound.csv"

# Map Riftcodex card types to a unified type string
TYPE_MAP = {
    "Unit": "Unit",
    "Spell": "Spell",
    "Gear": "Gear",
    "Rune": "Rune",
    "Battlefield": "Battlefield",
    "Legend": "Legend",
}

# Fix incomplete set labels from the API
SET_LABEL_FIXES = {
    "SFD": "Spiritforged",
}

# Keywords to extract from plain text
KEYWORD_RE = re.compile(r"\[([A-Za-z][A-Za-z ]+?)\]")


def fetch_page(page: int, *, timeout: int = 30, retries: int = 3) -> dict:
    """Fetch one page of cards from the Riftcodex API."""
    url = f"{API_BASE}?page={page}&size={PAGE_SIZE}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "DeckSage/1.0 (research project)",
        },
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except Exception as exc:
            if attempt < retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"  Retry {attempt + 1}: {exc} -- waiting {wait}s")
                time.sleep(wait)
            else:
                raise
    return {}


def fetch_all_cards() -> list[dict]:
    """Fetch all cards from the Riftcodex API with pagination."""
    all_cards: list[dict] = []
    page = 1

    # Get first page to learn total
    data = fetch_page(page)
    total = data.get("total", 0)
    pages = data.get("pages", 1)
    all_cards.extend(data.get("items", []))
    print(f"  Page 1/{pages}: {len(data.get('items', []))} cards (total: {total})")

    for page in range(2, pages + 1):
        time.sleep(0.3)  # polite rate limit
        data = fetch_page(page)
        items = data.get("items", [])
        if not items:
            break
        all_cards.extend(items)
        if page % 20 == 0:
            print(f"  Page {page}/{pages}: {len(all_cards)} cards so far")

    return all_cards


def extract_keywords(card: dict) -> list[str]:
    """Extract gameplay keywords from card text."""
    keywords: list[str] = []
    seen: set[str] = set()

    # Card type
    ctype = card.get("classification", {}).get("type", "")
    if ctype:
        keywords.append(ctype)
        seen.add(ctype)

    # Supertype (Champion, Signature)
    supertype = card.get("classification", {}).get("supertype")
    if supertype and supertype not in seen:
        keywords.append(supertype)
        seen.add(supertype)

    # Extract bracketed keywords from text
    text = card.get("text", {}).get("plain", "")
    for m in KEYWORD_RE.finditer(text):
        kw = m.group(1).strip()
        if kw and kw not in seen:
            keywords.append(kw)
            seen.add(kw)

    return keywords


def clean_text(text: str) -> str:
    """Clean Riftbound card text: remove icon tokens, normalize whitespace."""
    # Remove :rb_*: icon tokens
    text = re.sub(r":rb_[a-z_0-9]+:", "", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def deduplicate_cards(cards: list[dict]) -> list[dict]:
    """Deduplicate by clean_name, preferring non-alternate-art."""
    best: dict[str, dict] = {}
    for card in cards:
        meta = card.get("metadata", {})
        clean_name = meta.get("clean_name", card.get("name", "")).strip()
        if not clean_name:
            continue

        existing = best.get(clean_name)
        if existing is None:
            best[clean_name] = card
        else:
            # Prefer non-alternate-art
            if meta.get("alternate_art", False):
                continue  # skip alt art if we already have a version
            best[clean_name] = card

    return list(best.values())


def main() -> None:
    print("Fetching Riftbound cards from Riftcodex API...")
    raw_cards = fetch_all_cards()
    print(f"  Raw entries: {len(raw_cards)}")

    cards = deduplicate_cards(raw_cards)
    cards.sort(key=lambda c: c.get("metadata", {}).get("clean_name", c.get("name", "")))
    print(f"  Unique cards (by clean_name): {len(cards)}")

    # Count by type
    type_counts: dict[str, int] = {}
    for c in cards:
        t = c.get("classification", {}).get("type", "Unknown")
        type_counts[t] = type_counts.get(t, 0) + 1
    for t, n in sorted(type_counts.items()):
        print(f"    {t}: {n}")

    # Count by set
    set_counts: dict[str, int] = {}
    for c in cards:
        s = c.get("set", {}).get("label", "Unknown")
        set_counts[s] = set_counts.get(s, 0) + 1
    for s, n in sorted(set_counts.items()):
        print(f"    Set {s}: {n}")

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
            meta = card.get("metadata", {})
            name = meta.get("clean_name", card.get("name", "")).strip()
            if not name:
                continue

            classification = card.get("classification", {})
            attrs = card.get("attributes", {})
            text = card.get("text", {})
            media = card.get("media", {})
            card_set = card.get("set", {})

            ctype = classification.get("type", "")
            supertype = classification.get("supertype") or ""
            full_type = f"{supertype} {ctype}".strip() if supertype else ctype

            # Domain = color equivalent
            domains = classification.get("domain", [])
            colors = ",".join(domains) if domains else ""

            # Energy = mana cost equivalent
            energy = attrs.get("energy")

            # Might = power, Power = health/toughness
            might = attrs.get("might")
            power_val = attrs.get("power")

            rarity = classification.get("rarity", "")
            keywords = extract_keywords(card)
            oracle_text = clean_text(text.get("plain", ""))

            image_url = media.get("image_url", "")
            set_label = card_set.get("label", "")
            set_label = SET_LABEL_FIXES.get(set_label, set_label)

            writer.writerow({
                "name": name,
                "type": full_type,
                "colors": colors,
                "cmc": energy if energy is not None else "",
                "rarity": rarity,
                "power": might if might is not None else "",
                "toughness": power_val if power_val is not None else "",
                "keywords": ",".join(keywords),
                "attribute": set_label,  # set name as attribute
                "race": "",  # no race concept in Riftbound
                "archetype": "",  # no archetype concept in Riftbound
                "oracle_text": oracle_text,
                "image_url": image_url,
            })
            written += 1

    print(f"Wrote {written} cards to {OUT_FILE}")


if __name__ == "__main__":
    main()
