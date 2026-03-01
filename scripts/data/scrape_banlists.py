#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx"]
# ///
"""
Scrape current ban/restricted lists from public TCG APIs.

Supported games:
  - magic   (Scryfall bulk data + search API)
  - yugioh  (YGOProDeck API)
  - pokemon (Pokemon TCG API)

Usage:
    uv run scripts/data/scrape_banlists.py --game magic
    uv run scripts/data/scrape_banlists.py --game all
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

USER_AGENT = "DeckSage-BanlistScraper/0.1 (research; +https://github.com/decksage)"
OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "banlists"

# ---------------------------------------------------------------------------
# Scryfall (Magic: The Gathering)
# ---------------------------------------------------------------------------

SCRYFALL_FORMATS = [
    "standard",
    "modern",
    "legacy",
    "vintage",
    "commander",
    "pioneer",
    "pauper",
    "brawl",
    "historic",
    "alchemy",
]

# Scryfall query syntax: "banned:<format>" / "restricted:<format>"
SCRYFALL_STATUSES = ["banned", "restricted"]


def _scryfall_search(
    client: httpx.Client, query: str, *, delay: float = 0.12
) -> list[str]:
    """Run a paginated Scryfall search and return card names."""
    names: list[str] = []
    url = "https://api.scryfall.com/cards/search"
    params: dict[str, Any] = {"q": query, "unique": "cards", "order": "name"}

    while True:
        time.sleep(delay)  # respect 10 req/s limit
        resp = client.get(url, params=params)
        if resp.status_code == 404:
            # "no cards found" -- not an error
            break
        resp.raise_for_status()
        data = resp.json()
        for card in data.get("data", []):
            names.append(card["name"])
        if not data.get("has_more"):
            break
        # follow next_page URL directly
        url = data["next_page"]
        params = {}  # next_page already includes params

    return sorted(set(names))


def scrape_magic(client: httpx.Client) -> dict[str, Any]:
    """Scrape Magic ban/restricted lists from Scryfall search API."""
    print("[magic] Starting Scryfall ban list scrape...")
    formats: dict[str, dict[str, list[str]]] = {}

    total = len(SCRYFALL_FORMATS) * len(SCRYFALL_STATUSES)
    done = 0

    for fmt in SCRYFALL_FORMATS:
        fmt_data: dict[str, list[str]] = {}
        for status in SCRYFALL_STATUSES:
            done += 1
            # Scryfall syntax: "banned:modern", "restricted:vintage"
            query = f"{status}:{fmt}"
            print(f"  [{done}/{total}] Searching: {query}")
            names = _scryfall_search(client, query)
            if names:
                fmt_data[status] = names
                print(f"    -> {len(names)} cards")
        if fmt_data:
            formats[fmt] = fmt_data

    result = {
        "game": "magic",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source": "scryfall",
        "formats": formats,
    }
    print(f"[magic] Done. {len(formats)} formats with bans/restrictions.")
    return result


# ---------------------------------------------------------------------------
# YGOProDeck (Yu-Gi-Oh!)
# ---------------------------------------------------------------------------

YUGIOH_BANLISTS = {
    "tcg": "ban_tcg",
    "ocg": "ban_ocg",
    "goat": "ban_goat",
}


def scrape_yugioh(client: httpx.Client) -> dict[str, Any]:
    """Scrape Yu-Gi-Oh! ban lists from YGOProDeck API."""
    print("[yugioh] Starting YGOProDeck ban list scrape...")
    formats: dict[str, dict[str, list[str]]] = {}

    for banlist_key, field_name in YUGIOH_BANLISTS.items():
        print(f"  Fetching banlist={banlist_key}...")
        time.sleep(1.0)  # polite delay
        url = "https://db.ygoprodeck.com/api/v7/cardinfo.php"
        resp = client.get(url, params={"banlist": banlist_key})
        resp.raise_for_status()
        cards = resp.json().get("data", [])

        buckets: dict[str, list[str]] = {}
        for card in cards:
            banlist_info = card.get("banlist_info", {})
            status = banlist_info.get(field_name, "")
            if not status:
                continue
            # Normalize: "Banned" -> "banned", "Semi-Limited" -> "semi-limited"
            key = status.lower()
            buckets.setdefault(key, []).append(card["name"])

        for key in buckets:
            buckets[key] = sorted(buckets[key])

        if buckets:
            formats[banlist_key] = buckets
            counts = {k: len(v) for k, v in buckets.items()}
            print(f"    -> {counts}")

    result = {
        "game": "yugioh",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source": "ygoprodeck",
        "formats": formats,
    }
    print(f"[yugioh] Done. {len(formats)} ban lists scraped.")
    return result


# ---------------------------------------------------------------------------
# Pokemon TCG API
# ---------------------------------------------------------------------------

POKEMON_FORMATS = ["standard", "expanded"]
POKEMON_STATUSES = ["Banned"]


def scrape_pokemon(client: httpx.Client) -> dict[str, Any]:
    """Scrape Pokemon TCG ban lists from pokemontcg.io."""
    print("[pokemon] Starting Pokemon TCG API ban list scrape...")
    formats: dict[str, dict[str, list[str]]] = {}

    for fmt in POKEMON_FORMATS:
        for status in POKEMON_STATUSES:
            query = f"legalities.{fmt}:{status}"
            print(f"  Searching: {query}")
            names: list[str] = []
            page = 1
            page_size = 250

            while True:
                time.sleep(1.0)  # polite delay
                url = "https://api.pokemontcg.io/v2/cards"
                params: dict[str, Any] = {
                    "q": query,
                    "pageSize": page_size,
                    "page": page,
                    "select": "name",
                }
                resp = client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                cards = data.get("data", [])
                if not cards:
                    break
                for card in cards:
                    names.append(card["name"])
                # Check if more pages
                total_count = data.get("totalCount", 0)
                if page * page_size >= total_count:
                    break
                page += 1

            if names:
                # Deduplicate (same card name, different printings)
                unique_names = sorted(set(names))
                formats.setdefault(fmt, {})[status.lower()] = unique_names
                print(f"    -> {len(unique_names)} unique card names")

    result = {
        "game": "pokemon",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source": "pokemontcg.io",
        "formats": formats,
    }
    print(f"[pokemon] Done. {len(formats)} formats with bans.")
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

SCRAPERS = {
    "magic": scrape_magic,
    "yugioh": scrape_yugioh,
    "pokemon": scrape_pokemon,
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape TCG ban/restricted lists from public APIs."
    )
    parser.add_argument(
        "--game",
        choices=["magic", "yugioh", "pokemon", "all"],
        default="all",
        help="Which game(s) to scrape (default: all)",
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    games = list(SCRAPERS.keys()) if args.game == "all" else [args.game]

    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(headers=headers, timeout=60.0, follow_redirects=True) as client:
        for game in games:
            scraper = SCRAPERS[game]
            try:
                result = scraper(client)
            except httpx.HTTPStatusError as exc:
                print(
                    f"[{game}] HTTP error: {exc.response.status_code} "
                    f"{exc.response.text[:200]}",
                    file=sys.stderr,
                )
                continue
            except httpx.RequestError as exc:
                print(f"[{game}] Request error: {exc}", file=sys.stderr)
                continue

            out_path = OUTPUT_DIR / f"{game}_banlists.json"
            out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
            print(f"[{game}] Saved to {out_path}")

    print("All done.")


if __name__ == "__main__":
    main()
