#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""
Scrape Pokemon TCG tournament decklists from the Limitless TCG API.

Limitless TCG (play.limitlesstcg.com) hosts online Pokemon TCG tournaments
and exposes a public JSON API for tournament listings and standings
(including full decklists when submitted by players).

This script paginates through recent PTCG tournaments, fetches standings
for each, extracts decklists, deduplicates by card composition, and
writes them in the standard DeckSage JSONL format.

Usage:
    uv run scripts/data/scrape_limitless_decks.py \
        --output data/decks/decks_pokemon_limitless.jsonl \
        --limit 5000
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx


BASE_URL = "https://play.limitlesstcg.com/api"
USER_AGENT = "DeckSage/1.0 (research project)"
RATE_LIMIT_DELAY = 1.0  # seconds between API requests
MAX_RETRIES = 3
BACKOFF_BASE = 2.0  # exponential backoff multiplier


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _request_with_retry(
    client: httpx.Client,
    url: str,
    *,
    params: dict | None = None,
    max_retries: int = MAX_RETRIES,
) -> httpx.Response:
    """GET with exponential-backoff retry on 429 / 5xx."""
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = client.get(url, params=params, timeout=30)
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = BACKOFF_BASE ** (attempt + 1)
                print(
                    f"  [retry] {resp.status_code} on {url} -- "
                    f"waiting {wait:.1f}s (attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(wait)
                continue
            return resp
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            last_exc = exc
            wait = BACKOFF_BASE ** (attempt + 1)
            print(
                f"  [retry] {type(exc).__name__} on {url} -- "
                f"waiting {wait:.1f}s (attempt {attempt + 1}/{max_retries})"
            )
            time.sleep(wait)

    if last_exc is not None:
        raise last_exc
    raise httpx.RequestError(f"Failed after {max_retries} retries: {url}")


def _get_json(
    client: httpx.Client,
    url: str,
    *,
    params: dict | None = None,
) -> list | dict:
    """GET + parse JSON, with retry and rate limiting."""
    time.sleep(RATE_LIMIT_DELAY)
    resp = _request_with_retry(client, url, params=params)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Tournament + standings fetching
# ---------------------------------------------------------------------------


def fetch_tournaments(
    client: httpx.Client,
    *,
    max_tournaments: int = 200,
) -> list[dict]:
    """Paginate through PTCG tournaments on Limitless."""
    tournaments: list[dict] = []
    offset = 0
    page_size = 50

    while len(tournaments) < max_tournaments:
        print(f"  Fetching tournaments offset={offset}...")
        data = _get_json(
            client,
            f"{BASE_URL}/tournaments",
            params={
                "game": "PTCG",
                "limit": page_size,
                "offset": offset,
            },
        )
        if not data:
            print("  No more tournaments.")
            break

        tournaments.extend(data)
        print(f"    Got {len(data)} tournaments (total: {len(tournaments)})")

        if len(data) < page_size:
            break
        offset += page_size

    return tournaments[:max_tournaments]


def fetch_standings(client: httpx.Client, tournament_id: str) -> list[dict]:
    """Fetch standings (with decklists) for a single tournament."""
    data = _get_json(client, f"{BASE_URL}/tournaments/{tournament_id}/standings")
    if not isinstance(data, list):
        return []
    return data


def _flatten_decklist(decklist: dict) -> list[dict]:
    """Convert Limitless decklist sections into flat card list.

    Limitless returns decklists grouped by category (pokemon, trainer, energy).
    Each card has: name, count, set, number.
    We flatten into a single list with partition labels.
    """
    cards: list[dict] = []
    section_map = {
        "pokemon": "Pokemon",
        "trainer": "Trainer",
        "energy": "Energy",
    }
    for section_key, partition in section_map.items():
        for card in decklist.get(section_key, []):
            name = card.get("name", "")
            count = card.get("count", 1)
            if name:
                cards.append({
                    "name": name,
                    "count": count,
                    "partition": partition,
                })
    return cards


def _card_fingerprint(cards: list[dict]) -> frozenset[tuple[str, int, str]]:
    """Create a hashable fingerprint from a card list for deduplication."""
    return frozenset(
        (c["name"], c["count"], c["partition"]) for c in cards
    )


# ---------------------------------------------------------------------------
# Main scraping logic
# ---------------------------------------------------------------------------


def scrape_decks(
    client: httpx.Client,
    *,
    max_tournaments: int = 200,
    deck_limit: int = 5000,
) -> tuple[list[dict], dict]:
    """Scrape decklists from Limitless tournaments.

    Returns (unique_decks, stats_dict).
    """
    now = datetime.now(UTC).isoformat()

    print("Fetching tournament list...")
    tournaments = fetch_tournaments(client, max_tournaments=max_tournaments)
    print(f"Found {len(tournaments)} tournaments.\n")

    seen_fingerprints: set[frozenset] = set()
    unique_decks: list[dict] = []
    total_decks_with_lists = 0
    tournaments_checked = 0
    tournaments_with_decks = 0

    for i, tourney in enumerate(tournaments):
        if len(unique_decks) >= deck_limit:
            print(f"  Reached deck limit ({deck_limit}), stopping.")
            break

        tid = tourney["id"]
        tname = tourney.get("name", tid)
        tformat = tourney.get("format", "")
        tdate = tourney.get("date", "")
        tournaments_checked += 1

        print(f"  [{i + 1}/{len(tournaments)}] {tname} ({tourney.get('players', '?')} players)...")

        try:
            standings = fetch_standings(client, tid)
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            print(f"    Error fetching standings: {exc}")
            continue

        decks_in_tourney = 0
        for entry in standings:
            if len(unique_decks) >= deck_limit:
                break

            decklist_raw = entry.get("decklist")
            if not decklist_raw:
                continue

            cards = _flatten_decklist(decklist_raw)
            if not cards:
                continue

            decks_in_tourney += 1
            total_decks_with_lists += 1

            # Deduplicate by card composition
            fp = _card_fingerprint(cards)
            if fp in seen_fingerprints:
                continue
            seen_fingerprints.add(fp)

            placing = entry.get("placing", "")
            player = entry.get("name", entry.get("player", ""))
            deck_info = entry.get("deck", {})
            archetype = deck_info.get("name", "") if isinstance(deck_info, dict) else ""

            record = {
                "deck_id": f"limitless:{tid}:{placing}",
                "archetype": archetype,
                "format": tformat,
                "url": f"https://play.limitlesstcg.com/tournament/{tid}",
                "source": "limitless",
                "player": player,
                "event": tname,
                "placement": str(placing),
                "created_at": tdate,
                "scraped_at": now,
                "cards": cards,
            }
            unique_decks.append(record)

        if decks_in_tourney > 0:
            tournaments_with_decks += 1
            print(f"    {decks_in_tourney} decklists found, {len(unique_decks)} unique total")
        else:
            print("    No decklists")

    stats = {
        "tournaments_checked": tournaments_checked,
        "tournaments_with_decks": tournaments_with_decks,
        "total_decks_with_lists": total_decks_with_lists,
        "unique_decks_written": len(unique_decks),
    }
    return unique_decks, stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scrape Pokemon TCG decklists from Limitless TCG tournaments."
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output JSONL file path",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5000,
        help="Max decks to fetch (default: 5000)",
    )
    parser.add_argument(
        "--max-tournaments",
        type=int,
        default=200,
        help="Max tournaments to paginate through (default: 200)",
    )
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)

    print("Limitless TCG deck scraper")
    print(f"  Output:          {args.output}")
    print(f"  Deck limit:      {args.limit}")
    print(f"  Max tournaments: {args.max_tournaments}")
    print()

    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        decks, stats = scrape_decks(
            client,
            max_tournaments=args.max_tournaments,
            deck_limit=args.limit,
        )

    with open(args.output, "w") as f:
        for deck in decks:
            f.write(json.dumps(deck, ensure_ascii=False) + "\n")

    print()
    print("--- Stats ---")
    print(f"  Tournaments checked:    {stats['tournaments_checked']}")
    print(f"  Tournaments w/ decks:   {stats['tournaments_with_decks']}")
    print(f"  Decks with decklists:   {stats['total_decks_with_lists']}")
    print(f"  Unique decks written:   {stats['unique_decks_written']}")
    print(f"  Output: {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
