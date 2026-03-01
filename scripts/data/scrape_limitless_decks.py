#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""
Scrape TCG tournament decklists from the Limitless TCG API.

Limitless TCG (play.limitlesstcg.com) hosts online tournaments for multiple
card games (Pokemon, Digimon, Lorcana, One Piece, etc.) and exposes a public
JSON API for tournament listings and standings (including full decklists when
submitted by players).

This script paginates through tournaments for a given game, fetches standings
for each, extracts decklists, deduplicates by card composition, and writes
them in the standard DeckSage JSONL format.

Supported games with decklists: PTCG (Pokemon), DCG (Digimon).

Usage:
    uv run scripts/data/scrape_limitless_decks.py \
        --game PTCG \
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
RATE_LIMIT_DELAY = 2.0  # seconds between API requests
MAX_RETRIES = 5
BACKOFF_BASE = 3.0  # exponential backoff multiplier

# Per-game decklist section mappings.
# Keys are the JSON keys in the Limitless API response; values are partition labels.
GAME_SECTIONS: dict[str, dict[str, str]] = {
    "PTCG": {"pokemon": "Pokemon", "trainer": "Trainer", "energy": "Energy"},
    "DCG": {"digimon": "Digimon", "tamer": "Tamer", "option": "Option", "egg": "Egg"},
}


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


def fetch_standings(client: httpx.Client, tournament_id: str) -> list[dict]:
    """Fetch standings (with decklists) for a single tournament."""
    data = _get_json(client, f"{BASE_URL}/tournaments/{tournament_id}/standings")
    if not isinstance(data, list):
        return []
    return data


def _flatten_decklist(decklist: dict, section_map: dict[str, str]) -> list[dict]:
    """Convert Limitless decklist sections into flat card list.

    Limitless returns decklists grouped by category (game-dependent).
    Each card has: name, count, set, number.
    We flatten into a single list with partition labels.
    """
    cards: list[dict] = []
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
    game: str = "PTCG",
    max_tournaments: int = 200,
    deck_limit: int = 5000,
    output_file: object | None = None,
) -> tuple[list[dict], dict]:
    """Scrape decklists from Limitless tournaments.

    Fetches tournament pages incrementally (one page at a time) and processes
    standings for each before fetching the next page. This avoids the large
    upfront tournament list fetch that triggers rate limits.

    If output_file is provided, writes each deck as JSONL incrementally.

    Returns (unique_decks, stats_dict).
    """
    section_map = GAME_SECTIONS.get(game)
    if section_map is None:
        print(f"No section mapping for game '{game}'. Known: {list(GAME_SECTIONS)}")
        return [], {"error": f"unsupported game: {game}"}

    now = datetime.now(UTC).isoformat()

    seen_fingerprints: set[frozenset] = set()
    unique_decks: list[dict] = []
    total_decks_with_lists = 0
    tournaments_checked = 0
    tournaments_with_decks = 0
    page_num = 1
    page_size = 50
    tournament_index = 0

    print("Fetching and processing tournaments incrementally...")

    while tournaments_checked < max_tournaments and len(unique_decks) < deck_limit:
        # Fetch one page of tournaments (API uses 'page', not 'offset')
        try:
            page = _get_json(
                client,
                f"{BASE_URL}/tournaments",
                params={"game": game, "limit": page_size, "page": page_num},
            )
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            print(f"  Error fetching tournament page {page_num}: {exc}")
            break

        if not page:
            print("  No more tournaments.")
            break

        print(f"  Fetched tournament page {page_num} ({len(page)} tournaments)")

        for tourney in page:
            if len(unique_decks) >= deck_limit or tournaments_checked >= max_tournaments:
                break

            tid = tourney["id"]
            tname = tourney.get("name", tid)
            tformat = tourney.get("format", "")
            tdate = tourney.get("date", "")
            tournaments_checked += 1
            tournament_index += 1

            if tournament_index % 100 == 0:
                print(f"  --- Progress: {tournament_index} tournaments checked, "
                      f"{len(unique_decks)} unique decks ---")

            try:
                standings = fetch_standings(client, tid)
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                print(f"    Error fetching standings for {tname}: {exc}")
                continue

            decks_in_tourney = 0
            for entry in standings:
                if len(unique_decks) >= deck_limit:
                    break

                decklist_raw = entry.get("decklist")
                if not decklist_raw:
                    continue

                cards = _flatten_decklist(decklist_raw, section_map)
                if not cards:
                    continue

                decks_in_tourney += 1
                total_decks_with_lists += 1

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
                if output_file is not None:
                    output_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                    output_file.flush()

            if decks_in_tourney > 0:
                tournaments_with_decks += 1

        if len(page) < page_size:
            print("  Reached end of tournament list.")
            break
        page_num += 1

    stats = {
        "tournaments_checked": tournaments_checked,
        "tournaments_with_decks": tournaments_with_decks,
        "total_decks_with_lists": total_decks_with_lists,
        "unique_decks_written": len(unique_decks),
    }
    return unique_decks, stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scrape TCG decklists from Limitless TCG tournaments."
    )
    parser.add_argument(
        "--game",
        default="PTCG",
        choices=list(GAME_SECTIONS),
        help="Game code (default: PTCG). Supported: %(choices)s",
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
    print(f"  Game:            {args.game}")
    print(f"  Output:          {args.output}")
    print(f"  Deck limit:      {args.limit}")
    print(f"  Max tournaments: {args.max_tournaments}")
    print()

    with (
        open(args.output, "w") as out_f,
        httpx.Client(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client,
    ):
        decks, stats = scrape_decks(
            client,
            game=args.game,
            max_tournaments=args.max_tournaments,
            deck_limit=args.limit,
            output_file=out_f,
        )

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
