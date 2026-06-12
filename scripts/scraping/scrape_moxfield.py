#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "cloudscraper>=1.2.0",
# ]
# ///
"""
Scrape Commander/EDH decks from Moxfield's public API.

Moxfield has a public API at api.moxfield.com that supports:
- Deck search with format filtering
- Pagination (pageNumber, pageSize)
- Per-deck card lists with quantities

This scraper respects rate limits and saves decks in DeckSage's JSONL format.

Usage:
    uv run scripts/scraping/scrape_moxfield.py --format commander --max-decks 5000
    uv run scripts/scraping/scrape_moxfield.py --format modern --max-decks 2000
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import cloudscraper


if not sys.stdout.isatty():
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

API_BASE = "https://api2.moxfield.com"


def get_client(use_proxy: bool = False) -> cloudscraper.CloudScraper:
    """Create cloudscraper client (bypasses Cloudflare JS challenge)."""
    scraper = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "darwin", "mobile": False},
    )
    scraper.headers.update(
        {
            "Accept": "application/json",
        }
    )

    if use_proxy:
        proxy_url = os.environ.get("PROXY_URL") or os.environ.get("HTTP_PROXY")
        if proxy_url:
            scraper.proxies = {"http": proxy_url, "https": proxy_url}

    return scraper


def search_decks(
    client: cloudscraper.CloudScraper,
    fmt: str = "commander",
    page: int = 1,
    page_size: int = 50,
    sort_type: str = "updated",
    sort_direction: str = "descending",
) -> dict | None:
    """Search for public decks by format."""
    try:
        r = client.get(
            f"{API_BASE}/v2/decks/search",
            params={
                "fmt": fmt,
                "pageNumber": page,
                "pageSize": page_size,
                "sortType": sort_type,
                "sortDirection": sort_direction,
                "board": "mainboard",
            },
            timeout=30,
        )
        if r.status_code == 200:
            return r.json()
        else:
            print(f"  Search failed: {r.status_code} {r.text[:200]}")
            return None
    except Exception as e:
        print(f"  Search error: {e}")
        return None


def get_deck_detail(client: cloudscraper.CloudScraper, public_id: str) -> dict | None:
    """Get full deck details including card list."""
    try:
        r = client.get(f"{API_BASE}/v2/decks/all/{public_id}", timeout=30)
        if r.status_code == 200:
            return r.json()
        else:
            return None
    except Exception:
        return None


def deck_to_jsonl(deck: dict, fmt: str) -> dict | None:
    """Convert Moxfield deck to DeckSage JSONL format."""
    cards = []
    board_map = {
        "mainboard": "Main",
        "sideboard": "Sideboard",
        "commanders": "Commander",
        "companions": "Companion",
    }

    for board_name, partition_name in board_map.items():
        board = deck.get(board_name, {})
        if not isinstance(board, dict):
            continue
        for card_name, card_data in board.items():
            if not card_name or not isinstance(card_data, dict):
                continue
            quantity = card_data.get("quantity", 1)
            cards.append(
                {
                    "name": card_name,
                    "count": quantity,
                    "partition": partition_name,
                }
            )

    if not cards:
        return None

    commander_names = [c["name"] for c in cards if c.get("partition") == "Commander"]
    public_id = deck.get("publicId", "")

    return {
        "deck_id": f"moxfield:{public_id}",
        "name": deck.get("name", ""),
        "format": fmt,
        "source": "moxfield",
        "url": f"https://www.moxfield.com/decks/{public_id}",
        "player": deck.get("createdByUser", {}).get("userName", ""),
        "commander": commander_names[0] if commander_names else "",
        "likes": deck.get("likeCount", 0),
        "views": deck.get("viewCount", 0),
        "created_at": deck.get("createdAtUtc", ""),
        "updated_at": deck.get("lastUpdatedAtUtc", ""),
        "scraped_at": datetime.now(UTC).isoformat(),
        "cards": cards,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape Moxfield decks")
    parser.add_argument("--format", default="commander", help="Format to scrape")
    parser.add_argument("--max-decks", type=int, default=5000)
    parser.add_argument("--rate-limit", type=float, default=1.0)
    parser.add_argument("--use-proxy", action="store_true")
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    out_path = (
        Path(args.output)
        if args.output
        else DATA_DIR / "decks" / f"decks_magic_moxfield_{args.format}.jsonl"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    client = get_client(use_proxy=args.use_proxy)

    print(f"Scraping Moxfield {args.format} decks")
    print(f"Output: {out_path}")
    print(f"Max decks: {args.max_decks}")

    n_saved = 0
    n_skipped = 0
    n_errors = 0
    t0 = time.time()

    # Resume support
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
        page = 1

        while n_saved < args.max_decks:
            time.sleep(args.rate_limit)
            search_result = search_decks(client, fmt=args.format, page=page, page_size=50)

            if not search_result:
                print(f"  Search failed at page {page}, stopping")
                break

            deck_summaries = search_result.get("data", [])
            if not deck_summaries:
                print(f"  No results at page {page}, stopping")
                break

            page += 1

            for summary in deck_summaries:
                if n_saved >= args.max_decks:
                    break

                public_id = summary.get("publicId", "")
                if not public_id:
                    continue

                full_id = f"moxfield:{public_id}"
                if full_id in existing_ids:
                    continue

                time.sleep(args.rate_limit)
                deck = get_deck_detail(client, public_id)
                if not deck:
                    n_errors += 1
                    continue

                jsonl = deck_to_jsonl(deck, args.format)
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
                        f"(page {page}, {rate:.2f}/s, {n_skipped} skip, {n_errors} err)"
                    )

    elapsed = time.time() - t0
    print(f"\nDone: {n_saved} decks, {n_skipped} skipped, {n_errors} errors, {elapsed:.0f}s")
    print(f"Output: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
