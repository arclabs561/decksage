#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""
Scrape decklists from Master Duel Meta (masterduelmeta.com) API.

Master Duel Meta has ~76k top-ranked decks accessible via a public JSON API.
Saves in the standard DeckSage JSONL format.

Usage:
    uv run scripts/data/scrape_masterduelmeta_decks.py \
        --output data/decks/decks_yugioh_masterduelmeta.jsonl \
        --max-pages 760
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

API_URL = "https://www.masterduelmeta.com/api/v1/top-decks"
PAGE_SIZE = 100
# Be polite: 0.3s between requests
DELAY = 0.3


def parse_deck(raw: dict) -> dict | None:
    """Convert a Master Duel Meta deck object to DeckSage format."""
    cards = []
    for section, partition in [
        ("main", "Main Deck"),
        ("extra", "Extra Deck"),
        ("side", "Side Deck"),
    ]:
        for entry in raw.get(section, []):
            card_obj = entry.get("card", {})
            name = card_obj.get("name")
            amount = entry.get("amount", 1)
            if not name:
                continue
            cards.append({"name": name, "count": amount, "partition": partition})

    if len(cards) < 20:
        return None

    deck_type = raw.get("deckType", {})
    archetype = deck_type.get("name", "") if isinstance(deck_type, dict) else ""

    ranked = raw.get("rankedType", {})
    rank_name = ranked.get("name", "") if isinstance(ranked, dict) else ""

    author = raw.get("author", {})
    player = author.get("username", "") if isinstance(author, dict) else ""

    url_path = raw.get("url", "")
    full_url = f"https://www.masterduelmeta.com/top-decks{url_path}" if url_path else ""

    return {
        "deck_id": raw.get("_id", ""),
        "archetype": archetype,
        "format": "Master Duel",
        "rank": rank_name,
        "player": player,
        "url": full_url,
        "source": "masterduelmeta",
        "cards": cards,
        "created_at": raw.get("created", ""),
        "scraped_at": datetime.now().isoformat(),
    }


def scrape(max_pages: int, output: Path) -> int:
    """Scrape decks page by page, writing JSONL incrementally."""
    output.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    seen_ids: set[str] = set()
    consecutive_empty = 0

    with httpx.Client(timeout=30) as client, open(output, "w") as f:
        for page in range(1, max_pages + 1):
            try:
                resp = client.get(
                    API_URL,
                    params={"limit": PAGE_SIZE, "page": page},
                )
                if resp.status_code != 200:
                    print(f"  page {page}: HTTP {resp.status_code}, stopping")
                    break

                data = resp.json()
                if not data:
                    consecutive_empty += 1
                    if consecutive_empty >= 3:
                        print(f"  3 consecutive empty pages at page {page}, stopping")
                        break
                    continue

                consecutive_empty = 0
                page_written = 0
                for raw in data:
                    deck_id = raw.get("_id", "")
                    if deck_id in seen_ids:
                        continue
                    seen_ids.add(deck_id)

                    deck = parse_deck(raw)
                    if deck:
                        f.write(json.dumps(deck) + "\n")
                        page_written += 1
                        total += 1

                if page % 50 == 0 or page <= 5:
                    print(f"  page {page}: +{page_written} decks (total {total})")

                time.sleep(DELAY)

            except httpx.HTTPError as e:
                print(f"  page {page}: network error: {e}")
                # Retry once after a longer pause
                time.sleep(2)
                continue
            except json.JSONDecodeError as e:
                print(f"  page {page}: JSON decode error: {e}")
                continue

    return total


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scrape Master Duel Meta top decks"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/decks/decks_yugioh_masterduelmeta.jsonl"),
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=800,
        help="Maximum pages to fetch (100 decks/page, ~760 pages available)",
    )
    args = parser.parse_args()

    print(f"Scraping Master Duel Meta top decks (up to {args.max_pages} pages)...")
    print(f"Output: {args.output}")

    total = scrape(args.max_pages, args.output)

    print(f"\nDone. {total} decks written to {args.output}")

    # Quick stats
    archetypes: dict[str, int] = {}
    with open(args.output) as f:
        for line in f:
            d = json.loads(line)
            arch = d.get("archetype", "unknown")
            archetypes[arch] = archetypes.get(arch, 0) + 1

    print(f"  {len(archetypes)} unique archetypes")
    top = sorted(archetypes.items(), key=lambda x: -x[1])[:15]
    for name, count in top:
        print(f"    {name}: {count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
