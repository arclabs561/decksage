#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "selectolax"]
# ///
"""
Scrape tournament decklists from MTGTop8.com.

MTGTop8 is a major Magic: The Gathering tournament results database with
decklists from MTGO leagues, GPs, Pro Tours, RCQs, and more.

Strategy:
  1. POST to /search with format filter to get paginated deck listings
     (25 results per page). Each row has archetype, player, event, placement,
     date, and a link containing event_id + deck_id.
  2. For each deck, GET the deck page and parse card entries from the inline
     HTML (div.deck_line elements with id prefix 'md' for main, 'sb' for side).

Usage:
    uv run scripts/data/scrape_mtgtop8_decks.py \
        --output data/decks/decks_magic_mtgtop8.jsonl \
        --limit 5000 \
        --formats ST,MO,PI,LE,PAU
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import httpx
from selectolax.parser import HTMLParser


BASE_URL = "https://mtgtop8.com"
USER_AGENT = "DeckSage/1.0 (research project)"
RATE_LIMIT_DELAY = 0.5  # seconds between requests
MAX_RETRIES = 5
BACKOFF_BASE = 2.0

# Format codes -> human-readable names
FORMAT_MAP = {
    "ST": "Standard",
    "PI": "Pioneer",
    "MO": "Modern",
    "LE": "Legacy",
    "VI": "Vintage",
    "PAU": "Pauper",
    "EDH": "Duel Commander",
    "cEDH": "cEDH",
    "PREM": "Premodern",
}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _request_with_retry(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    data: dict | None = None,
    max_retries: int = MAX_RETRIES,
) -> httpx.Response:
    """HTTP request with exponential-backoff retry on 429 / 5xx."""
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            if method == "POST":
                resp = client.post(url, data=data, timeout=30)
            else:
                resp = client.get(url, timeout=30)
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
    msg = f"Failed after {max_retries} retries: {last_exc}"
    raise RuntimeError(msg)


# ---------------------------------------------------------------------------
# Search page parser: extract deck metadata from search results
# ---------------------------------------------------------------------------


def _parse_date(date_str: str) -> str:
    """Convert dd/mm/yy to YYYY-MM-DD."""
    try:
        parts = date_str.strip().split("/")
        if len(parts) == 3:
            day, month, year = parts
            if len(year) == 2:
                year = "20" + year if int(year) < 50 else "19" + year
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    except (ValueError, IndexError):
        pass
    return ""


def search_decks(
    client: httpx.Client,
    fmt: str,
    page: int,
) -> list[dict]:
    """Fetch one page of search results for a format. Returns deck metadata dicts."""
    url = f"{BASE_URL}/search"
    data = {"format": fmt, "current_page": str(page)}
    resp = _request_with_retry(client, "POST", url, data=data)
    if resp.status_code != 200:
        print(f"  [warn] search returned {resp.status_code} for {fmt} page {page}")
        return []

    tree = HTMLParser(resp.text)
    results = []

    # Results are in table rows. Each deck row has 6 cells:
    # [checkbox] [archetype+link] [player] [format] [event] [placement] [date]
    # We look for rows containing deck links (event?e=...&d=...)
    rows = tree.css("tr")
    for row in rows:
        cells = row.css("td")
        if len(cells) < 6:
            continue

        # Look for a deck link in the row
        deck_link = None
        archetype = ""
        for a_tag in cells[0].css("a") + cells[1].css("a"):
            href = a_tag.attributes.get("href", "")
            if "event?" in href and "&d=" in href:
                deck_link = href
                archetype = a_tag.text(strip=True)
                break

        if not deck_link:
            continue

        # Extract event_id and deck_id from the link
        e_match = re.search(r"e=(\d+)", deck_link)
        d_match = re.search(r"d=(\d+)", deck_link)
        if not e_match or not d_match:
            continue

        event_id = e_match.group(1)
        deck_id = d_match.group(1)

        # Extract player
        player = ""
        for a_tag in row.css("a.player"):
            player = a_tag.text(strip=True)
            break

        # Extract event name
        event_name = ""
        for cell in cells[3:5]:
            for a_tag in cell.css("a"):
                href = a_tag.attributes.get("href", "")
                if "event?" in href and "&d=" not in href:
                    event_name = a_tag.text(strip=True)
                    break
            if event_name:
                break

        # Extract placement and date from remaining cells
        placement = ""
        date_str = ""
        for cell in cells:
            text = cell.text(strip=True)
            # Date pattern: dd/mm/yy
            if re.match(r"^\d{2}/\d{2}/\d{2}$", text):
                date_str = text
            # Placement: number or range like "1", "3-4", "5-8"
            elif re.match(r"^\d+(-\d+)?$", text) and not date_str:
                placement = text

        results.append(
            {
                "event_id": event_id,
                "deck_id": deck_id,
                "archetype": archetype,
                "player": player,
                "event": event_name,
                "placement": placement,
                "date": _parse_date(date_str),
                "format_code": fmt,
            }
        )

    return results


# ---------------------------------------------------------------------------
# Deck page parser: extract card list
# ---------------------------------------------------------------------------

# Regex to extract cards directly from HTML.  Each card is a div like:
#   <div id="md..." class="deck_line ...">4 <span class="L14">Card Name</span></div>
# or with id=sb... for sideboard.  The (md|sb) prefix determines partition.
CARD_HTML_RE = re.compile(
    r'<div\s+id="?(md|sb)[^"]*"?\s+class="deck_line[^"]*"[^>]*>'
    r"(\d+)\s+<span[^>]*>([^<]+)</span>",
)


def fetch_deck_cards(
    client: httpx.Client,
    event_id: str,
    deck_id: str,
    fmt: str,
) -> list[dict]:
    """Fetch a deck page and parse the card list via regex on raw HTML."""
    url = f"{BASE_URL}/event?e={event_id}&d={deck_id}&f={fmt}"
    resp = _request_with_retry(client, "GET", url)
    if resp.status_code != 200:
        print(f"  [warn] deck page returned {resp.status_code}: {url}")
        return []

    cards = []
    for m in CARD_HTML_RE.finditer(resp.text):
        prefix = m.group(1)  # "md" or "sb"
        count = int(m.group(2))
        name = m.group(3).strip()
        partition = "Sideboard" if prefix == "sb" else "Main"
        if name:
            cards.append({"name": name, "count": count, "partition": partition})

    return cards


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Scrape MTGTop8 tournament decklists")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/decks/decks_magic_mtgtop8.jsonl"),
        help="Output JSONL file path",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5000,
        help="Maximum number of decks to scrape across all formats",
    )
    parser.add_argument(
        "--formats",
        default="ST,MO,PI,LE,PAU",
        help="Comma-separated format codes (ST, MO, PI, LE, VI, PAU, EDH, cEDH, PREM)",
    )
    args = parser.parse_args()

    formats = [f.strip() for f in args.formats.split(",")]
    args.output.parent.mkdir(parents=True, exist_ok=True)

    total_written = 0
    seen_deck_ids: set[str] = set()

    # Load existing deck IDs to avoid duplicates
    if args.output.exists():
        with open(args.output) as f:
            for line in f:
                try:
                    d = json.loads(line)
                    seen_deck_ids.add(d.get("deck_id", ""))
                except json.JSONDecodeError:
                    pass
        print(f"Loaded {len(seen_deck_ids)} existing deck IDs from {args.output}")

    with (
        httpx.Client(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client,
        open(args.output, "a") as out_f,
    ):
        for fmt in formats:
            if total_written >= args.limit:
                break

            fmt_name = FORMAT_MAP.get(fmt, fmt)
            print(f"\n{'=' * 60}")
            print(f"Format: {fmt_name} ({fmt})")
            print(f"{'=' * 60}")

            fmt_count = 0
            page = 1
            empty_pages = 0

            while total_written < args.limit:
                print(f"  Searching page {page}...")
                time.sleep(RATE_LIMIT_DELAY)

                deck_metas = search_decks(client, fmt, page)

                if not deck_metas:
                    empty_pages += 1
                    if empty_pages >= 2:
                        print(f"  No more results for {fmt_name}")
                        break
                    page += 1
                    continue

                empty_pages = 0

                for meta in deck_metas:
                    if total_written >= args.limit:
                        break

                    full_id = f"mtgtop8:{meta['deck_id']}"
                    if full_id in seen_deck_ids:
                        continue

                    time.sleep(RATE_LIMIT_DELAY)
                    cards = fetch_deck_cards(client, meta["event_id"], meta["deck_id"], fmt)

                    if not cards:
                        print(f"    [skip] No cards for deck {meta['deck_id']}")
                        continue

                    record = {
                        "deck_id": full_id,
                        "archetype": meta["archetype"],
                        "format": fmt_name,
                        "url": f"{BASE_URL}/event?e={meta['event_id']}&d={meta['deck_id']}&f={fmt}",
                        "source": "mtgtop8",
                        "player": meta["player"],
                        "event": meta["event"],
                        "placement": meta["placement"],
                        "created_at": meta["date"],
                        "cards": cards,
                    }

                    out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    out_f.flush()
                    seen_deck_ids.add(full_id)
                    total_written += 1
                    fmt_count += 1

                    if total_written % 50 == 0:
                        print(f"    Progress: {total_written} total, {fmt_count} {fmt_name}")

                page += 1

            print(f"  {fmt_name}: {fmt_count} decks scraped")

    print(f"\nDone. Total decks written: {total_written}")
    print(f"Output: {args.output}")

    # Quick validation
    if args.output.exists():
        with open(args.output) as f:
            lines = sum(1 for _ in f)
        print(f"Total lines in file: {lines}")

        # Show a sample
        with open(args.output) as f:
            for i, line in enumerate(f):
                if i == 0:
                    d = json.loads(line)
                    print(f"\nSample deck: {d['archetype']} ({d['format']})")
                    print(f"  Player: {d['player']}, Event: {d['event']}")
                    print(f"  Cards: {len(d['cards'])} entries")
                    print(f"  Date: {d['created_at']}")
                    break


if __name__ == "__main__":
    main()
