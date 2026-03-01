# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""Scrape Digimon TCG decklists from Limitless TCG (play.limitlesstcg.com).

Uses the Limitless public API to fetch Digimon (DCG) tournament decklists.
This is the same API used by scrape_limitless_decks.py but specialized for
Digimon output.

Output: data/decks/decks_digimon.jsonl

Usage:
    uv run scripts/data/scrape_digimon_decks.py
    uv run scripts/data/scrape_digimon_decks.py --limit 2000
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
RATE_LIMIT_DELAY = 3.0
MAX_RETRIES = 8
BACKOFF_BASE = 2.0

GAME = "DCG"
SECTION_MAP = {
    "digimon": "Digimon",
    "tamer": "Tamer",
    "option": "Option",
    "egg": "Egg",
}

OUT_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "decks"
OUT_FILE = OUT_DIR / "decks_digimon.jsonl"


def _request_with_retry(
    client: httpx.Client,
    url: str,
    *,
    params: dict | None = None,
) -> httpx.Response:
    """GET with exponential-backoff retry on 429 / 5xx."""
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.get(url, params=params, timeout=30)
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = BACKOFF_BASE ** (attempt + 1)
                print(
                    f"  [retry] {resp.status_code} on {url} -- "
                    f"waiting {wait:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})"
                )
                time.sleep(wait)
                continue
            return resp
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            last_exc = exc
            wait = BACKOFF_BASE ** (attempt + 1)
            print(
                f"  [retry] {type(exc).__name__} on {url} -- "
                f"waiting {wait:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})"
            )
            time.sleep(wait)
    if last_exc is not None:
        raise last_exc
    raise httpx.RequestError(f"Failed after {MAX_RETRIES} retries: {url}")


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


def _flatten_decklist(decklist: dict) -> list[dict]:
    """Convert Limitless decklist sections into flat card list."""
    cards: list[dict] = []
    for section_key, partition in SECTION_MAP.items():
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


def scrape_decks(
    client: httpx.Client,
    *,
    max_tournaments: int = 500,
    deck_limit: int = 5000,
) -> tuple[list[dict], dict]:
    """Scrape Digimon decklists from Limitless tournaments."""
    now = datetime.now(UTC).isoformat()

    seen_fingerprints: set[frozenset] = set()
    unique_decks: list[dict] = []
    total_decks_with_lists = 0
    tournaments_checked = 0
    tournaments_with_decks = 0
    offset = 0
    page_size = 50

    print("Fetching Digimon tournaments from Limitless...")

    while tournaments_checked < max_tournaments and len(unique_decks) < deck_limit:
        try:
            page = _get_json(
                client,
                f"{BASE_URL}/tournaments",
                params={"game": GAME, "limit": page_size, "offset": offset},
            )
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            print(f"  Error fetching tournament page at offset={offset}: {exc}")
            break

        if not page:
            print("  No more tournaments.")
            break

        print(f"  Fetched page offset={offset} ({len(page)} tournaments)")

        for tourn in page:
            if len(unique_decks) >= deck_limit:
                break

            tid = tourn.get("id", "")
            tname = tourn.get("name", "unknown")
            tformat = tourn.get("format", "")
            tdate = tourn.get("date", "")
            tournaments_checked += 1

            try:
                standings = _get_json(
                    client, f"{BASE_URL}/tournaments/{tid}/standings"
                )
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                print(f"    Skip tournament {tid} ({tname}): {exc}")
                continue

            if not isinstance(standings, list):
                continue

            has_decks = False
            for player in standings:
                decklist = player.get("decklist")
                if not decklist:
                    continue

                cards = _flatten_decklist(decklist)
                if not cards:
                    continue

                total_decks_with_lists += 1
                fp = _card_fingerprint(cards)
                if fp in seen_fingerprints:
                    continue
                seen_fingerprints.add(fp)
                has_decks = True

                deck_record = {
                    "deck_id": f"limitless-dcg-{tid}-{player.get('name', 'unknown')}",
                    "archetype": player.get("archetype", ""),
                    "format": tformat or "Standard",
                    "url": f"https://play.limitlesstcg.com/tournaments/{tid}",
                    "source": "limitless",
                    "player": player.get("name", ""),
                    "event": tname,
                    "placement": player.get("placing", 0),
                    "date": tdate,
                    "scraped_at": now,
                    "cards": cards,
                }
                unique_decks.append(deck_record)

            if has_decks:
                tournaments_with_decks += 1

            if tournaments_checked % 10 == 0:
                print(
                    f"    Progress: {tournaments_checked} tournaments, "
                    f"{len(unique_decks)} unique decks"
                )

        offset += page_size

    stats = {
        "game": GAME,
        "tournaments_checked": tournaments_checked,
        "tournaments_with_decks": tournaments_with_decks,
        "total_decks_with_lists": total_decks_with_lists,
        "unique_decks": len(unique_decks),
    }
    return unique_decks, stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Digimon TCG decks from Limitless")
    parser.add_argument("--limit", type=int, default=5000, help="Max unique decks")
    parser.add_argument("--max-tournaments", type=int, default=500, help="Max tournaments to check")
    parser.add_argument("--output", type=str, default=str(OUT_FILE), help="Output JSONL path")
    args = parser.parse_args()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        decks, stats = scrape_decks(
            client,
            max_tournaments=args.max_tournaments,
            deck_limit=args.limit,
        )

    print(f"\nStats: {json.dumps(stats, indent=2)}")

    with open(out_path, "w", encoding="utf-8") as f:
        for deck in decks:
            f.write(json.dumps(deck, ensure_ascii=False) + "\n")

    print(f"Wrote {len(decks)} decks to {out_path}")


if __name__ == "__main__":
    main()
