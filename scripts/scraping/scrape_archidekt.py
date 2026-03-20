#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx>=0.27.0",
# ]
# ///
"""
Scrape Commander/EDH decks from Archidekt's public API.

Archidekt has an undocumented REST API at /api/decks/ that supports:
- Format filtering (Commander/EDH)
- Pagination (orderBy, page)
- Per-deck card lists

This scraper respects rate limits (1 req/s default) and saves decks
in DeckSage's JSONL format for integration with the Go backend.

Usage:
    uv run scripts/scraping/scrape_archidekt.py --format commander --max-decks 1000
    uv run scripts/scraping/scrape_archidekt.py --format commander --max-decks 10000 --use-proxy
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def get_client(use_proxy: bool = False, rate_limit: float = 1.0) -> httpx.Client:
    """Create HTTP client with optional proxy."""
    proxy_url = os.environ.get("PROXY_URL") or os.environ.get("HTTP_PROXY")
    proxies = proxy_url if (use_proxy and proxy_url) else None

    return httpx.Client(
        base_url="https://archidekt.com",
        headers={
            "User-Agent": "DeckSage/1.0 (deck-research; contact@decksage.dev)",
            "Accept": "application/json",
        },
        proxy=proxies,
        timeout=30.0,
        follow_redirects=True,
    )


def search_decks(
    client: httpx.Client,
    format_name: str = "commander",
    page: int = 1,
    page_size: int = 50,
    order_by: str = "-viewCount",
) -> dict | None:
    """Search for decks by format."""
    try:
        r = client.get(
            "/api/decks/cards/",
            params={
                "formats": format_name,
                "orderBy": order_by,
                "page": page,
                "pageSize": page_size,
            },
        )
        if r.status_code == 200:
            return r.json()
        else:
            print(f"  Search failed: {r.status_code}")
            return None
    except Exception as e:
        print(f"  Search error: {e}")
        return None


def get_deck_detail(client: httpx.Client, deck_id: int) -> dict | None:
    """Get full deck details including card list."""
    try:
        r = client.get(f"/api/decks/{deck_id}/")
        if r.status_code == 200:
            return r.json()
        else:
            return None
    except Exception as e:
        return None


def deck_to_jsonl(deck: dict) -> dict | None:
    """Convert Archidekt deck to DeckSage JSONL format."""
    cards_raw = deck.get("cards", [])
    if not cards_raw:
        return None

    cards = []
    for card_entry in cards_raw:
        card_obj = card_entry.get("card", {})
        name = card_obj.get("oracleCard", {}).get("name", "")
        if not name:
            continue

        quantity = card_entry.get("quantity", 1)
        categories = card_entry.get("categories") or []

        # Map Archidekt categories to partitions
        partition = "Main"
        if "Sideboard" in categories:
            partition = "Sideboard"
        elif "Commander" in categories or "Companion" in categories:
            partition = "Commander"

        cards.append(
            {
                "name": name,
                "count": quantity,
                "partition": partition,
            }
        )

    if not cards:
        return None

    commander_names = [c["name"] for c in cards if c.get("partition") == "Commander"]

    return {
        "deck_id": f"archidekt:{deck.get('id', '')}",
        "name": deck.get("name", ""),
        "format": "commander",
        "source": "archidekt",
        "url": f"https://archidekt.com/decks/{deck.get('id', '')}",
        "player": deck.get("owner", {}).get("username", ""),
        "commander": commander_names[0] if commander_names else "",
        "view_count": deck.get("viewCount", 0),
        "created_at": deck.get("createdAt", ""),
        "updated_at": deck.get("updatedAt", ""),
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "cards": cards,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape Archidekt decks")
    parser.add_argument("--format", default="commander", help="Format to scrape")
    parser.add_argument("--max-decks", type=int, default=1000)
    parser.add_argument("--rate-limit", type=float, default=1.0, help="Seconds between requests")
    parser.add_argument("--use-proxy", action="store_true")
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--start-page", type=int, default=1)
    args = parser.parse_args()

    out_path = (
        Path(args.output)
        if args.output
        else DATA_DIR / "decks" / f"decks_magic_archidekt_{args.format}.jsonl"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    client = get_client(use_proxy=args.use_proxy, rate_limit=args.rate_limit)

    print(f"Scraping Archidekt {args.format} decks")
    print(f"Output: {out_path}")
    print(f"Max decks: {args.max_decks}")
    print(f"Rate limit: {args.rate_limit}s")
    if args.use_proxy:
        print(f"Using proxy: {os.environ.get('PROXY_URL', 'none')[:30]}...")

    format_codes = {"commander": 3, "standard": 1, "modern": 2, "legacy": 4}
    target_format = format_codes.get(args.format, 3)

    n_saved = 0
    n_skipped = 0
    n_errors = 0
    deck_id = args.start_page  # reuse as start ID
    t0 = time.time()

    # Resume support: skip already-scraped IDs
    existing_ids: set[str] = set()
    if out_path.exists():
        with open(out_path) as ef:
            for line in ef:
                if line.strip():
                    try:
                        existing_ids.add(json.loads(line).get("deck_id", ""))
                    except json.JSONDecodeError:
                        pass
        if existing_ids:
            print(f"Resuming: {len(existing_ids)} decks already scraped")

    with open(out_path, "a") as f:
        while n_saved < args.max_decks:
            time.sleep(args.rate_limit)
            deck = get_deck_detail(client, deck_id)
            deck_id += 1

            if not deck:
                n_errors += 1
                if n_errors > 200 and n_saved == 0:
                    print("Too many errors, stopping")
                    break
                continue

            if deck.get("deckFormat") != target_format:
                n_skipped += 1
                continue

            full_id = f"archidekt:{deck.get('id', '')}"
            if full_id in existing_ids:
                continue

            jsonl = deck_to_jsonl(deck)
            if not jsonl or len(jsonl.get("cards", [])) < 20:
                n_skipped += 1
                continue

            f.write(json.dumps(jsonl) + "\n")
            f.flush()
            n_saved += 1

            if n_saved % 50 == 0:
                elapsed = time.time() - t0
                rate = n_saved / elapsed if elapsed > 0 else 0
                print(
                    f"  {n_saved}/{args.max_decks} saved "
                    f"(ID ~{deck_id}, {rate:.2f}/s, {n_skipped} skip, {n_errors} err)"
                )

    elapsed = time.time() - t0
    print(f"\nDone: {n_saved} decks, {n_skipped} skipped, {n_errors} errors, {elapsed:.0f}s")
    print(f"Output: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
