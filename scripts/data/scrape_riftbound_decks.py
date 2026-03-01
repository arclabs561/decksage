# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "selectolax"]
# ///
"""Scrape Riftbound tournament and community decklists from riftmana.com.

Scrapes both /tournaments/ and /decks/ pages. Each page contains embedded
deck-viewer widgets with structured card data in data-* attributes.
No JavaScript rendering needed -- card data is in the server-rendered HTML.

Output: data/decks/decks_riftbound.jsonl

Usage:
    uv run scripts/data/scrape_riftbound_decks.py
    uv run scripts/data/scrape_riftbound_decks.py --limit 20
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from selectolax.parser import HTMLParser

BASE_URL = "https://riftmana.com"
USER_AGENT = "DeckSage/1.0 (research project)"
RATE_LIMIT_DELAY = 1.5  # seconds between requests

OUT_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "decks"
OUT_FILE = OUT_DIR / "decks_riftbound.jsonl"


def get_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=30,
    )


def fetch_page(client: httpx.Client, url: str, retries: int = 3) -> str:
    """Fetch a page with retry logic."""
    for attempt in range(retries):
        try:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.text
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            if attempt < retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"  Retry {attempt + 1}: {exc} -- waiting {wait}s")
                time.sleep(wait)
            else:
                raise
    return ""


def discover_tournament_urls(client: httpx.Client) -> list[str]:
    """Discover all tournament deck page URLs from /tournaments/."""
    page_html = fetch_page(client, f"{BASE_URL}/tournaments/")
    links = re.findall(
        r'href="(https?://riftmana\.com/tournaments/[^"?]+)"', page_html
    )
    # Deduplicate and sort
    unique = sorted(set(links))
    print(f"  Found {len(unique)} tournament URLs")
    return unique


def discover_deck_urls(client: httpx.Client) -> list[str]:
    """Discover community deck page URLs from /decks/."""
    page_html = fetch_page(client, f"{BASE_URL}/decks/")
    links = re.findall(
        r'href="(https?://riftmana\.com/decks/[^"?]+)"', page_html
    )
    unique = sorted(set(links))
    print(f"  Found {len(unique)} community deck URLs")
    return unique


def extract_decks_from_page(page_html: str, page_url: str) -> list[dict]:
    """Extract all deck-viewer decks from a page's HTML.

    Each deck-viewer widget has:
    - data-deck-title, data-deck-author, data-deck-uuid on the viewer div
    - Card entries as elements with class "deck-viewer-card-image" containing:
      - data-card-id (e.g. "OGN-247")
      - data-card-name (e.g. "Kai'Sa, Daughter of the Void")
      - data-cost, data-type, data-type-name, data-color, data-might
    - Card quantities as sibling spans with class "deck-viewer-card-qty"
    """
    decks: list[dict] = []
    tree = HTMLParser(page_html)

    # Find all deck-viewer elements
    viewers = tree.css("div.deck-viewer")
    if not viewers:
        # Fallback: try broader selector
        viewers = tree.css("[data-deck-uuid]")

    for viewer in viewers:
        deck_title = viewer.attributes.get("data-deck-title", "")
        deck_author = viewer.attributes.get("data-deck-author", "")
        deck_uuid = viewer.attributes.get("data-deck-uuid", "")
        deck_url = viewer.attributes.get("data-deck-url", page_url)

        if not deck_uuid:
            continue

        # Extract cards from deck-viewer-card-image elements
        card_elements = viewer.css(".deck-viewer-card-image, [data-card-id]")
        qty_elements = viewer.css(".deck-viewer-card-qty")

        cards: list[dict] = []
        seen_cards: dict[str, int] = {}  # name -> index in cards list

        for i, card_el in enumerate(card_elements):
            card_id = card_el.attributes.get("data-card-id", "")
            card_name = html_mod.unescape(
                card_el.attributes.get("data-card-name", "")
            )
            if not card_name:
                continue

            # Get quantity from matching qty element
            qty = 1
            if i < len(qty_elements):
                qty_text = qty_elements[i].text(strip=True)
                try:
                    qty = int(qty_text)
                except ValueError:
                    qty = 1

            # Determine partition based on card type
            card_type = card_el.attributes.get("data-type-name", "")
            if card_type in ("Legend", "Rune", "Battlefield"):
                partition = card_type
            else:
                partition = "Deck"

            if card_name in seen_cards:
                # Merge quantities for duplicate card entries
                idx = seen_cards[card_name]
                cards[idx]["count"] += qty
            else:
                seen_cards[card_name] = len(cards)
                cards.append({
                    "name": card_name,
                    "count": qty,
                    "partition": partition,
                })

        if not cards:
            continue

        # Extract event date from page URL slug (format: "name-M-D" or similar)
        event_date = ""
        date_match = re.search(r"(\d{1,2})-(\d{1,2})/?$", page_url.rstrip("/"))
        if date_match:
            month, day = date_match.groups()
            # Assume 2025-2026 era (game launched late 2024/early 2025)
            year = 2025 if int(month) >= 6 else 2026
            event_date = f"{year}-{int(month):02d}-{int(day):02d}"

        # Determine source type
        is_tournament = "/tournaments/" in page_url
        source_type = "tournament" if is_tournament else "community"

        # Extract champion (Legend card)
        champion = ""
        for card in cards:
            if card["partition"] == "Legend":
                champion = card["name"]
                break

        deck = {
            "deck_id": f"riftmana:{deck_uuid}",
            "archetype": champion or deck_title,
            "format": "Standard",
            "url": deck_url or page_url,
            "source": "riftmana",
            "player": deck_author,
            "event": deck_title if is_tournament else "",
            "placement": 0,
            "date": event_date,
            "scraped_at": datetime.now(UTC).isoformat(),
            "cards": cards,
        }

        decks.append(deck)

    return decks


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Riftbound decks from riftmana.com")
    parser.add_argument("--limit", type=int, default=0, help="Max pages to scrape (0 = all)")
    args = parser.parse_args()

    client = get_client()

    print("Discovering Riftbound deck sources on riftmana.com...")
    tournament_urls = discover_tournament_urls(client)
    time.sleep(RATE_LIMIT_DELAY)
    community_urls = discover_deck_urls(client)

    all_urls = tournament_urls + community_urls
    if args.limit > 0:
        all_urls = all_urls[: args.limit]

    print(f"Total pages to scrape: {len(all_urls)}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    all_decks: list[dict] = []
    seen_uuids: set[str] = set()
    errors = 0

    for i, url in enumerate(all_urls, 1):
        try:
            page_html = fetch_page(client, url)
            decks = extract_decks_from_page(page_html, url)

            for deck in decks:
                uuid = deck["deck_id"]
                if uuid not in seen_uuids:
                    seen_uuids.add(uuid)
                    all_decks.append(deck)

            if decks:
                print(f"  [{i}/{len(all_urls)}] {url} -- {len(decks)} deck(s)")
            else:
                print(f"  [{i}/{len(all_urls)}] {url} -- no decks found")

        except Exception as exc:
            print(f"  [{i}/{len(all_urls)}] ERROR {url}: {exc}", file=sys.stderr)
            errors += 1

        time.sleep(RATE_LIMIT_DELAY)

    # Write output
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        for deck in all_decks:
            f.write(json.dumps(deck, ensure_ascii=False) + "\n")

    total_cards = sum(
        sum(c["count"] for c in d["cards"]) for d in all_decks
    )
    avg_cards = total_cards / len(all_decks) if all_decks else 0

    print(f"\nResults:")
    print(f"  Decks written: {len(all_decks)}")
    print(f"  Total card slots: {total_cards}")
    print(f"  Avg cards/deck: {avg_cards:.1f}")
    print(f"  Errors: {errors}")
    print(f"  Output: {OUT_FILE}")


if __name__ == "__main__":
    main()
